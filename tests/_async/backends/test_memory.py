# ruff: noqa: A004
from collections.abc import AsyncIterator
from pathlib import PurePosixPath as P

import pytest

from storix._async.backends import BackendBase, StorageBackend
from storix._async.backends.memory import MemoryBackend
from storix.errors import (
    AlreadyExistsError,
    DirectoryNotEmptyError,
    IsADirectoryError,
    NotADirectoryError,
    PathNotFoundError,
)
from storix.types import EchoMode


@pytest.fixture
def backend() -> MemoryBackend:
    return MemoryBackend()


async def _astream(*chunks: bytes) -> AsyncIterator[bytes]:
    for chunk in chunks:
        yield chunk


async def put(
    backend: MemoryBackend, path: str, data: bytes = b'', mode: EchoMode = 'w'
) -> None:
    await backend.write(P(path), _astream(data), mode=mode, content_type=None)


# --- conformance ---


def test_backendbase_is_abstract():
    with pytest.raises(TypeError):
        BackendBase()  # type: ignore[abstract]


def test_memory_satisfies_protocol():
    # the annotation is the test: type checkers verify structural conformance
    backend: StorageBackend = MemoryBackend()
    assert backend.capabilities.content_type is False


async def test_root_exists_initially(backend: MemoryBackend):
    assert await backend.exists(P('/'))
    assert not await backend.exists(P('/anything'))


# --- write / read ---


async def test_write_creates_and_read_round_trips(backend: MemoryBackend):
    await put(backend, '/a.txt', b'hello')
    assert await backend.read(P('/a.txt')) == b'hello'


async def test_write_truncates_existing(backend: MemoryBackend):
    await put(backend, '/a.txt', b'old content')
    await put(backend, '/a.txt', b'new')
    assert await backend.read(P('/a.txt')) == b'new'


async def test_append_extends(backend: MemoryBackend):
    await put(backend, '/a.txt', b'hello ')
    await put(backend, '/a.txt', b'world', mode='a')
    assert await backend.read(P('/a.txt')) == b'hello world'


async def test_append_creates_missing(backend: MemoryBackend):
    await put(backend, '/a.txt', b'created', mode='a')
    assert await backend.read(P('/a.txt')) == b'created'


@pytest.mark.parametrize('mode', ['w', 'a'])
async def test_write_onto_directory_raises(backend: MemoryBackend, mode: EchoMode):
    await backend.make_dir(P('/d'), parents=False)
    with pytest.raises(IsADirectoryError):
        await put(backend, '/d', b'x', mode=mode)


async def test_read_missing_raises(backend: MemoryBackend):
    with pytest.raises(PathNotFoundError):
        await backend.read(P('/nope'))


async def test_read_directory_raises(backend: MemoryBackend):
    await backend.make_dir(P('/d'), parents=False)
    with pytest.raises(IsADirectoryError):
        await backend.read(P('/d'))


async def test_read_stream_yields_content(backend: MemoryBackend):
    await put(backend, '/a.txt', b'streamed')
    chunks = [chunk async for chunk in backend.read_stream(P('/a.txt'))]
    assert b''.join(chunks) == b'streamed'


# --- list_dir ---


async def test_list_dir_entries(backend: MemoryBackend):
    await backend.make_dir(P('/d'), parents=False)
    await backend.make_dir(P('/d/sub'), parents=False)
    await put(backend, '/d/a.txt', b'12345')

    entries = {(e.name, e.is_dir, e.size) async for e in backend.list_dir(P('/d'))}
    assert entries == {('sub', True, 0), ('a.txt', False, 5)}


async def test_list_dir_on_file_raises(backend: MemoryBackend):
    await put(backend, '/a.txt')
    with pytest.raises(NotADirectoryError):
        async for _ in backend.list_dir(P('/a.txt')):
            pass


async def test_list_dir_missing_raises(backend: MemoryBackend):
    with pytest.raises(PathNotFoundError):
        async for _ in backend.list_dir(P('/nope')):
            pass


async def test_list_dir_tolerates_delete_during_iteration(backend: MemoryBackend):
    await backend.make_dir(P('/d'), parents=False)
    for name in ('a', 'b', 'c'):
        await put(backend, f'/d/{name}')

    async for entry in backend.list_dir(P('/d')):
        await backend.delete(P('/d') / entry.name)

    assert [e async for e in backend.list_dir(P('/d'))] == []


# --- stat ---


async def test_stat_file(backend: MemoryBackend):
    await put(backend, '/a.txt', b'12345')
    props = await backend.stat(P('/a.txt'))
    assert props.kind == 'file'
    assert props.size == 5
    assert props.created.tzinfo is not None
    assert props.modified.tzinfo is not None


async def test_stat_directory_size_is_zero(backend: MemoryBackend):
    await backend.make_dir(P('/d'), parents=False)
    await put(backend, '/d/a.txt', b'12345')
    props = await backend.stat(P('/d'))
    assert props.kind == 'directory'
    assert props.size == 0


