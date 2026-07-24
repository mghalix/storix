# Reading and writing

Storix is Python-first about data: you hand it whatever shape you already have,
and its streaming-native built-ins move large payloads through bounded memory.

The synchronous examples below use a disposable, zero-configuration memory
session:

```python
from storix import get_storage

fs = get_storage("memory")
```

## Writing with `echo`

`echo` is the one write verb. Its first argument accepts native Python:

```python
fs.echo(b"raw bytes", "/a.bin")          # bytes
fs.echo("some text", "/a.txt")           # str
buf = b"hello"
fs.echo(memoryview(buf), "/a.bin")       # any Buffer (memoryview, bytearray, ...)
with open("photo.jpg", "rb") as photo:
    fs.echo(photo, "/p.jpg")              # an open file object (IO)
fs.echo([b"one ", b"two ", b"three"], "/a.txt")  # an iterable of chunks
```

A scalar is one complete logical payload, like `Path.write_bytes()`. An iterable
is a lazy source. Both travel through the same streaming backend path: storix
splits oversized values and combines tiny iterator yields into efficient write
batches. Iterator boundaries are production details, not storage boundaries.

Append instead of overwrite with `mode="a"`:

```python
fs.echo("first line\n", "/log.txt")
fs.echo("second line\n", "/log.txt", mode="a")
```

### Streaming a write from a generator

Because `echo` accepts any iterable of chunks, a generator lets you produce a
large file lazily, one chunk at a time, without ever holding it all in memory:

```python
def rows():
    for i in range(1_000_000):
        yield f"row,{i}\n".encode()

fs.echo(rows(), "/big.csv")   # tiny rows are combined into backend-sized batches
```

Control the maximum target batch when needed:

```python
fs.echo(rows(), "/big.csv", chunk_size=4 * 1024 * 1024)
```

`chunk_size=None` (the default) lets the backend select a suitable batch size.
Zero and negative values raise `ValueError`; there is no special `-1` value.

## Reading

`cat` reads the whole file into `bytes`. Use it when you know the file is small:

```python
data = fs.cat("/a.txt")       # bytes
text = fs.cat("/a.txt").decode()
```

`stream` reads the file back in chunks. With a streaming-native backend, a large
file never lands in memory all at once:

```python
for chunk in fs.stream("/big.csv"):
    process(chunk)
```

`stream(..., chunk_size=N)` guarantees that no yielded chunk exceeds `N` bytes.
It splits larger provider chunks but does not combine smaller ones, so consumers
receive data promptly. Use `cat()` when you intentionally want one complete
`bytes` value.

```python
for chunk in fs.stream("/big.csv", chunk_size=64 * 1024):
    process(chunk)  # every chunk is at most 64 KiB
```

As with `echo`, `None` selects the backend default and non-positive values raise
`ValueError`.

## Copying a large file through bounded memory

`stream` returns an iterator and `echo` accepts one, so you can pipe a large file
from one path to another in chunks. With streaming-native backends, memory stays
bounded no matter the file size:

```python
fs.mkdir("/backup", parents=True)
fs.echo(fs.stream("/big.bin"), "/backup/big.bin")
```

This is the heart of the Python-first design: the same iterator protocol that
Python already uses for lazy sequences is how storix keeps I/O efficient.

## Async

Under `storix.aio` the same verbs are awaitable, and `echo` additionally accepts
an `AsyncIterator[bytes]`, so an async producer streams straight to storage:

```python
from storix.aio import Storix
from storix.aio.backends import MemoryBackend

async def produce():
    for i in range(10):
        yield f"row,{i}\n".encode()

async with Storix(MemoryBackend()) as fs:
    await fs.echo(produce(), "/out.bin")        # async iterator in
    async for chunk in fs.stream("/out.bin"):   # stream back out
        print(chunk.decode(), end="")
```

## Defaults and memory bounds

The public default is `None`, not one global size forced onto every provider.
The built-in defaults balance syscall/request overhead with bounded host memory:

| Backend | Read output | Write batch | Additional read buffer |
| --- | ---: | ---: | ---: |
| `BackendBase` whole-object fallback | 1 MiB | whole payload | full file |
| Local | 1 MiB | 1 MiB | none beyond active chunks |
| Memory | 1 MiB | not applicable (the file is already in memory) | the stored file |
| Azure ADLS Gen2 | 4 MiB | 4 MiB | up to 8 MiB initial SDK request |

Azure's SDK buffers live in your process even though the data is in the cloud.
Configure its provider-level limits with `read_chunk_size`,
`write_chunk_size`, and `read_prefetch_size` (or the matching
`STORIX_AZURE_*` variables). A per-call `stream(chunk_size=...)` controls the
consumer-facing maximum; it does not merge smaller SDK chunks or rebuild the
Azure client.

Streaming-native built-ins keep memory bounded. A custom whole-object backend
can implement only `read()` and `write()` and inherit compatibility stream
fallbacks, but those fallbacks necessarily materialize the whole file. Implement
`read_stream()` and/or `write_stream()` when the provider supports true bounded
streaming.

!!! tip "Rule of thumb"

    Reach for `cat`/plain `echo(bytes)` for small, known-size payloads. Reach for
    `stream`/`echo(iterator)` the moment a file could be large. For custom
    backends, bounded memory requires a native streaming method in that
    direction.
