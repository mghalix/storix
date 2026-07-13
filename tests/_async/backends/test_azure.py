"""Azure-backend specifics that need no credentials.

Behavioral coverage lives in the conformance suite (test_backends.py),
where the azure param is integration-marked and runs against a real
HNS-enabled account.
"""

from collections.abc import AsyncIterator, Mapping
from pathlib import PurePosixPath as P

import pytest

from azure.core.exceptions import (
    ClientAuthenticationError,
    HttpResponseError,
    ResourceExistsError,
    ResourceNotFoundError,
)

from storix._async.backends.azure import _HNS_HINT, AzureBackend, _translate
from storix.errors import (
    AlreadyExistsError,
    DirectoryNotEmptyError,
    PathNotFoundError,
    PermissionDeniedError,
    StorageError,
)
from storix.models import RawStat
from storix.utils.time import utcnow


PATH = P('/docs/a.txt')


def test_key_strips_the_port_anchor():
    assert AzureBackend._key(P('/docs/a.txt')) == 'docs/a.txt'
    assert AzureBackend._key(P('/')) == ''


def test_translate_not_found():
    err = _translate(ResourceNotFoundError(message='gone'), PATH)
    assert isinstance(err, PathNotFoundError)
    assert str(err.path) == str(PATH)


def test_translate_exists():
    err = _translate(ResourceExistsError(message='x'), PATH)
    assert isinstance(err, AlreadyExistsError)


def test_translate_auth():
    err = _translate(ClientAuthenticationError(message='denied'), PATH)
    assert isinstance(err, PermissionDeniedError)


def test_translate_error_code_beats_exception_type():
    exc = ResourceExistsError(message='conflict')
    exc.error_code = 'DirectoryNotEmpty'
    assert isinstance(_translate(exc, PATH), DirectoryNotEmptyError)


def test_translate_unknown_http_error_hints_at_hns():
    err = _translate(HttpResponseError(message='mystery failure'), PATH)
    assert isinstance(err, StorageError)
    assert _HNS_HINT in str(err)


def test_capabilities_advertise_content_type():
    assert AzureBackend.capabilities.content_type is True


async def _astream(*chunks: bytes) -> AsyncIterator[bytes]:
    for chunk in chunks:
        yield chunk


async def test_read_stream_splits_without_coalescing_provider_chunks(
    monkeypatch: pytest.MonkeyPatch,
):
    class Download:
        async def chunks(self) -> AsyncIterator[bytes]:
            yield b'ab'
            yield b'cdefgh'

    class FileClient:
        async def download_file(self) -> Download:
            return Download()

    class Filesystem:
        def get_file_client(self, key: str) -> FileClient:
            assert key == 'docs/a.txt'
            return FileClient()

    async def stat(path: P) -> RawStat:
        now = utcnow()
        return RawStat(kind='file', size=8, created=now, modified=now)

    backend = AzureBackend('raw', account_name='acct', credential='token')
    monkeypatch.setattr(backend, 'stat', stat)
    monkeypatch.setattr(backend, '_filesystem', Filesystem())

    chunks = [chunk async for chunk in backend.read_stream(PATH, chunk_size=4)]

    assert chunks == [b'ab', b'cdef', b'gh']


async def test_write_stream_batches_tiny_yields_into_append_requests(
    monkeypatch: pytest.MonkeyPatch,
):
    class FileClient:
        def __init__(self) -> None:
            self.created = False
            self.appends: list[tuple[bytes, int, int]] = []
            self.flushed_at: int | None = None

        async def create_file(self, *, metadata: Mapping[str, str] | None) -> None:
            assert metadata is None
            self.created = True

        async def append_data(self, chunk: bytes, *, offset: int, length: int) -> None:
            self.appends.append((chunk, offset, length))

        async def flush_data(
            self, offset: int, *, content_settings: object | None = None
        ) -> None:
            assert content_settings is None
            self.flushed_at = offset

    client = FileClient()

    class Filesystem:
        def get_file_client(self, key: str) -> FileClient:
            assert key == 'docs/a.txt'
            return client

    async def stat(path: P) -> RawStat:
        raise PathNotFoundError(path)

    backend = AzureBackend('raw', account_name='acct', credential='token')
    monkeypatch.setattr(backend, 'stat', stat)
    monkeypatch.setattr(backend, '_filesystem', Filesystem())

    await backend.write_stream(
        PATH,
        _astream(b'a', b'b', b'cd', b'efghi'),
        chunk_size=4,
        mode='w',
        content_type=None,
    )

    assert client.created
    assert client.appends == [
        (b'abcd', 0, 4),
        (b'efgh', 4, 4),
        (b'i', 8, 1),
    ]
    assert client.flushed_at == 9
