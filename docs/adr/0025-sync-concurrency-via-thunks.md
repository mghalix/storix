# 25. Concurrency in the sync flavor: a thunk-based fan-out

Status: accepted

## Context

The async core fans out multi-target work concurrently through the `gather`
shim (`_async/_compat.py` = `asyncio.gather` with a bounded semaphore): `cat`,
`touch`, `mkdir`, `rm`, `mv`, `cp`, and `du`'s subtree walk run N backend
operations at once. The sync flavor does none of it. `unasync.py` strips
`await`, so an argument expression like `backend.read(t)` executes immediately
during `*` unpacking; by the time the sync `gather` (`_sync/_compat.py`) runs,
every result is already computed, sequentially. The shim documents this.

The CLI runs on sync, so `sx du`/`cp`/`rm` on a wide cloud tree pay N serial
round trips where the async API would pay one. This is not the adapters being
slow - the sync backends are real blocking-library twins (`os`, the non-aio
Azure SDK, `opendal.Operator`), and a single op is library-fast, and those
blocking calls release the GIL during I/O. It is the orchestration: concurrency
across operations is the core's job, and sync Python has no built-in I/O
concurrency. See `docs/design/deferred-decisions.md` for the original analysis.

The fix must not drop codegen and must not regress the async path.

## Decision

Replace the eager `gather(*(backend.op(x) for x in items))` idiom with a
deferred one: a `concurrent` helper that receives the work as **thunks**
(zero-arg callables), so the sync flavor can dispatch them to threads instead
of pre-computing them.

```python
# _compat.py (both flavors), signature identical:
def concurrent[T](
    thunks: Iterable[Callable[[], T]], *, limit: int = DEFAULT_CONCURRENCY
) -> list[T]: ...
```

- **async** (`_async/_compat.py`): `await gather(*(t() for t in thunks),
  limit=limit)` - each `t()` returns a coroutine, gathered concurrently under
  the existing bounded semaphore.
- **sync** (`_sync/_compat.py`): a bounded `ThreadPoolExecutor(max_workers=
  limit)`; submit every thunk, return results in submission order, and let the
  first exception propagate unwrapped when its future is resolved (remaining
  submitted threads run to completion). Because the sync backends do
  GIL-releasing blocking I/O, the threads give genuine I/O concurrency.

**Call sites** in `_async/core.py` and `_async/backends/generic.py` migrate from
`gather` to `concurrent`, building each thunk with `functools.partial` - which
avoids the lambda late-binding trap in a comprehension and reads cleanly, and
covers every site shape uniformly:

```python
# homogeneous map
concurrent(partial(self._backend.read, t) for t in targets)
# per-item conditional (delete_tree vs delete)
concurrent(
    partial(self._backend.delete_tree if raw.kind is PathKind.DIRECTORY
            else self._backend.delete, target)
    for target, raw in zip(targets, stats, strict=True)
)
# zipped
concurrent(partial(self._backend.move, s, d) for s, d in zip(sources, targets))
# mixed fan-out (copy_tree subdirs + copy files)
concurrent(chain(
    (partial(copy_tree, backend, src / s, dst / s) for s in subdirs),
    (partial(backend.copy, src / f, dst / f) for f in files),
))
```

Passing a `partial` un-invoked is what lets sync defer to threads; the async
flavor invokes it to get a coroutine. The source is identical in both flavors -
only the two hand-written `_compat` twins differ, as they already do - so
codegen is untouched. The now-unused sync `gather` is removed; the async
`gather` stays (`concurrent` is built on it).

**Thread-safety.** Every fan-out is over *distinct* targets - different keys,
files, or blobs - so no two threads touch the same object; there is no shared
mutable state per operation. The shared backend *client* is called
concurrently, which the sync SDKs support (the Azure SDK and `opendal.Operator`
are built for it; `MemoryBackend`'s dict operations on distinct keys are
GIL-atomic). The parametrized conformance suite gains a case that runs a
multi-target write and read under the thread pool on every backend, to catch
any backend that is not concurrency-safe.

**Error semantics** stay the async default: the first exception propagates
unwrapped (no `ExceptionGroup`), so `except PathNotFoundError` keeps working and
the storix taxonomy survives.

Rejected: a `concurrent_map(fn, iterable)` that only takes a single homogeneous
callable - it does not fit the conditional/zip/mixed sites without contortions;
the thunk form is uniform. Rejected: `asyncio.run` from the sync core to reuse
the event loop - it cannot run inside an already-running loop and forces an
async dependency into the sync path; threads are the honest sync tool.

## Consequences

The sync core's multi-target operations (`cat`, `touch`, `mkdir`, `rm`, `mv`,
`cp`, `du`) become genuinely concurrent, so `sx du`/`cp`/`rm` on a wide cloud
tree speed up to roughly the async path, and any future sync consumer inherits
it. Codegen and the async path are unchanged. Cost: a `ThreadPoolExecutor` per
fan-out in sync (bounded, short-lived), and one more concept in `_compat`.

Not covered here: `sx tree` and `sx ls`'s emptiness checks are still sequential
CLI loops - they benefit only once the recursive walk moves into the core
(the `find`/`walk` work), which will express its per-level fan-out through this
same `concurrent` helper.

0.4.4 (backward-compatible; internal-only, no public API change; ADR 0021).
