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

Every provider understands the same two sizes, and every provider that
fetches over the network adds a third. Each is a `STORIX_<PROVIDER>_*`
environment variable, a `get_storage(...)` keyword, or a backend constructor
argument. Sizes are in bytes and must be positive.

| Setting | Local | S3 / GCS / Azure Blob | Azure ADLS |
| --- | --- | --- | --- |
| `READ_CHUNK_SIZE` | 1 MiB | 1 MiB | 4 MiB |
| `WRITE_CHUNK_SIZE` | 1 MiB | 1 MiB | 4 MiB |
| `READ_PREFETCH_SIZE` | not applicable | read chunk size | 8 MiB |

`READ_CHUNK_SIZE` is both the largest chunk a read yields and the size the
engine is asked to fetch per request. `WRITE_CHUNK_SIZE` is the batch a write
accumulates before sending a request. `READ_PREFETCH_SIZE` is the opening read
of a stream, the one buffer a download holds before it yields anything; local
disk has no equivalent, so it is not offered there rather than being accepted
and ignored.

Raising a size means fewer, larger requests and more memory per in-flight
transfer. Lowering it means the opposite. There is no universally right
answer, which is why they are settings.

```bash
# a workstation pulling one large file at a time: prefer round trips saved
STORIX_AZURE_READ_PREFETCH_SIZE=33554432

# a small container running many concurrent transfers: prefer the headroom
STORIX_AZURE_READ_PREFETCH_SIZE=4194304

# the same knobs, any provider
STORIX_S3_READ_CHUNK_SIZE=8388608
STORIX_LOCAL_WRITE_CHUNK_SIZE=4194304
```

```python
from storix import get_storage

fs = get_storage("azure", read_prefetch_size=32 * 1024 * 1024)
fs = get_storage("s3", bucket="media", read_chunk_size=8 * 1024 * 1024)
```

`sx` reads exactly the same environment, so a variable exported for your
application tunes the CLI too.

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

## One file, several ranges

One stream is one connection, and a connection to an object store is bounded by
round trips rather than bandwidth. So a directory of eight hundred files
saturates a link that a single large file cannot come close to.

`download()` closes that gap: it fetches several byte ranges of the same file at
once and writes each at its own offset. Measured on one home connection to
Azure, a 200 MiB file, bytes verified identical on every run:

| ranges | wall   | throughput |
| ------ | -----: | ---------: |
| 1      | 61.53s |   3.3 MB/s |
| 8      | 25.51s |   7.8 MB/s |

```python
from storix import get_storage

fs = get_storage("azure")
with open("movie.mkv", "wb") as sink:
    fs.download("/media/movie.mkv", sink)      # ranges chosen for you
    fs.download("/media/movie.mkv", sink, ranges=1)   # force one stream
```

`sx pull` uses it automatically. The number of ranges comes out of the fan-out
budget the transfer is **not** using:

```text
ranges = clamp(32 / files in flight, 1, 8)
```

An eight-hundred-file pull already saturates 32 streams, so it opens one range
per file and behaves exactly as before. A six-file pull opens five ranges each.
A single-file pull opens eight. Total requests in flight never exceeds what a
directory transfer already issues, so this does not make throttling more likely
than the transfers you run today.

Files below 64 MiB are never split: a second request would cost more than the
round trip it saves.

### Turning it off

Every range is a separate request, so eight ranges is eight times the read
transactions for that file. If your bill or your provider quota prefers fewer,
larger requests, turn it down or off:

```python
fs.download("/media/movie.mkv", sink, ranges=1)   # library: one stream
```

```bash
STORIX_MAX_TRANSFER_RANGES=1 sx pull /media/movie.mkv   # sx: one stream
export STORIX_MAX_TRANSFER_RANGES=2                     # or a lower ceiling
```

`STORIX_MAX_TRANSFER_RANGES` caps every file `sx` transfers; `1` restores the
pre-0.4.10 behavior exactly. Two more things also keep a transfer on one
stream, with identical output either way: a backend that does not advertise
`ranged_reads`, and a sink that cannot be written at an offset (a `BytesIO`, a
pipe, a socket).

## Current limits

- **The fan-out is fixed at 32.** It is a constant today, not a setting. It is
  the ceiling both file-level and range-level parallelism share.
- **Uploads are one connection per file.** The symmetric case, parallel
  multi-part uploads, is not implemented; `push` is not currently the
  bottleneck. See ADR 0032.
