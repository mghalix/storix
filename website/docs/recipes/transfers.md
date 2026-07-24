# Tune transfer memory and throughput

A bulk transfer (`sx push`, `sx pull`, or your own loop over `echo`/`stream`)
moves one file per in-flight stream. Two numbers decide what it costs:

- **how many streams run at once** - the fan-out, 32 by default
- **how much each stream buffers** - the backend's chunk and prefetch sizes

Wall time scales with the first, peak memory with the product of both. This
page is the map of which knob does what, and what changing it costs.

## The memory model

```text
peak memory  ~  streams in flight  x  per-stream buffers
```

For Azure, a stream's buffers are the initial download request
(`read_prefetch_size`) plus one range chunk (`read_chunk_size`) on reads, and
one write batch (`write_chunk_size`) on writes. Nothing accumulates across
files: a directory of 800 files costs the same as a directory of 8 once the
fan-out is saturated.

Measured on a 480 MiB pull (12 files of 40 MiB, fan-out 12, one home
connection to Azure):

| `read_prefetch_size` | wall time | peak RSS |
| -------------------- | --------- | -------- |
| 32 MiB               | 43.3s     | 708 MB   |
| 8 MiB (default)      | 42.6s     | 273 MB   |
| 4 MiB                | 43.1s     | 225 MB   |

The prefetch is the only buffer a download holds whole before it yields
anything, so it is what a concurrent pull multiplies. Shrinking it costs
nothing while many streams are running, because their round trips overlap.

## The knobs

Every one of these is a `STORIX_<PROVIDER>_*` environment variable, a
`get_storage(...)` keyword, or a backend constructor argument. Sizes are in
bytes and must be positive.

| Setting                           | Default | Raise it when                                     | Lowering it costs         |
| --------------------------------- | ------- | ------------------------------------------------- | ------------------------- |
| `STORIX_AZURE_READ_PREFETCH_SIZE` | 8 MiB   | one big file at a time matters more than many      | more requests per byte    |
| `STORIX_AZURE_READ_CHUNK_SIZE`    | 4 MiB   | round trips dominate (high latency, large files)   | more requests per byte    |
| `STORIX_AZURE_WRITE_CHUNK_SIZE`   | 4 MiB   | uploads are large and memory is plentiful          | more requests per byte    |

```bash
# a workstation pulling one large file at a time: prefer round trips saved
STORIX_AZURE_READ_PREFETCH_SIZE=33554432

# a small container running many concurrent transfers: prefer the headroom
STORIX_AZURE_READ_PREFETCH_SIZE=4194304
```

```python
from storix import get_storage

fs = get_storage("azure", read_prefetch_size=32 * 1024 * 1024)
```

## Requests cost money, not just time

Smaller chunks mean more requests for the same bytes, and object stores bill
per transaction as well as per byte. Pulling a 1.2 GB file with a 8 MiB
prefetch and 4 MiB chunks is roughly 300 read requests; at 32 MiB and 16 MiB
it is roughly 75. The per-request price is small (fractions of a cent per ten
thousand), but it is real at scale, and it is the reason the sizes are
settings rather than constants: pick the point on the curve your bill and
your memory budget agree on.

The same applies to rate limits. A provider that throttles a single account
(HTTP 503 `SlowDown` on S3, `ServerBusy` on Azure) is counting requests, so a
transfer that is both wide (many streams) and finely chunked is the one most
likely to be throttled. If you see throttling, raise the chunk sizes first:
fewer, larger requests for the same throughput.

## What `sx` does on its own

The `sx` command line pins glibc's `mmap` threshold at startup so that
multi-megabyte transfer buffers are returned to the operating system when
they are freed, rather than being retained in per-thread allocator arenas.
Without it, a finished bulk push can hold hundreds of megabytes of resident
memory that Python has already released. It is a no-op on any other libc, and
it is deliberately not done on library import - a library has no business
setting a process-wide allocator policy for your application.

## Current limits

- **The fan-out is fixed at 32.** It is a constant today, not a setting. A
  directory with fewer files than that uses fewer streams, which is why a
  six-file pull is much slower than an eight-hundred-file push over the same
  link.
- **A single file uses a single stream.** storix parallelizes across files,
  never within one, so one large file transfers at one connection's speed
  however fast your link is. Range-parallel reads are under consideration;
  see the roadmap.
