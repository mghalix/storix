# 28. Concurrent recursive traversal: level-buffered core walk

Status: proposed

## Context

One `scandir` is one remote directory operation, but recursive consumers issue
those operations sequentially today. `Storix.walk` descends depth-first and
does not list the next directory until the current subtree returns. `sx tree`
does not consume that core method at all: it has a second depth-first recursion
around `scandir`. `find` and `glob` inherit the core walk, while `sx du` uses its
post-order form. All four therefore pay roughly the sum of directory latencies.

The effect is visible on the HNS Azure container used for ADR 0027. `sx tree -L
1` (one root listing) took 1.62s. `sx tree -L 2` (the root plus its nine child
directories) took 14.36s. An unrestricted traversal was still running after
72.33s and was interrupted. This is network wait, not rendering or CPU.

ADR 0025 provides the portable `concurrent` thunk helper: bounded asyncio work
in async and a bounded thread pool in sync, with results returned in submission
order and errors left in the Storix taxonomy. ADR 0026 intended recursive
consumers to use it, but the implemented walk stayed sequential and the CLI
kept its own traversal. ADR 0027 deferred the correction as concurrent walk.

The core boundary applies: traversal, depth limits, concurrency, hidden-entry
semantics, and backend errors belong to `Storix`. `sx tree` may choose colors,
branches, and sibling sort order, but it must not decide how storage is walked.

## Decision

Replace recursive depth-first I/O with a bounded, level-buffered traversal in
the core. It continues to use the portable `scandir` port path; no backend
capability or recursive-listing fast path is required.

### Frontier execution

The engine holds a frontier of directories at one depth, initially the
requested root. It splits that frontier into chunks no larger than
`DEFAULT_CONCURRENCY`. For each chunk it calls `concurrent` with one thunk per
directory. A thunk materializes that directory's immediate `scandir` result:
materialization is necessary because returning a generator from a sync worker
would defer its I/O back onto the caller thread.

`concurrent` returns listings in frontier submission order, not completion
order. Within a listing, backend order remains intact. The engine filters
hidden entries exactly as `scandir` does and collects visible child directories
for the next frontier. It never creates one task for every directory in the
tree; concurrency and task memory are bounded per chunk.

The public method gains an additive depth bound:

```python
walk(
    path=None,
    *,
    all=False,
    top_down=True,
    max_depth: int | None = None,
) -> Iterator[DirEntry]
```

Depth 1 includes immediate children and does not list inside child
directories. Zero includes no descendants. Negative values raise `ValueError`.
The bound is enforced before a directory enters the next frontier, so `tree -L
N` avoids the remote calls it excludes instead of walking and filtering later.

### Ordering

`top_down=True` emits a level's entries in stable parent/listing order, then
moves to the next level. Every directory therefore appears before all of its
descendants. Exact depth-first order is no longer part of the contract.

`top_down=False` discovers the same frontiers, emits file leaves as they are
read, and retains directory entries by depth. After traversal it emits
directories from deepest level to shallowest, preserving stable order within a
level. Every descendant is therefore emitted before its ancestor, which keeps
`sx du`'s single-pass size propagation correct. This mode stores one
`DirEntry` per directory until traversal completes; file entries remain
streaming.

This is an observable ordering change from the current depth-first generator.
Storix 0.x treats it as breaking and releases it under the 0.5 minor line per
ADR 0021. The documented ordering contract becomes relational (ancestor before
or after descendant), not a particular depth-first sibling sequence.

### Core consumers and CLI

`find` and `glob` continue to filter the top-down walk. `sx du` continues to
consume the post-order walk. All inherit frontier concurrency without their own
thread or task management.

`sx tree` deletes its `children_of`/recursive storage loop and calls
`walk(max_depth=level)`. It may materialize the requested `DirEntry` stream to
group siblings, apply `--sort name|time|size`, and draw branches; that is
presentation over facts the core already fetched, not another traversal.
Missing sizes or timestamps needed for a requested sort remain batched through
the existing `stat_all` helper.

Closing a walk or encountering an error leaves no orphan work. A frontier chunk
finishes under `concurrent`'s existing semantics, then the first error in stable
submission order propagates unwrapped.

### Verification

Add a latency backend whose `list_dir` records active calls. Tests cover both
generated flavors and prove:

- sibling directory listings overlap and never exceed `DEFAULT_CONCURRENCY`;
- top-down ancestors precede descendants and post-order reverses that relation;
- `max_depth` prevents excluded backend calls;
- hidden directories are neither yielded nor scheduled unless `all=True`;
- completion timing does not reorder results;
- errors propagate as the original Storix exception; and
- `sx tree` delegates traversal to `walk` rather than calling `scandir`
  recursively.

Benchmark the deterministic latency backend and the ADR 0027 Azure container.
For a wide level, expected latency moves from the sum of sibling listings toward
the slowest listing in each bounded chunk. A single deep chain has no available
fan-out and is not expected to improve.

Rejected: use backend `list_tree` for all recursive consumers. A delimiter-less
recursive listing loses per-directory request boundaries, can exceed the key
bound before proving emptiness, and cannot replace the portable rich-entry walk
on every backend. Rejected: add concurrency only inside `sx tree`; `find`,
`glob`, and `du` would remain slow and the driving adapter would continue to own
core behavior. Rejected: recursively spawn one task per directory; a large tree
would create unbounded work and make cancellation and error order unpredictable.
Rejected: preserve exact depth-first output with one-level sibling prefetch; it
helps a shallow wide root but leaves deeper sibling frontiers serialized and
does not deliver the measured tree-wide improvement.

## Consequences

Wide remote trees become bounded by level/chunk latency instead of the sum of
every directory latency. Sync and async keep one source-level algorithm and use
their audited `concurrent` twins. `tree`, `find`, `glob`, and `du` share one
traversal and one error model.

Costs: top-down walk buffers one frontier and its immediate listings;
post-order walk additionally retains directory entries until the reverse-depth
emission. Output order changes from depth-first to stable level order, requiring
the 0.5 minor release. Deep single-child chains do not become faster, because
they contain no independent directory listings to overlap.

Implementation is staged. ADR acceptance precedes code changes.