async def test_append_updates_modified_preserves_created(backend: MemoryBackend):
    await put(backend, '/a.txt', b'x')
    before = await backend.stat(P('/a.txt'))
    await put(backend, '/a.txt', b'y', mode='a')
    after = await backend.stat(P('/a.txt'))
    assert after.created == before.created
    assert after.modified >= before.modified


# --- make_dir ---


async def test_make_dir_plain(backend: MemoryBackend):
    await backend.make_dir(P('/d'), parents=False)
    assert (await backend.stat(P('/d'))).kind == 'directory'


async def test_make_dir_missing_parent_raises(backend: MemoryBackend):
    with pytest.raises(PathNotFoundError) as excinfo:
        await backend.make_dir(P('/missing/d'), parents=False)
    assert str(excinfo.value.path) == '/missing'


async def test_make_dir_parent_is_file_raises(backend: MemoryBackend):
    await put(backend, '/a.txt')
    with pytest.raises(NotADirectoryError):
        await backend.make_dir(P('/a.txt/d'), parents=False)


async def test_make_dir_existing_raises(backend: MemoryBackend):
    await backend.make_dir(P('/d'), parents=False)
    with pytest.raises(AlreadyExistsError):
        await backend.make_dir(P('/d'), parents=False)


async def test_make_dir_parents_creates_chain(backend: MemoryBackend):
    await backend.make_dir(P('/a/b/c'), parents=True)
    for path in ('/a', '/a/b', '/a/b/c'):
        assert (await backend.stat(P(path))).kind == 'directory'


async def test_make_dir_parents_is_idempotent(backend: MemoryBackend):
    await backend.make_dir(P('/d'), parents=True)
    await backend.make_dir(P('/d'), parents=True)  # no raise


async def test_make_dir_parents_existing_file_still_raises(backend: MemoryBackend):
    await put(backend, '/a.txt')
    with pytest.raises(AlreadyExistsError):
        await backend.make_dir(P('/a.txt'), parents=True)


async def test_make_dir_parents_file_in_chain_raises(backend: MemoryBackend):
    await put(backend, '/a.txt')
    with pytest.raises(NotADirectoryError):
        await backend.make_dir(P('/a.txt/d'), parents=True)


# --- delete ---


async def test_delete_file(backend: MemoryBackend):
    await put(backend, '/a.txt')
    await backend.delete(P('/a.txt'))
    assert not await backend.exists(P('/a.txt'))


async def test_delete_empty_directory(backend: MemoryBackend):
    await backend.make_dir(P('/d'), parents=False)
    await backend.delete(P('/d'))
    assert not await backend.exists(P('/d'))


async def test_delete_non_empty_directory_raises(backend: MemoryBackend):
    await backend.make_dir(P('/d'), parents=False)
    await put(backend, '/d/a.txt')
    with pytest.raises(DirectoryNotEmptyError):
        await backend.delete(P('/d'))


async def test_delete_missing_raises(backend: MemoryBackend):
    with pytest.raises(PathNotFoundError):
        await backend.delete(P('/nope'))


# --- generic fallbacks through BackendBase ---


async def test_du_file(backend: MemoryBackend):
    await put(backend, '/a.txt', b'12345')
    assert await backend.du(P('/a.txt')) == 5


async def test_du_sums_tree(backend: MemoryBackend):
    await backend.make_dir(P('/a/b'), parents=True)
    await put(backend, '/a/f1', b'123')
    await put(backend, '/a/b/f2', b'12345')
    assert await backend.du(P('/a')) == 8
    assert await backend.du(P('/')) == 8


async def test_move_file(backend: MemoryBackend):
    await put(backend, '/src.txt', b'payload')
    await backend.move(P('/src.txt'), P('/dst.txt'))
    assert await backend.read(P('/dst.txt')) == b'payload'
    assert not await backend.exists(P('/src.txt'))


async def test_copy_file_is_independent(backend: MemoryBackend):
    await put(backend, '/src.txt', b'payload')
    await backend.copy(P('/src.txt'), P('/dst.txt'))
    assert await backend.read(P('/dst.txt')) == b'payload'

    # mutating the copy must not touch the original (no buffer aliasing)
    await put(backend, '/dst.txt', b' more', mode='a')
    assert await backend.read(P('/src.txt')) == b'payload'


async def test_delete_tree_removes_everything(backend: MemoryBackend):
    await backend.make_dir(P('/d/sub'), parents=True)
    await put(backend, '/d/a.txt', b'x')
    await put(backend, '/d/sub/b.txt', b'y')

    await backend.delete_tree(P('/d'))

    for path in ('/d', '/d/sub', '/d/a.txt', '/d/sub/b.txt'):
        assert not await backend.exists(P(path))
    assert await backend.exists(P('/'))
