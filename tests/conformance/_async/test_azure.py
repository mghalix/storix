"""Azure-backend specifics that need no credentials.

Behavioral coverage lives in the conformance suite (test_backends.py),
where the azure param is integration-marked and runs against a real
HNS-enabled account.
"""

from collections.abc import AsyncIterator, Mapping
from pathlib import PurePosixPath as P

import pytest

from azure.core import MatchConditions
from azure.core.exceptions import (
    AzureError,
    ClientAuthenticationError,
    HttpResponseError,
    ResourceExistsError,
    ResourceModifiedError,
    ResourceNotFoundError,
)
from azure.storage.filedatalake import FileProperties

from storix._async.backends.azure import _HNS_HINT, AzureBackend, _translate
from storix.enums import PathKind
from storix.errors import (
    AlreadyExistsError,
    ConfigurationError,
    DirectoryNotEmptyError,
    PathNotFoundError,
    PermissionDeniedError,
    PreconditionFailedError,
    StorageError,
    UnsupportedOperationError,
)
from storix.models import Capabilities, RawStat
from storix.preconditions import IF_MATCH_ABSENT
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


def test_translate_authentication_failure_as_configuration_error():
    err = _translate(ClientAuthenticationError(message='denied'), PATH)
    assert isinstance(err, ConfigurationError)
    assert 'account_name' in str(err)
    assert 'credential' in str(err)


def test_translate_server_authentication_failure_as_configuration_error():
    exc = HttpResponseError(message='invalid credential')
    exc.error_code = 'AuthenticationFailed'
    assert isinstance(_translate(exc, PATH), ConfigurationError)


def test_translate_authorization_failure_as_permission_denied():
    exc = HttpResponseError(message='not allowed')
    exc.error_code = 'AuthorizationPermissionMismatch'
    assert isinstance(_translate(exc, PATH), PermissionDeniedError)


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


async def test_provision_creates_filesystem_returns_true(
    monkeypatch: pytest.MonkeyPatch,
):
    # Given an ADLS backend whose filesystem does not yet exist
    class Filesystem:
        def __init__(self) -> None:
            self.created = False

        async def create_file_system(self) -> None:
            self.created = True

    filesystem = Filesystem()
    backend = AzureBackend('raw', account_name='acct', credential='token')
    monkeypatch.setattr(backend, '_filesystem', filesystem)

    # When provision runs
    created = await backend.provision()

    # Then it creates the filesystem and reports it new
    assert created is True
    assert filesystem.created


async def test_provision_existing_filesystem_returns_false(
    monkeypatch: pytest.MonkeyPatch,
):
    # Given an ADLS backend whose filesystem already exists (or a lost race)
    class Filesystem:
        async def create_file_system(self) -> None:
            raise ResourceExistsError(message='filesystem exists')

    backend = AzureBackend('raw', account_name='acct', credential='token')
    monkeypatch.setattr(backend, '_filesystem', Filesystem())

    # When provision runs, the race-safe create surfaces already-present
    created = await backend.provision()

    # Then it reports the root already existed, not a failure
    assert created is False


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


class _RecordingFileClient:
    """dfs file client stub that remembers the keywords each request carried.

    Narrow on purpose: it reimplements nothing the SDK does, so the
    assertions are about the requests the backend issues and about which
    request carries a precondition.
    """

    def __init__(self, create_error: AzureError | None = None) -> None:
        """Record requests, optionally failing the create.

        Args:
            create_error: SDK failure the create should raise, if any.
        """
        self.create_kwargs: dict[str, object] | None = None
        self.flush_kwargs: dict[str, object] | None = None
        self._create_error = create_error

    async def create_file(self, **kwargs: object) -> None:
        self.create_kwargs = kwargs
        if self._create_error is not None:
            raise self._create_error

    async def append_data(self, chunk: bytes, **kwargs: object) -> None:
        assert chunk

    async def flush_data(self, offset: int, **kwargs: object) -> None:
        self.flush_kwargs = {'offset': offset, **kwargs}


