"""Memory-backend specifics; shared behavior lives in test_backends.py."""

from collections.abc import AsyncIterator
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
    await backend.write(P(path), _astream(data), mode=mode, content_type=None)


def test_backendbase_is_abstract():
    with pytest.raises(TypeError):
        BackendBase()  # type: ignore[abstract]


def test_memory_satisfies_protocol():
    # the annotation is the test: type checkers verify structural conformance
    backend: StorageBackend = MemoryBackend()
    assert backend.capabilities.content_type is False


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
