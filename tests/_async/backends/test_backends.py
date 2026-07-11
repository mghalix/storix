# ruff: noqa: A004
"""The backend conformance suite: one behavior spec, every backend.

Every StorageBackend implementation must pass every test here - this is
the enforcement mechanism for 'one behavior everywhere'. Backend-specific
quirks live in the per-backend test files.
"""

import os
import uuid

from collections.abc import AsyncIterator
from pathlib import Path, PurePosixPath as P

import pytest

from storix._async.backends import StorageBackend
from storix._async.backends.local import LocalBackend
from storix._async.backends.memory import MemoryBackend
from storix._async.layers import SandboxLayer
from storix.errors import (
    AlreadyExistsError,
    DirectoryNotEmptyError,
    IsADirectoryError,
    NotADirectoryError,
    PathNotFoundError,
    UnsupportedOperationError,
)
from storix.types import EchoMode


@pytest.fixture(
    params=[
        'memory',
        'local',
        'sandbox',
        pytest.param('azure', marks=pytest.mark.integration),
    ]
)
async def backend(
    request: pytest.FixtureRequest, tmp_path: Path
) -> AsyncIterator[StorageBackend]:
    if request.param == 'memory':
        yield MemoryBackend()
        return
    if request.param == 'local':
        yield LocalBackend(tmp_path)
        return
    if request.param == 'sandbox':
        # a layer must satisfy the full port contract like any backend
        inner = MemoryBackend()
        await inner.make_dir(P('/jail'), parents=False)
        yield SandboxLayer(inner, root='/jail')
        return

    account = os.environ.get('ADLSG2_ACCOUNT_NAME')
    token = os.environ.get('ADLSG2_TOKEN')
    if not (account and token):
        pytest.skip('azure integration credentials not configured')
    from storix._async.backends.azure import AzureBackend

    azure = AzureBackend(
        f'storix-conformance-{uuid.uuid4().hex[:12]}',
        account_name=account,
        credential=token,
    )
    await azure._filesystem.create_file_system()
    try:
        yield azure
    finally:
        await azure._filesystem.delete_file_system()
        await azure.close()


async def _astream(*chunks: bytes) -> AsyncIterator[bytes]:
    for chunk in chunks:
        yield chunk


async def put(
    backend: StorageBackend, path: str, data: bytes = b'', mode: EchoMode = 'w'
) -> None:
    await backend.write(P(path), _astream(data), mode=mode, content_type=None)


async def test_root_exists_initially(backend: StorageBackend):
    assert await backend.exists(P('/'))
    assert not await backend.exists(P('/anything'))


# --- write / read ---


async def test_write_creates_and_read_round_trips(backend: StorageBackend):
    await put(backend, '/a.txt', b'hello')
    assert await backend.read(P('/a.txt')) == b'hello'


async def test_write_truncates_existing(backend: StorageBackend):
    await put(backend, '/a.txt', b'old content')
    await put(backend, '/a.txt', b'new')
    assert await backend.read(P('/a.txt')) == b'new'


async def test_append_extends(backend: StorageBackend):
    await put(backend, '/a.txt', b'hello ')
    await put(backend, '/a.txt', b'world', mode='a')
    assert await backend.read(P('/a.txt')) == b'hello world'


async def test_append_creates_missing(backend: StorageBackend):
    await put(backend, '/a.txt', b'created', mode='a')
    assert await backend.read(P('/a.txt')) == b'created'


@pytest.mark.parametrize('mode', ['w', 'a'])
async def test_write_onto_directory_raises(backend: StorageBackend, mode: EchoMode):
    await backend.make_dir(P('/d'), parents=False)
    with pytest.raises(IsADirectoryError):
        await put(backend, '/d', b'x', mode=mode)


async def test_read_missing_raises(backend: StorageBackend):
    with pytest.raises(PathNotFoundError):
        await backend.read(P('/nope'))


async def test_read_directory_raises(backend: StorageBackend):
    await backend.make_dir(P('/d'), parents=False)
    with pytest.raises(IsADirectoryError):
        await backend.read(P('/d'))


async def test_read_stream_yields_content(backend: StorageBackend):
    await put(backend, '/a.txt', b'streamed')
    chunks = [chunk async for chunk in backend.read_stream(P('/a.txt'))]
    assert b''.join(chunks) == b'streamed'


# --- list_dir ---


async def test_list_dir_entries(backend: StorageBackend):
    await backend.make_dir(P('/d'), parents=False)
    await backend.make_dir(P('/d/sub'), parents=False)
    await put(backend, '/d/a.txt', b'12345')

    entries = {(e.name, e.is_dir, e.size) async for e in backend.list_dir(P('/d'))}
    # directory entries report size=None: a listing size is only meaningful
    # for files, and du() recurses into directories regardless
    assert entries == {('sub', True, None), ('a.txt', False, 5)}