def _file_stat() -> RawStat:
    """A RawStat standing for a file already occupying the target path."""
    now = utcnow()
    return RawStat(kind=PathKind.FILE, size=3, created=now, modified=now)


def _backend_over(
    monkeypatch: pytest.MonkeyPatch,
    client: _RecordingFileClient,
    *,
    existing: RawStat | None = None,
) -> AzureBackend:
    """An ADLS backend driving the recording client instead of an account.

    Args:
        monkeypatch: The patcher installing the stubs.
        client: The recording file client the write should drive.
        existing: What ``stat`` reports at the target path, or ``None`` for
            a path nothing occupies yet.
    """

    class Filesystem:
        def get_file_client(self, key: str) -> _RecordingFileClient:
            assert key == 'docs/a.txt'
            return client

    async def stat(path: P) -> RawStat:
        if existing is None:
            raise PathNotFoundError(path)
        return existing

    backend = AzureBackend('raw', account_name='acct', credential='token')
    monkeypatch.setattr(backend, 'stat', stat)
    monkeypatch.setattr(backend, '_filesystem', Filesystem())
    return backend


def test_capabilities_advertise_both_precondition_forms():
    """Given the dfs create takes both conditions, then both are advertised."""
    assert AzureBackend.capabilities.conditional_writes is True
    assert AzureBackend.capabilities.exclusive_create is True


async def test_stat_reports_the_response_etag_as_the_version(
    monkeypatch: pytest.MonkeyPatch,
):
    """Given a properties response, when stat runs, then its ETag is the version.

    Assembled from the raw header names the SDK model reads, which is what
    shows the validator riding the response ``stat`` already parses rather
    than a second request.
    """
    now = utcnow()
    props = FileProperties(
        **{
            'ETag': '"0xABC"',
            'Last-Modified': now,
            'x-ms-creation-time': now,
            'Content-Length': 3,
            'metadata': {},
        }
    )

    class FileClient:
        async def get_file_properties(self) -> FileProperties:
            return props

    class Filesystem:
        def get_file_client(self, key: str) -> FileClient:
            assert key == 'docs/a.txt'
            return FileClient()

    backend = AzureBackend('raw', account_name='acct', credential='token')
    monkeypatch.setattr(backend, '_filesystem', Filesystem())

    raw = await backend.stat(PATH)

    assert raw.version == '"0xABC"'


async def test_a_version_precondition_rides_on_the_create(
    monkeypatch: pytest.MonkeyPatch,
):
    """Given a version, when writing, then the create carries If-Match for it.

    The create is the request that truncates an occupied path, so gating
    that one is what keeps a lost race from destroying stored content, and
    the flush stays unconditional.
    """
    client = _RecordingFileClient()
    backend = _backend_over(monkeypatch, client, existing=_file_stat())

    await backend.write_stream(
        PATH, _astream(b'new'), mode='w', content_type=None, if_match='"0xOLD"'
    )

    assert client.create_kwargs == {
        'metadata': None,
        'etag': '"0xOLD"',
        'match_condition': MatchConditions.IfNotModified,
    }
    assert client.flush_kwargs == {'offset': 3, 'content_settings': None}


async def test_an_exclusive_create_rides_on_the_create(
    monkeypatch: pytest.MonkeyPatch,
):
    """Given IF_MATCH_ABSENT, when writing, then the create sends If-None-Match."""
    client = _RecordingFileClient()
    backend = _backend_over(monkeypatch, client)

    await backend.write_stream(
        PATH, _astream(b'mine'), mode='w', content_type=None, if_match=IF_MATCH_ABSENT
    )

    assert client.create_kwargs == {
        'metadata': None,
        'match_condition': MatchConditions.IfMissing,
    }


