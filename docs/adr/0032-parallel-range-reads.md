# 32. Parallel range reads for single-file transfers

Status: accepted

## Context

storix parallelizes transfers across files and never within one. `sx push`
and `sx pull` hand one thunk per file to the core `concurrent` helper, so a
directory of 826 files runs at the fan-out ceiling (32 streams) while a
directory of 6 files runs 6 streams, and a single file runs exactly one.

That is the whole explanation for an asymmetry that looks like a
direction-of-travel problem and is not. Measured on one home connection to
Azure, same link, same session:

| workload                     | streams | throughput |
| ---------------------------- | ------: | ---------: |
| push, 826 files              |      32 | 115 MB/s   |
| pull, 6 files of 1.2 GB      |       6 |  12 MB/s   |
| read one 200 MiB file        |       1 | 3.8 MB/s   |

A single HTTPS stream to the provider carries 2 to 4 MB/s here regardless of
direction, because it is bounded by round trips rather than bandwidth:
`read_stream` issues one range GET per chunk and drains it before asking for
the next, so every chunk pays a full round trip of dead air, and the server's
congestion window restarts after each idle gap. Aggregate throughput is
therefore `streams x per-stream rate`, and the only lever a one-file pull has
is `streams`.

A prototype confirmed the headroom (200 MiB file, ranges fetched with
`download_file(offset=, length=)` in a thread pool, written with `pwrite`):

| ranges in flight | wall   | throughput | peak RSS |
| ---------------- | -----: | ---------: | -------: |
| 1 (today)        | 55.87s |   3.8 MB/s |    91 MB |
| 4                | 33.33s |   6.3 MB/s |   261 MB |
| 8                | 18.34s |  11.4 MB/s |   297 MB |
| 16               | 16.53s |  12.7 MB/s |   460 MB |

Three things follow from that table. Eight ranges is a 3.0x improvement and
the curve flattens after it, because the link saturates at the same 12 to 13
MB/s a six-file pull reaches. The memory column is an artifact of the
prototype calling `readall()` per range, which materializes a whole range;
any real implementation must stream each range. And more ranges means more
requests for the same bytes, which is what object stores bill per transaction
and throttle on (`ServerBusy` on Azure, `SlowDown` on S3), so the request rate
is a budget to be spent, not a free parameter.

Related decisions: ADR 0017 (bidirectional streaming boundary), ADR 0027
(`bulk_listing` as an internal, silently-gated performance capability), ADR
0029 (transfer setup in `sx`).

## Decision

### 1. The port grows `read_range`, not a wider `read_stream`

```python
def read_range(
    self,
    path: PurePosixPath,
    *,
    offset: int,
    length: int,
    chunk_size: int | None = None,
) -> Iterator[bytes]:
```

`BackendBase` implements it correctly for every backend by streaming and
discarding up to `offset`, then yielding `length` bytes. A backend that never
heard of ranges still returns the right bytes.

The alternative - adding `offset`/`length` keywords to `read_stream` - was
rejected on safety, not aesthetics. Every backend already overrides
`read_stream`, so widening it would silently make each existing override
ignore the new arguments and return the wrong bytes until every backend was
updated by hand, including third-party ones. A separate method with a correct
default cannot fail that way.

### 2. `Capabilities.ranged_reads` advertises efficiency, never gates behavior

A new capability, defaulting to False like every other, set by backends whose
range read is a native single request (Azure ADLS, the opendal-backed
object stores, local disk, memory). It follows the `bulk_listing` precedent
from ADR 0027: an internal speed gate the core consults to choose a fast
path, silently falling back, never raising `UnsupportedOperationError`. It is
not user-facing, because "can this backend read a range" is always yes - only
"cheaply" varies.

### 3. The core owns the parallelism: `Storix.download`

```python
def download(self, path: StrPathLike, dest: BinaryIO, *, ranges: int | None = None) -> int:
```

Reads `path` into an already-open, seekable binary sink and returns the bytes
written. It is the parallel counterpart of `stream()`: `stream()` stays the
sequential, ordered, sink-agnostic API that a FastAPI `StreamingResponse`
needs, and `download()` is for when the destination can be written out of
order.

