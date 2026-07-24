import io

from collections.abc import AsyncIterator

import pytest

from storix._async._stream import (
    batch_chunks,
    chunked,
    collect,
    ensure_chunks,
    iter_chunks,
    resolve_chunk_size,
    split_chunks,
    validate_chunk_size,
)


async def _astream(*chunks: bytes) -> AsyncIterator[bytes]:
    for chunk in chunks:
        yield chunk


async def test_collect_joins_chunks():
    assert await collect(_astream(b'hello ', b'world')) == b'hello world'


async def test_collect_empty_stream():
    assert await collect(_astream()) == b''


async def test_split_chunks_splits_large_upstream_chunks():
    out = [c async for c in split_chunks(_astream(b'0123456789'), size=4)]
    assert out == [b'0123', b'4567', b'89']


async def test_split_chunks_preserves_smaller_upstream_boundaries():
    first = b'a'
    second = b'bc'
    out = [c async for c in split_chunks(_astream(first, second), size=4)]
    assert out == [b'a', b'bc']
    assert out[0] is first
    assert out[1] is second


async def test_split_chunks_skips_empty_chunks():
    out = [c async for c in split_chunks(_astream(b'', b'a', b''), size=4)]
    assert out == [b'a']


@pytest.mark.parametrize('size', [0, -1])
async def test_split_chunks_rejects_non_positive_size(size: int):
    with pytest.raises(ValueError, match='chunk_size must be positive'):
        [c async for c in split_chunks(_astream(b'a'), size=size)]


async def test_batch_chunks_coalesces_small_upstream_chunks():
    out = [
        c async for c in batch_chunks(_astream(b'a', b'b', b'c', b'd', b'e'), size=2)
    ]
    assert out == [b'ab', b'cd', b'e']


async def test_batch_chunks_splits_oversized_chunks():
    out = [c async for c in batch_chunks(_astream(b'0123456789'), size=4)]
    assert out == [b'0123', b'4567', b'89']


async def test_batch_chunks_handles_boundaries_across_source_chunks():
    out = [c async for c in batch_chunks(_astream(b'abc', b'defgh'), size=4)]
    assert out == [b'abcd', b'efgh']


async def test_batch_chunks_passes_exact_bytes_without_copying():
    chunk = b'abcd'
    out = [c async for c in batch_chunks(_astream(chunk), size=4)]
    assert out == [chunk]
    assert out[0] is chunk


async def test_batch_chunks_skips_empty_chunks():
    out = [c async for c in batch_chunks(_astream(b'', b'a', b''), size=4)]
    assert out == [b'a']


@pytest.mark.parametrize('size', [0, -1])
async def test_batch_chunks_rejects_non_positive_size(size: int):
    with pytest.raises(ValueError, match='chunk_size must be positive'):
        [c async for c in batch_chunks(_astream(b'a'), size=size)]


@pytest.mark.parametrize('size', [0, -1])
def test_validate_chunk_size_rejects_non_positive_size(size: int):
    with pytest.raises(ValueError, match='chunk_size must be positive'):
        validate_chunk_size(size)


def test_resolve_chunk_size_uses_default_only_for_none():
    assert resolve_chunk_size(None, 8) == 8
    assert resolve_chunk_size(4, 8) == 4


def test_chunked_exact_division():
    assert list(chunked(b'abcdef', size=2)) == [b'ab', b'cd', b'ef']


def test_chunked_remainder():
    assert list(chunked(b'abcde', size=2)) == [b'ab', b'cd', b'e']


def test_chunked_empty():
    assert list(chunked(b'', size=2)) == []


@pytest.mark.parametrize('size', [0, -1])
def test_chunked_rejects_non_positive_size(size: int):
    with pytest.raises(ValueError, match='chunk_size must be positive'):
        list(chunked(b'a', size=size))


def test_chunked_accepts_bytearray_and_yields_bytes():
    chunks = list(chunked(bytearray(b'abcd'), size=3))
    assert chunks == [b'abc', b'd']
    assert all(type(c) is bytes for c in chunks)


def test_chunked_accepts_memoryview():
    assert list(chunked(memoryview(b'abcd'), size=2)) == [b'ab', b'cd']


async def _drain(data) -> bytes:
    return b''.join([chunk async for chunk in ensure_chunks(data)])


async def test_ensure_chunks_scalars():
    assert await _drain(b'raw bytes') == b'raw bytes'
    assert await _drain('text encodes') == b'text encodes'
    assert await _drain(bytearray(b'buffer')) == b'buffer'


async def test_ensure_chunks_keeps_scalar_as_one_source_chunk():
    data = b'x' * 10
    assert [chunk async for chunk in ensure_chunks(data)] == [data]


async def test_ensure_chunks_iterable_of_mixed_chunks():
    assert await _drain([b'a', 'b', b'c']) == b'abc'


async def test_ensure_chunks_file_like():
    assert await _drain(io.BytesIO(b'from a file')) == b'from a file'


async def test_ensure_chunks_reads_binary_file_by_size_not_by_line():
    """A file object is iterable by line; bytes must not be pulled that way."""
    payload = b'no newline here' + b'\n' + b'x' * 4096

    sizes = [len(chunk) async for chunk in ensure_chunks(io.BytesIO(payload))]

    assert sizes == [len(payload)]


async def test_ensure_chunks_keeps_iterating_a_body_style_reader():
    """A no-argument read() (httpx-style) must not be called with a size."""

    class BodyReader:
        def __init__(self, body: bytes) -> None:
            self._body = body

        def read(self) -> bytes:
            return self._body

        def __iter__(self):
            yield self._body

    assert await _drain(BodyReader(b'whole body')) == b'whole body'


async def test_ensure_chunks_async_iterable():
    async def agen() -> AsyncIterator[bytes]:
        yield b'async '
        yield b'chunks'

    assert await _drain(agen()) == b'async chunks'


async def test_ensure_chunks_rejects_unsupported_items():
    with pytest.raises(TypeError):
        await _drain([1, 2, 3])


def test_iter_chunks_reads_file_like_in_chunks():
    assert list(iter_chunks(io.BytesIO(b'x' * 10), read_size=4)) == [
        b'x' * 4,
        b'x' * 4,
        b'x' * 2,
    ]


def test_iter_chunks_keeps_scalar_as_one_source_chunk():
    data = b'x' * 10
    assert list(iter_chunks(data, read_size=4)) == [data]


@pytest.mark.parametrize('size', [0, -1])
def test_iter_chunks_rejects_non_positive_read_size(size: int):
    with pytest.raises(ValueError, match='chunk_size must be positive'):
        list(iter_chunks(io.BytesIO(b'x'), read_size=size))