async def test_an_unconditional_write_sends_no_condition(
    monkeypatch: pytest.MonkeyPatch,
):
    """Given no precondition, when writing, then the create is exactly as before.

    The default has to issue the requests it always has, so no existing
    write pays for the feature.
    """
    client = _RecordingFileClient()
    backend = _backend_over(monkeypatch, client, existing=_file_stat())

    await backend.write_stream(PATH, _astream(b'plain'), mode='w', content_type=None)

    assert client.create_kwargs == {'metadata': None}


async def test_a_stale_version_becomes_a_precondition_failure(
    monkeypatch: pytest.MonkeyPatch,
):
    """Given the service refuses If-Match, when writing, then storix reports it."""
    client = _RecordingFileClient(ResourceModifiedError(message='ConditionNotMet'))
    backend = _backend_over(monkeypatch, client, existing=_file_stat())

    with pytest.raises(PreconditionFailedError):
        await backend.write_stream(
            PATH, _astream(b'lost'), mode='w', content_type=None, if_match='"0xOLD"'
        )


async def test_a_lost_exclusive_create_becomes_a_precondition_failure(
    monkeypatch: pytest.MonkeyPatch,
):
    """Given an occupied path, when creating exclusively, then storix reports it.

    ``If-None-Match: *`` loses as an already-exists, which under a
    precondition means the precondition failed rather than that the caller
    asked to create the same path twice.
    """
    client = _RecordingFileClient(ResourceExistsError(message='PathAlreadyExists'))
    backend = _backend_over(monkeypatch, client)

    with pytest.raises(PreconditionFailedError):
        await backend.write_stream(
            PATH,
            _astream(b'second'),
            mode='w',
            content_type=None,
            if_match=IF_MATCH_ABSENT,
        )


async def test_a_bare_412_becomes_a_precondition_failure(
    monkeypatch: pytest.MonkeyPatch,
):
    """Given a 412 carrying no known code, when a condition was sent, then it loses."""
    failure = HttpResponseError(message='precondition failed')
    failure.status_code = 412
    backend = _backend_over(
        monkeypatch, _RecordingFileClient(failure), existing=_file_stat()
    )

    with pytest.raises(PreconditionFailedError):
        await backend.write_stream(
            PATH, _astream(b'lost'), mode='w', content_type=None, if_match='"0xOLD"'
        )


async def test_an_unconditional_collision_stays_already_exists(
    monkeypatch: pytest.MonkeyPatch,
):
    """Given no precondition, when the create collides, then it is not a 412.

    The precondition translation is gated on one having been sent, so
    ordinary failures keep their established meaning.
    """
    client = _RecordingFileClient(ResourceExistsError(message='PathAlreadyExists'))
    backend = _backend_over(monkeypatch, client)

    with pytest.raises(AlreadyExistsError):
        await backend.write_stream(PATH, _astream(b'x'), mode='w', content_type=None)


async def test_a_precondition_is_refused_on_append(monkeypatch: pytest.MonkeyPatch):
    """Given mode='a', when a precondition accompanies it, then nothing is sent."""
    client = _RecordingFileClient()
    backend = _backend_over(monkeypatch, client, existing=_file_stat())

    with pytest.raises(ValueError, match='if_match'):
        await backend.write_stream(
            PATH,
            _astream(b'more'),
            mode='a',
            content_type=None,
            if_match=IF_MATCH_ABSENT,
        )

    assert client.create_kwargs is None


async def test_the_capability_gate_refuses_an_unadvertised_form(
    monkeypatch: pytest.MonkeyPatch,
):
    """Given a backend advertising neither form, when one is asked, then it raises.

    Shows the shared gate reading the instance's own capabilities rather
    than being short-circuited by how the precondition is wired.
    """
    client = _RecordingFileClient()
    backend = _backend_over(monkeypatch, client, existing=_file_stat())
    monkeypatch.setattr(backend, 'capabilities', Capabilities())

    with pytest.raises(UnsupportedOperationError, match='conditional_writes'):
        await backend.write_stream(
            PATH, _astream(b'x'), mode='w', content_type=None, if_match='"0xOLD"'
        )

    assert client.create_kwargs is None
