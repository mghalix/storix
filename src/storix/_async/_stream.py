"""Byte-stream helpers for the backends and core."""

from collections.abc import AsyncIterator, Buffer, Iterator

from storix.constants import DEFAULT_WRITE_CHUNKSIZE


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
