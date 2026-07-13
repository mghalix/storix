# 17. Bidirectional streaming and provider-aware chunking

Status: accepted

## Context
The original read path reused a 100 MiB write-batching constant. Local
and memory files below that size therefore appeared as one chunk, while
Azure used its SDK's smaller native chunks. `stream()` exposed no size
control, so the same port method had materially different behavior by
provider.

The write path had the opposite problem. `echo()` accepted scalars,
files, and iterators, but forwarded iterator boundaries directly to the
backend. A generator yielding one CSV row at a time could therefore
cause one Azure append request per row. Source production boundaries
were accidentally treated as transport boundaries.

Adding streaming primitives to the port also raised an extension
question: a simple custom backend may naturally support whole-object
reads and writes but have no native streaming API. Requiring every such
backend to implement fake stream methods would add boilerplate; making
whole-object methods the only primitives would force built-in and cloud
backends to buffer entire files.

This ADR supersedes ADR 0003 only for the read/write primitive shape;
its other port and DTO decisions remain in force.

## Decision
### Public API
`cat()` remains the explicit whole-file read. `stream(...,
chunk_size=N)` is its bounded counterpart: every yielded chunk is at
most `N` bytes. It splits larger provider chunks but never combines
smaller ones, because filling an output buffer would add latency and
hide the provider's readiness boundary.

`echo(..., chunk_size=N)` accepts the same scalar, file-like, iterable,
and async-iterable sources as before. A scalar remains one logical
payload, like `Path.write_bytes()`, while the backend may split it into
transport batches. Iterator ticks carry no storage meaning. Writes
split oversized source chunks and combine small yields into target
backend batches; there is no `preserve_chunks` mode.

Both methods use the keyword `chunk_size` with the same validation.
`None` delegates to the backend's preferred default. Explicit zero or
negative values raise stdlib `ValueError`. There is no `-1` whole-file
sentinel; callers use `cat()` when they want one complete `bytes`
result.

### Port boundary and custom backends
The port has two I/O pairs:

- `read(path) -> bytes` and `read_stream(path, *, chunk_size=None)`
- `write(path, data: bytes, ...)` and `write_stream(path, iterator, *,
  chunk_size=None, ...)`

`BackendBase` requires at least one member of each pair, independently
per direction, in addition to the four structural primitives. It
derives a whole-object operation from a native stream by collecting or
wrapping one chunk. It derives a stream from a whole-object operation
by materializing once, then splitting a read or collecting a write.
The compatibility fallbacks are correct but not bounded-memory. If
neither member of a pair is implemented, the base raises a clear
`NotImplementedError` rather than recursing.

Local and Azure are streaming-native. Memory implements the stream
surface directly but necessarily retains each stored file in process. A
dict, database, or other naturally whole-object custom backend can
implement `read()` and `write()` only and inherit the compatibility
stream forms. This port change is intentionally breaking while the
library is new: custom backends and layers overriding stream methods
must add the keyword-only `chunk_size` parameter, and streaming sinks
move from `write()` to `write_stream()`.

### Batching implementation
Read normalization is split-only. Write normalization is split and
coalesce, linear in input bytes, and bounded by the selected batch
size. Exact-sized immutable `bytes` pass through unchanged. Oversized
`bytes` use direct C-level slicing; only small fragments are buffered
with stdlib `io.BytesIO`. File-like Python sources are pulled in 1 MiB
pieces before provider batching.

`itertools.batched` was rejected. It batches iterable elements, not a
byte stream: it cannot split one oversized bytes value or fill a batch
across differently sized yields without another buffering layer, and
its tuples add work without replacing the required algorithm.

### Defaults and Azure
There is no forced global provider size. `None` resolves as follows:

- generic/local read and local write: 1 MiB
- Python file-like source reads: 1 MiB
- Azure SDK range reads and consumer output: 4 MiB
- Azure append request batches: 4 MiB
- Azure initial download request: 32 MiB

Azure exposes `read_chunk_size`, `write_chunk_size`, and
`read_prefetch_size` through its constructor, factory overrides, and
`STORIX_AZURE_*` settings. The SDK's buffers are host memory even when
the object is remote, so the provider defaults balance request overhead
against small hosts and serverless workers. A per-call read size is an
output maximum; it does not rebuild the Azure client or coalesce smaller
SDK chunks. Writes remain sequential and bounded, but batching prevents
one `append_data` request per tiny producer yield. Transfer concurrency
is a separate future decision because it changes memory and retry
semantics.

## Consequences
Read and write streaming now have symmetric controls without pretending
their semantics are identical: reads prioritize prompt delivery, writes
prioritize efficient transport batches. Local and memory no longer use
100 MiB read buffers, Azure avoids small-request explosions, and callers
can bound consumer chunks independently of provider configuration.

The cost is an intentional backend-port break and an explicit caveat:
whole-object compatibility fallbacks materialize a complete payload.
The conformance suite covers positive and invalid sizes across backends
and layers; direct helper tests cover splitting, coalescing, empty
chunks, exact pass-through, and fallback recursion; credential-free
Azure tests pin append batches, offsets, and split-only reads.