async def test_list_dir_on_file_raises(backend: StorageBackend):
    await put(backend, '/a.txt')
    with pytest.raises(NotADirectoryError):
        async for _ in backend.list_dir(P('/a.txt')):
            pass


async def test_list_dir_missing_raises(backend: StorageBackend):
    with pytest.raises(PathNotFoundError):
        async for _ in backend.list_dir(P('/nope')):
            pass


async def test_list_dir_tolerates_delete_during_iteration(backend: StorageBackend):
    await backend.make_dir(P('/d'), parents=False)
    for name in ('a', 'b', 'c'):
        await put(backend, f'/d/{name}')

    async for entry in backend.list_dir(P('/d')):
        await backend.delete(P('/d') / entry.name)

    assert [e async for e in backend.list_dir(P('/d'))] == []


# --- stat ---


async def test_stat_file(backend: StorageBackend):
    await put(backend, '/a.txt', b'12345')
    props = await backend.stat(P('/a.txt'))
    assert props.kind == 'file'
    assert props.size == 5
    assert props.created.tzinfo is not None
    assert props.modified.tzinfo is not None


async def test_stat_directory_size_is_zero(backend: StorageBackend):
    await backend.make_dir(P('/d'), parents=False)
    await put(backend, '/d/a.txt', b'12345')
    props = await backend.stat(P('/d'))
    assert props.kind == 'directory'
    assert props.size == 0


async def test_metadata_round_trip(backend: StorageBackend):
    if not backend.capabilities.custom_metadata:
        pytest.skip('backend does not advertise custom_metadata')
    await backend.write(
        P('/m.txt'),
        _astream(b'x'),
        mode='w',
        content_type=None,
        metadata={'owner': 'tests'},
    )
    raw = await backend.stat(P('/m.txt'))
    assert raw.metadata == {'owner': 'tests'}


async def test_metadata_absent_by_default(backend: StorageBackend):
    await put(backend, '/plain.txt', b'x')
    assert (await backend.stat(P('/plain.txt'))).metadata is None


async def test_metadata_replace_semantics(backend: StorageBackend):
    """Provided mapping replaces; None preserves on append; {} clears."""
    if not backend.capabilities.custom_metadata:
        pytest.skip('backend does not advertise custom_metadata')

    async def put_meta(data: bytes, mode: EchoMode, metadata: dict | None) -> None:
        await backend.write(
            P('/m.txt'), _astream(data), mode=mode, content_type=None, metadata=metadata
        )

    async def meta() -> dict | None:
        raw = await backend.stat(P('/m.txt'))
        return dict(raw.metadata) if raw.metadata is not None else None

    await put_meta(b'x', 'w', {'a': '1', 'b': '2'})
    await put_meta(b'y', 'a', None)  # None preserves on append
    assert await meta() == {'a': '1', 'b': '2'}

    await put_meta(b'z', 'a', {'c': '3'})  # replace, not merge
    assert await meta() == {'c': '3'}

    await put_meta(b'w', 'a', {})  # empty mapping clears
    assert await meta() is None


async def test_set_metadata_replaces_without_touching_content(
    backend: StorageBackend,
):
    if not backend.capabilities.custom_metadata:
        with pytest.raises(UnsupportedOperationError):
            await backend.set_metadata(P('/x'), {'a': '1'})
        return

    await put(backend, '/m.txt', b'content')
    await backend.set_metadata(P('/m.txt'), {'a': '1'})
    assert (await backend.stat(P('/m.txt'))).metadata == {'a': '1'}
    assert await backend.read(P('/m.txt')) == b'content'

    await backend.set_metadata(P('/m.txt'), {})  # empty mapping clears
    assert (await backend.stat(P('/m.txt'))).metadata is None


async def test_set_metadata_on_directory_raises(backend: StorageBackend):
    if not backend.capabilities.custom_metadata:
        pytest.skip('backend does not advertise custom_metadata')
    await backend.make_dir(P('/d'), parents=False)
    with pytest.raises(IsADirectoryError):
        await backend.set_metadata(P('/d'), {'a': '1'})


async def test_make_url_respects_capability(backend: StorageBackend):
    await put(backend, '/u.txt', b'x')
    if backend.capabilities.presigned_urls:
        url = await backend.make_url(P('/u.txt'), expires_in=60)
        assert url.startswith('https://')
    else:
        with pytest.raises(UnsupportedOperationError):
            await backend.make_url(P('/u.txt'), expires_in=60)


