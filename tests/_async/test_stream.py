import io

from collections.abc import AsyncIterator

import pytest

from storix._async._stream import chunked, collect, ensure_chunks, iter_chunks


async def _astream(*chunks: bytes) -> AsyncIterator[bytes]:
    for chunk in chunks:
        yield chunk


async def test_collect_joins_chunks():
    assert await collect(_astream(b'hello ', b'world')) == b'hello world'


async def test_collect_empty_stream():
    assert await collect(_astream()) == b''


def test_chunked_exact_division():
    assert list(chunked(b'abcdef', size=2)) == [b'ab', b'cd', b'ef']


def test_chunked_remainder():
    assert list(chunked(b'abcde', size=2)) == [b'ab', b'cd', b'e']


def test_chunked_empty():
    assert list(chunked(b'', size=2)) == []


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


async def test_ensure_chunks_iterable_of_mixed_chunks():
    assert await _drain([b'a', 'b', b'c']) == b'abc'


async def test_ensure_chunks_file_like():
    assert await _drain(io.BytesIO(b'from a file')) == b'from a file'


async def test_ensure_chunks_async_iterable():
    async def agen() -> AsyncIterator[bytes]:
        yield b'async '
        yield b'chunks'

    assert await _drain(agen()) == b'async chunks'


async def test_ensure_chunks_rejects_unsupported_items():
    with pytest.raises(TypeError):
        await _drain([1, 2, 3])


def test_iter_chunks_reads_file_like_in_chunks():
    assert b''.join(iter_chunks(io.BytesIO(b'x' * 10))) == b'x' * 10
