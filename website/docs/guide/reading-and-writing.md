# Reading and writing

Storix is Python-first about data: you hand it whatever shape you already have,
and it never forces a large payload through memory just to move it.

## Writing with `echo`

`echo` is the one write verb. Its first argument accepts native Python:

```python
fs.echo(b"raw bytes", "/a.bin")          # bytes
fs.echo("some text", "/a.txt")           # str
fs.echo(memoryview(buf), "/a.bin")       # any Buffer (memoryview, bytearray, ...)
fs.echo(open("photo.jpg", "rb"), "/p.jpg")   # an open file object (IO)
fs.echo([b"one ", b"two ", b"three"], "/a.txt")  # an iterable of chunks
```

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
        yield f"row {i}\n".encode()

fs.echo(rows(), "/big.csv")   # written chunk by chunk
```

## Reading

`cat` reads the whole file into `bytes`. Use it when you know the file is small:

```python
data = fs.cat("/a.txt")       # bytes
text = fs.cat("/a.txt").decode()
```

`stream` reads the file back in chunks, so a large file never lands in memory
all at once:

```python
for chunk in fs.stream("/big.csv"):
    process(chunk)
```

## Copying a large file through bounded memory

`stream` returns an iterator and `echo` accepts one, so you can pipe a large file
from one path to another in chunks. Memory stays flat no matter the file size:

```python
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
    async for chunk in some_async_source():
        yield chunk

async with Storix(MemoryBackend()) as fs:
    await fs.echo(produce(), "/out.bin")        # async iterator in
    async for chunk in fs.stream("/out.bin"):   # stream back out
        process(chunk)
```

!!! tip "Rule of thumb"

    Reach for `cat`/plain `echo(bytes)` for small, known-size payloads. Reach for
    `stream`/`echo(iterator)` the moment a file could be large, and memory stays
    bounded either way.