The core, not `sx`, owns it, for the reason recorded in the architecture
guide: a capability re-implemented in a driving adapter is one the next
driving adapter re-implements again. `sx pull`, the planned pathlike adapter,
and any future MCP server all get the same behavior from one place.

The core still never opens a local file. The caller passes the sink, so the
core writes through the file object it was handed and stays free of local
filesystem policy (paths, permissions, parents). A non-seekable sink is not
an error: `download` detects it (`dest.seekable()`) and streams sequentially.

### 4. Range parallelism spends the existing fan-out budget

This is the constraint that keeps rate limits where they are today. The
number of ranges is derived from how much of the fan-out a transfer is
actually using:

```text
ranges = clamp(DEFAULT_CONCURRENCY // files_in_flight, 1, MAX_TRANSFER_RANGES)
```

A 826-file pull already saturates 32 streams, so it gets 1 range per file and
behaves exactly as it does today. A 6-file pull gets 5 ranges each, for 30
streams. A single-file pull gets `MAX_TRANSFER_RANGES` (8). Total requests in
flight never exceeds what a directory transfer already issues, so no workload
becomes more likely to be throttled than the ones running today.

Ranges are only opened for files at or above `MIN_RANGE_SIZE` (64 MiB by
default). Below that, one request for the whole file beats several, and the
extra transactions would be pure cost.

### 5. Memory stays bounded per range, and the knobs stay configurable

Each range is streamed at `chunk_size` and written with `os.pwrite` at its
offset, so peak memory is `ranges x chunk_size` (8 x 4 MiB = 32 MB), not
`ranges x range_size`. The prototype's 460 MB was `readall()`, and it is
exactly what this rules out.

`MAX_TRANSFER_RANGES` and `MIN_RANGE_SIZE` are settings, not constants:
`STORIX_MAX_TRANSFER_RANGES=1` turns the whole behavior off for anyone whose
bill or provider quota prefers the old shape, and per-call `ranges=` overrides
both. Both are documented on the website with what they cost in requests, per
the project's rule that an optimization that spends money must be opt-outable
and explained.

### 6. Failure is loud and whole

A failed range fails the download through the existing `concurrent`
semantics: the first exception in submission order propagates unwrapped, the
storix error taxonomy survives, and the sink is left with a partial file that
the caller (for `sx pull`, the CLI) removes. No partial download is ever
reported as success. Retry of an individual range is deliberately out of
scope; it belongs with the resilience work already on the roadmap.

## Measured outcome

The shipped implementation, same link and same 200 MiB file, bytes verified by
digest on every run: 61.53s at one range, 25.51s at eight - **2.1x**, with peak
resident memory at 173 MB.

That is below the prototype's 3.0x, and the difference is the deliberate part:
the prototype called `readall()` per range and held a whole range in memory,
while the shipped path streams each range at `chunk_size` and writes it out as
it arrives. Trading some pipelining for a bounded, predictable memory profile is
the right side of that trade for a library, and the ceiling can be raised later
by prefetching the next chunk of a range while the current one is written.

## Consequences

- A single large file pulls about 3x faster on a typical home link, and a
  small-file-count directory scales to the same ceiling as a large one. This
  is the last remaining large gap between `sx pull` and `sx push`.
- The port grows one method with a correct default, so it is not a breaking
  change for any backend, in-tree or third-party. Backends that do not set
  `ranged_reads` keep exactly today's behavior: the core sees no capability
  and does not parallelize.
- The core grows one public method (`download`) to maintain and document. It
  is a genuine addition to the library surface, not just CLI plumbing: users
  writing to disk or to any seekable sink want it too.
- Large-file reads issue more requests for the same bytes (bounded by
  `MAX_TRANSFER_RANGES`), which costs transactions. In-flight request
  concurrency does not rise, so throttling exposure is unchanged.
- `stream()` is untouched. Ordered, sequential, sink-agnostic streaming
  remains the default path and the one the docs point at for HTTP responses.
- The symmetric case, parallel multi-part uploads (Azure block staging, S3
  multipart), is not decided here. The same budget rule and the same
  capability shape should apply when it is; `push` is not currently the
  bottleneck, so it waits for evidence.
