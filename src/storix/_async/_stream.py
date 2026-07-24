"""Byte-stream normalization, splitting, and batching helpers."""

import inspect

from collections.abc import (
    AsyncIterable,
    AsyncIterator,
    Buffer,
    Callable,
    Iterable,
    Iterator,
)
from io import BytesIO
from typing import TypeGuard, cast

from storix.constants import DEFAULT_SOURCE_READ_SIZE
from storix.types import AsyncDataBuffer, DataBuffer


async def collect(stream: AsyncIterator[bytes]) -> bytes:
    """Drain a chunk stream into a single bytes object."""
    return b''.join([chunk async for chunk in stream])


def validate_chunk_size(chunk_size: int | None) -> None:
    """Validate an optional public chunk-size argument.

    Args:
        chunk_size: Requested maximum chunk size, or ``None`` for a
            backend-selected default.

    Raises:
        ValueError: If ``chunk_size`` is zero or negative.
    """
    if chunk_size is not None and chunk_size <= 0:
        msg = 'chunk_size must be positive'
        raise ValueError(msg)


def resolve_chunk_size(chunk_size: int | None, default: int) -> int:
    """Resolve ``None`` to a backend default and validate the result.

    Args:
        chunk_size: Requested maximum chunk size, or ``None``.
        default: Backend-selected size used when ``chunk_size`` is ``None``.

    Returns:
        A positive chunk size.

    Raises:
        ValueError: If the requested or default size is zero or negative.
    """
    resolved = default if chunk_size is None else chunk_size
    validate_chunk_size(resolved)
    return resolved


async def split_chunks(stream: AsyncIterator[bytes], size: int) -> AsyncIterator[bytes]:
    """Yield source chunks no larger than ``size`` without coalescing.

    Existing chunks at or below the limit pass through without a copy.
    Oversized ``bytes`` are sliced in C, with one required allocation per
    output chunk. Smaller upstream boundaries remain observable.

    Args:
        stream: Source byte chunks.
        size: Maximum output chunk size.

    Raises:
        ValueError: If ``size`` is zero or negative.
    """
    validate_chunk_size(size)
    async for chunk in stream:
        if not chunk:
            continue
        if len(chunk) <= size:
            yield chunk
            continue
        for offset in range(0, len(chunk), size):
            yield chunk[offset : offset + size]


async def batch_chunks(stream: AsyncIterator[bytes], size: int) -> AsyncIterator[bytes]:
    """Split and coalesce source chunks into efficient write batches.

    Exact-sized immutable chunks pass through without copying. Oversized
    chunks use direct ``bytes`` slicing; only small fragments are buffered
    in ``BytesIO``. The algorithm is linear in the number of input bytes.

    Args:
        stream: Source byte chunks.
        size: Target write-batch size; the final batch may be shorter.

    Raises:
        ValueError: If ``size`` is zero or negative.
    """
    validate_chunk_size(size)
    pending = BytesIO()
    pending_size = 0

    async for chunk in stream:
        if not chunk:
            continue
        offset = 0

        if pending_size:
            needed = size - pending_size
            if len(chunk) < needed:
                pending.write(chunk)
                pending_size += len(chunk)
                continue
            pending.write(chunk if len(chunk) == needed else chunk[:needed])
            yield pending.getvalue()
            pending = BytesIO()
            pending_size = 0
            offset = needed

        remaining = len(chunk) - offset
        while remaining >= size:
            if offset == 0 and len(chunk) == size:
                yield chunk
            else:
                yield chunk[offset : offset + size]
            offset += size
            remaining -= size

        if remaining:
            pending.write(chunk[offset:])
            pending_size = remaining

    if pending_size:
        yield pending.getvalue()


def validate_span(offset: int, length: int) -> None:
    """Validate a byte range requested from a backend.

    Args:
        offset: First byte of the range, counted from the start of the file.
        length: Number of bytes requested.

    Raises:
        ValueError: If either bound is negative.
    """
    if offset < 0:
        msg = 'offset must not be negative'
        raise ValueError(msg)
    if length < 0:
        msg = 'length must not be negative'
        raise ValueError(msg)


