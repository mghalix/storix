"""Memory-backend specifics; shared behavior lives in test_backends.py."""

from collections.abc import AsyncIterator, Mapping
from pathlib import PurePosixPath as P

import pytest

from storix._async.backends import BackendBase, StorageBackend
from storix._async.backends.memory import MemoryBackend
from storix.types import EchoMode


async def _astream(*chunks: bytes) -> AsyncIterator[bytes]:
    for chunk in chunks:
        yield chunk


async def put(
    backend: MemoryBackend, path: str, data: bytes = b'', mode: EchoMode = 'w'
) -> None:
    await backend.write_stream(P(path), _astream(data), mode=mode, content_type=None)


class WholeMemoryBackend(MemoryBackend):
    """Memory store exposing only whole-object I/O to exercise fallbacks."""

    read_stream = BackendBase.read_stream
    write_stream = BackendBase.write_stream

    def __init__(self) -> None:
        super().__init__()
        self.full_writes: list[bytes] = []

    async def read(self, path: P) -> bytes:
        return b''.join(
            [chunk async for chunk in MemoryBackend.read_stream(self, path)]
        )

    async def write(
        self,
        path: P,
        data: bytes,
        *,
        mode: EchoMode,
        content_type: str | None,
        metadata: Mapping[str, str] | None = None,
    ) -> None:
        self.full_writes.append(data)
        await MemoryBackend.write_stream(
            self,
            path,
            _astream(data),
            mode=mode,
            content_type=content_type,
            metadata=metadata,
        )


class MissingIOBackend(MemoryBackend):
    """Concrete structural backend with neither member of either I/O pair."""

    read = BackendBase.read
    read_stream = BackendBase.read_stream
    write = BackendBase.write
    write_stream = BackendBase.write_stream


def test_backendbase_is_abstract():
    with pytest.raises(TypeError):
        BackendBase()  # type: ignore[abstract]


def test_memory_satisfies_protocol():
    # the annotation is the test: type checkers verify structural conformance
    backend: StorageBackend = MemoryBackend()
    assert backend.capabilities.content_type is False


async def test_whole_object_backend_gets_bounded_read_stream_fallback():
    backend = WholeMemoryBackend()
    await backend.write(P('/a.txt'), b'abcdef', mode='w', content_type=None)

    chunks = [chunk async for chunk in backend.read_stream(P('/a.txt'), chunk_size=2)]

    assert chunks == [b'ab', b'cd', b'ef']


async def test_whole_object_backend_gets_single_write_fallback():
    backend = WholeMemoryBackend()

    await backend.write_stream(
        P('/a.txt'),
        _astream(b'a', b'b', b'c'),
        chunk_size=2,
        mode='w',
        content_type=None,
    )

    assert backend.full_writes == [b'abc']
    assert await backend.read(P('/a.txt')) == b'abc'


async def test_backend_without_either_read_form_fails_clearly():
    backend = MissingIOBackend()

    with pytest.raises(NotImplementedError, match=r'read\(\) or read_stream\(\)'):
        await backend.read(P('/a.txt'))
    with pytest.raises(NotImplementedError, match=r'read\(\) or read_stream\(\)'):
        [chunk async for chunk in backend.read_stream(P('/a.txt'))]


async def test_backend_without_either_write_form_fails_clearly():
    backend = MissingIOBackend()

    with pytest.raises(NotImplementedError, match=r'write\(\) or write_stream\(\)'):
        await backend.write(P('/a.txt'), b'x', mode='w', content_type=None)
    with pytest.raises(NotImplementedError, match=r'write\(\) or write_stream\(\)'):
        await backend.write_stream(
            P('/a.txt'), _astream(b'x'), mode='w', content_type=None
        )


async def test_append_updates_modified_preserves_created():
    """Memory-specific: POSIX ctime shifts on append, so only the memory
    backend can promise creation-time stability across appends.
    """
    backend = MemoryBackend()
    await put(backend, '/a.txt', b'x')
    before = await backend.stat(P('/a.txt'))
    await put(backend, '/a.txt', b'y', mode='a')
    after = await backend.stat(P('/a.txt'))
    assert after.created == before.created
    assert after.modified >= before.modified