async def test_append_updates_modified(backend: StorageBackend):
    await put(backend, '/a.txt', b'x')
    before = await backend.stat(P('/a.txt'))
    await put(backend, '/a.txt', b'y', mode='a')
    after = await backend.stat(P('/a.txt'))
    assert after.modified >= before.modified


# --- make_dir ---


async def test_make_dir_plain(backend: StorageBackend):
    await backend.make_dir(P('/d'), parents=False)
    assert (await backend.stat(P('/d'))).kind == 'directory'


async def test_make_dir_missing_parent_raises(backend: StorageBackend):
    with pytest.raises(PathNotFoundError) as excinfo:
        await backend.make_dir(P('/missing/d'), parents=False)
    assert str(excinfo.value.path) == '/missing'


async def test_make_dir_parent_is_file_raises(backend: StorageBackend):
    await put(backend, '/a.txt')
    with pytest.raises(NotADirectoryError):
        await backend.make_dir(P('/a.txt/d'), parents=False)


async def test_make_dir_existing_raises(backend: StorageBackend):
    await backend.make_dir(P('/d'), parents=False)
    with pytest.raises(AlreadyExistsError):
        await backend.make_dir(P('/d'), parents=False)


async def test_make_dir_parents_creates_chain(backend: StorageBackend):
    await backend.make_dir(P('/a/b/c'), parents=True)
    for path in ('/a', '/a/b', '/a/b/c'):
        assert (await backend.stat(P(path))).kind == 'directory'


async def test_make_dir_parents_is_idempotent(backend: StorageBackend):
    await backend.make_dir(P('/d'), parents=True)
    await backend.make_dir(P('/d'), parents=True)  # no raise


async def test_make_dir_parents_existing_file_still_raises(backend: StorageBackend):
    await put(backend, '/a.txt')
    with pytest.raises(AlreadyExistsError):
        await backend.make_dir(P('/a.txt'), parents=True)


# --- delete ---


async def test_delete_file(backend: StorageBackend):
    await put(backend, '/a.txt')
    await backend.delete(P('/a.txt'))
    assert not await backend.exists(P('/a.txt'))


async def test_delete_empty_directory(backend: StorageBackend):
    await backend.make_dir(P('/d'), parents=False)
    await backend.delete(P('/d'))
    assert not await backend.exists(P('/d'))


async def test_delete_non_empty_directory_raises(backend: StorageBackend):
    await backend.make_dir(P('/d'), parents=False)
    await put(backend, '/d/a.txt')
    with pytest.raises(DirectoryNotEmptyError):
        await backend.delete(P('/d'))


async def test_delete_missing_raises(backend: StorageBackend):
    with pytest.raises(PathNotFoundError):
        await backend.delete(P('/nope'))


# --- generic fallbacks / native fast paths through the same contract ---


async def test_du_file(backend: StorageBackend):
    await put(backend, '/a.txt', b'12345')
    assert await backend.du(P('/a.txt')) == 5


async def test_du_sums_tree(backend: StorageBackend):
    await backend.make_dir(P('/a/b'), parents=True)
    await put(backend, '/a/f1', b'123')
    await put(backend, '/a/b/f2', b'12345')
    assert await backend.du(P('/a')) == 8
    assert await backend.du(P('/')) == 8


async def test_move_file(backend: StorageBackend):
    await put(backend, '/src.txt', b'payload')
    await backend.move(P('/src.txt'), P('/dst.txt'))
    assert await backend.read(P('/dst.txt')) == b'payload'
    assert not await backend.exists(P('/src.txt'))


async def test_move_directory_tree(backend: StorageBackend):
    await backend.make_dir(P('/d/sub'), parents=True)
    await put(backend, '/d/sub/a.txt', b'x')
    await backend.move(P('/d'), P('/renamed'))
    assert await backend.read(P('/renamed/sub/a.txt')) == b'x'
    assert not await backend.exists(P('/d'))


async def test_copy_file_is_independent(backend: StorageBackend):
    await put(backend, '/src.txt', b'payload')
    await backend.copy(P('/src.txt'), P('/dst.txt'))
    assert await backend.read(P('/dst.txt')) == b'payload'

    # mutating the copy must not touch the original (no buffer aliasing)
    await put(backend, '/dst.txt', b' more', mode='a')
    assert await backend.read(P('/src.txt')) == b'payload'


async def test_delete_tree_removes_everything(backend: StorageBackend):
    await backend.make_dir(P('/d/sub'), parents=True)
    await put(backend, '/d/a.txt', b'x')
    await put(backend, '/d/sub/b.txt', b'y')

    await backend.delete_tree(P('/d'))

    for path in ('/d', '/d/sub', '/d/a.txt', '/d/sub/b.txt'):
        assert not await backend.exists(P(path))
    assert await backend.exists(P('/'))