async def span_of(
    stream: AsyncIterator[bytes], *, offset: int, length: int
) -> AsyncIterator[bytes]:
    """Yield only the bytes of ``stream`` inside ``[offset, offset + length)``.

    The portable way to serve a range from a backend that can only stream
    from the start: bytes before the range are pulled and discarded, and the
    stream is abandoned as soon as the range is complete. A range past the
    end of the stream simply ends early.

    Args:
        stream: Source chunks, from the start of the file.
        offset: First byte to yield.
        length: Maximum number of bytes to yield.
    """
    if length == 0:
        return
    seen = 0
    remaining = length
    async for chunk in stream:
        end = seen + len(chunk)
        if end <= offset:
            seen = end
            continue
        start = max(0, offset - seen)
        piece = chunk[start : start + remaining]
        seen = end
        remaining -= len(piece)
        if piece:
            yield piece
        if remaining <= 0:
            return


def chunked(data: Buffer, size: int) -> Iterator[bytes]:
    """Slice a buffer into ``bytes`` chunks with a single copy per chunk.

    The ``memoryview`` makes slicing zero-copy regardless of the input
    buffer type; ``bytes()`` performs the one copy consumers need.

    Args:
        data: Source buffer.
        size: Maximum output chunk size.

    Raises:
        ValueError: If ``size`` is zero or negative.
    """
    validate_chunk_size(size)
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


def _reads_by_size(read: object) -> TypeGuard[Callable[[int], object]]:
    """Whether ``read`` is a synchronous reader that takes a size argument.

    Every readable in the buffer union reads by size (``file.read(n)``), but
    some objects in the wild expose a no-argument ``read()`` that returns the
    whole body at once (``httpx.Response``) while also being iterable. Those
    must keep their iterable behavior rather than be called with a size they
    would reject.

    Args:
        read: Candidate ``read`` attribute of a data source.

    Returns:
        True when the attribute is callable, is not a coroutine function, and
        accepts at least one argument. A callable whose signature cannot be
        introspected (a C-level reader) counts as reading by size, which is
        what every such reader in the standard library does.
    """
    if not callable(read) or inspect.iscoroutinefunction(read):
        return False
    try:
        signature = inspect.signature(read)
    except (TypeError, ValueError):
        return True
    return bool(signature.parameters)


def iter_chunks(
    data: DataBuffer[str] | DataBuffer[bytes],
    *,
    read_size: int = DEFAULT_SOURCE_READ_SIZE,
) -> Iterator[bytes]:
    """Normalize any synchronous data source into a bytes-chunk iterator.

    Accepts scalars (str/bytes/any buffer), readable file-like objects,
    and iterables of either.
    """
    validate_chunk_size(read_size)
    if isinstance(data, (str, Buffer)):
        yield _as_bytes(data)
        return

    read = getattr(data, 'read', None)
    if _reads_by_size(read):
        while chunk := read(read_size):
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
    streams of items. A synchronous readable is pulled with ``read()``
    for the same reason: a binary file object is also iterable, but by
    newline-delimited lines, which for bytes is neither bounded (a file
    with no newline yields itself whole) nor efficient (a 19 GiB video
    yields ~250-byte chunks). The codegen turns the async-iterable branch
    below into a plain iterable one, so without this check the sync
    flavor would hand every file object to it.
    """
    if isinstance(data, (str, Buffer)):
        yield _as_bytes(data)
        return

    if _reads_by_size(getattr(data, 'read', None)):
        # a size-taking synchronous reader is the IO[...] arm of the
        # buffer union, whichever flavor is running
        for chunk in iter_chunks(cast('DataBuffer[str] | DataBuffer[bytes]', data)):
            yield chunk
        return

    if isinstance(data, AsyncIterable):
        async for item in data:
            yield _as_bytes(item)
        return

    for chunk in iter_chunks(data):
        yield chunk
