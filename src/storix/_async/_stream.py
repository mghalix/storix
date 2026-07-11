"""Byte-stream helpers for the backends and core."""

from collections.abc import AsyncIterable, AsyncIterator, Buffer, Iterable, Iterator

from storix.constants import DEFAULT_WRITE_CHUNKSIZE
from storix.types import AsyncDataBuffer, DataBuffer


async def collect(stream: AsyncIterator[bytes]) -> bytes:
    """Drain a chunk stream into a single bytes object."""
    return b''.join([chunk async for chunk in stream])


def chunked(data: Buffer, size: int = DEFAULT_WRITE_CHUNKSIZE) -> Iterator[bytes]:
    """Slice any buffer into ``bytes`` chunks with a single copy per chunk.

    The ``memoryview`` makes slicing zero-copy regardless of the input
    buffer type; ``bytes()`` performs the one copy consumers need.
    """
    view = memoryview(data)

    for i in range(0, len(view), size):
        yield bytes(view[i : i + size])


def _as_bytes(chunk: object) -> bytes:
    """Convert a single produced item into bytes (str encodes as UTF-8)."""
    if isinstance(chunk, str):
        return chunk.encode()
    if isinstance(chunk, Buffer):
        return bytes(chunk)
    msg = f'cannot convert a {type(chunk).__name__} chunk to bytes'
    raise TypeError(msg)


def iter_chunks(data: DataBuffer[str] | DataBuffer[bytes]) -> Iterator[bytes]:
    """Normalize any synchronous data source into a bytes-chunk iterator.

    Accepts scalars (str/bytes/any buffer), readable file-like objects,
    and iterables of either.
    """
    if isinstance(data, (str, Buffer)):
        yield from chunked(_as_bytes(data))
        return

    read = getattr(data, 'read', None)
    if callable(read):
        while chunk := read(DEFAULT_WRITE_CHUNKSIZE):
            yield _as_bytes(chunk)
        return

    if isinstance(data, Iterable):
        for item in data:
            yield _as_bytes(item)
        return

    msg = f'unsupported data source: {type(data).__name__}'
    raise TypeError(msg)


async def ensure_chunks(
    data: AsyncDataBuffer[str] | AsyncDataBuffer[bytes],
) -> AsyncIterator[bytes]:
    """Normalize any supported data source into the port's chunk stream.

    The scalar check must run first: str and bytes are themselves
    iterable (per character / per int), and must never be treated as
    streams of items.
    """
    if isinstance(data, (str, Buffer)):
        for chunk in chunked(_as_bytes(data)):
            yield chunk
        return

    if isinstance(data, AsyncIterable):
        async for item in data:
            yield _as_bytes(item)
        return

    for chunk in iter_chunks(data):
        yield chunk
