# 19. ObservabilityLayer: progress as transfer events, not a callback

Status: accepted

## Context
We want upload/download progress (for `sx` and library consumers) now, and a
white-box audit/metrics story later. The obvious reach is a per-call
`on_progress` callback plus a `total_size` argument on `echo`/`stream`. It does
not survive scrutiny:

- A percentage needs a total, and the total is never storix's to know. An
  arbitrary write iterator has no knowable end (`fs.echo(some_stream, ...)`).
  The total is always the *caller's* knowledge of their own source: a local
  file's `stat().st_size`, an HTTP upload's `Content-Length`. So `total_size`
  as a core argument is redundant, and stat-for-progress is pure overhead.
- storix's only honest contribution is "bytes transferred so far", which is
  always knowable, and which a layer wrapping the port emits for free by
  counting the read/write stream. Progress is the transfer-event slice of the
  observability story we already planned (0.5.0), not a separate feature. A
  callback would be a second mechanism for one need.

## Decision
Progress is delivered by an `ObservabilityLayer` (a `LayerBase` subclass) that
wraps `read_stream`/`write_stream`, counts bytes at the pull boundary, and emits
a `TransferEvent` per chunk to a consumer-supplied sink. No core signature
changes, no `total_size`, no stat.

```python
@dataclass(frozen=True, slots=True, kw_only=True)
class TransferEvent:
    op: Literal["read", "write"]
    path: PurePosixPath
    transferred: int   # cumulative bytes; the consumer owns the total
```

- The consumer owns the total and computes any percentage: a bar when it has a
  total (it produced the source, so it does), a counter or spinner when it does
  not (a truly unbounded source).
- Counting at the pull boundary tracks backend-acked bytes to within one
  in-flight batch (the pipeline is pull-based; a backend requests the next chunk
  only after awaiting the current write). One site covers every backend,
  including future opendal/fsspec, with zero per-backend edits.
- The sink may be sync or async (SSE); await it if it returns a coroutine
  (the `inspect.iscoroutine` idiom).
- v0 scope is transfer events only. This IS the first increment of the
  observability/audit story, grown later by emitting op-start/end/error around
  the other port methods. Named `ObservabilityLayer` from day one (not
  `ProgressLayer`) so it is the seed, not a throwaway to deprecate.
- Composition: outermost by convention (counts the full logical transfer);
  removable (default); scoped per session via `with_layer`/`without_layer`.

Rejected: a per-call `on_progress` + `total_size` (redundant total, stat
overhead, core signature churn, two mechanisms for one need). Also rejected: a
`finalizing`/flush phase in v0 - Azure's post-loop flush is invisible to a
port-wrapping layer, and it is not worth per-backend cooperation for a bar that
fills then completes.

## Consequences
`sx` and any consumer get progress from one contract with zero core churn; the
layer composes and is removable; the observability roadmap item starts now as a
real increment instead of waiting for 0.5.0. Cost: a consumer who wants a
percentage supplies the total it already owns. Implementation is ~25 lines.

Implementation (codegen layer: edit `_async` only, then `just gen`; `just check`):

- [ ] `src/storix/_async/layers/observability.py`: `TransferEvent` +
      `ObservabilityLayer(LayerBase)`; override `read_stream`/`write_stream` to
      route through a `_count` async-iterator that increments and emits per
      chunk; sink may be sync or async.
- [ ] Export `ObservabilityLayer` and `TransferEvent` from `layers/__init__`,
      `_async/__init__`, `aio`, `storix/__init__`, and each `__all__` (mirror the
      other layers).
- [ ] Slot into the parametrized conformance suite: a pure passthrough when no
      sink is set; with a collecting sink, assert cumulative `transferred`
      equals a known payload size.
- [ ] `just gen`, then `just check`.
- [ ] (later, not v0) op-start/end/error events for the audit story.

0.4.1 (backward-compatible feature -> patch; 0.4.0 already published).
