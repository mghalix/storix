from collections.abc import AsyncIterator

from storix._async._stream import chunked, collect


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
