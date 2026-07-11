# ruff: noqa: A004
from pathlib import Path, PurePosixPath as P

import pytest

from storix._async import Storix
from storix._async.backends.local import LocalBackend
from storix._async.backends.memory import MemoryBackend
from storix.errors import (
    AlreadyExistsError,
    DirectoryNotEmptyError,
    IsADirectoryError,
    NotADirectoryError,
    PathNotFoundError,
    UnsupportedOperationError,
)
from storix.models import FileProperties


@pytest.fixture(params=['memory', 'local'])
def fs(request: pytest.FixtureRequest, tmp_path: Path) -> Storix:
    """The whole core suite runs against every backend."""
    if request.param == 'memory':
        return Storix(MemoryBackend())
    return Storix(LocalBackend(tmp_path))


# --- construction ---


async def test_layers_kwarg_wraps_the_backend():
    from functools import partial

    from storix._async import SandboxLayer

    inner = MemoryBackend()
    await inner.make_dir(P('/jail'), parents=False)
    fs = Storix(inner, layers=[partial(SandboxLayer, root='/jail')])

    await fs.touch('/a.txt')
    assert await inner.exists(P('/jail/a.txt'))


async def test_with_layer_returns_a_new_wrapped_session():
    from functools import partial

    from storix._async import SandboxLayer

    inner = MemoryBackend()
    await inner.make_dir(P('/jail'), parents=False)

    fs = Storix(inner)
    jailed = fs.with_layer(partial(SandboxLayer, root='/jail'))

    await jailed.touch('/a.txt')
    assert await inner.exists(P('/jail/a.txt'))
    assert await fs.exists('/jail/a.txt')  # original session untouched


async def test_resolve_returns_session_absolute_path(fs: Storix):
    await fs.mkdir('/docs')
    await fs.cd('/docs')
    assert str(fs.resolve('a.txt')) == '/docs/a.txt'
    assert str(fs.resolve('~/b.txt')) == '/b.txt'
    assert str(fs.resolve()) == '/docs'


# --- identity & navigation ---


def test_defaults(fs: Storix):
    assert str(fs.root) == '/'
    assert str(fs.home) == '/'
    assert str(fs.pwd()) == '/'


async def test_cd_into_directory(fs: Storix):
    await fs.mkdir('/docs')
    await fs.cd('/docs')
    assert str(fs.pwd()) == '/docs'


async def test_cd_none_returns_home(fs: Storix):
    await fs.mkdir('/docs')
    await fs.cd('/docs')
    await fs.cd()
    assert fs.pwd() == fs.home


async def test_cd_into_file_raises(fs: Storix):
    await fs.touch('/a.txt')
    with pytest.raises(NotADirectoryError):
        await fs.cd('/a.txt')


async def test_cd_missing_raises(fs: Storix):
    with pytest.raises(PathNotFoundError):
        await fs.cd('/nope')


async def test_relative_paths_resolve_against_cwd(fs: Storix):
    await fs.mkdir('/docs')
    await fs.cd('/docs')
    await fs.touch('a.txt')
    assert await fs.exists('/docs/a.txt')
    assert await fs.exists('../docs/a.txt')


async def test_tilde_resolves_against_home(fs: Storix):
    backend = MemoryBackend()
    scoped = Storix(backend, home='/h')
    await Storix(backend).mkdir('/h')
    await scoped.touch('~/a.txt')
    assert await scoped.exists('/h/a.txt')


# --- ls ---


async def test_ls_hides_dotfiles_by_default(fs: Storix):
    await fs.touch('/a.txt', '/.env')
    names = {str(p) for p in await fs.ls('/')}
    assert names == {'a.txt'}


async def test_ls_all_shows_hidden(fs: Storix):
    await fs.touch('/a.txt', '/.env')
    names = {str(p) for p in await fs.ls('/', all=True)}
    assert names == {'a.txt', '.env'}


async def test_ls_abs_returns_full_paths(fs: Storix):
    await fs.mkdir('/docs')
    await fs.touch('/docs/a.txt')
    assert await fs.ls('/docs', abs=True) == [P('/docs/a.txt')]


async def test_ls_on_file_returns_the_file(fs: Storix):
    await fs.touch('/a.txt')
    assert await fs.ls('/a.txt') == [P('a.txt')]
    assert await fs.ls('/a.txt', abs=True) == [P('/a.txt')]


async def test_ls_missing_raises(fs: Storix):
    with pytest.raises(PathNotFoundError):
        await fs.ls('/nope')


# --- cat ---


async def test_cat_single(fs: Storix):
    await fs.echo(b'hello', '/a.txt')
    assert await fs.cat('/a.txt') == b'hello'


async def test_cat_concatenates_in_order(fs: Storix):
    await fs.echo(b'one', '/a.txt')
    await fs.echo(b'two', '/b.txt')
    assert await fs.cat('/a.txt', '/b.txt') == b'onetwo'


# --- touch ---


async def test_touch_creates_empty_files_variadic(fs: Storix):
    await fs.touch('/a.txt', '/b.txt')
    assert await fs.cat('/a.txt') == b''
    assert await fs.cat('/b.txt') == b''


async def test_touch_preserves_content_and_refreshes_mtime(fs: Storix):
    await fs.echo(b'content', '/a.txt')
    before = await fs.stat('/a.txt')
    await fs.touch('/a.txt')
    after = await fs.stat('/a.txt')
    assert await fs.cat('/a.txt') == b'content'
    assert after.modified >= before.modified


async def test_touch_missing_parent_raises(fs: Storix):
    with pytest.raises(PathNotFoundError) as excinfo:
        await fs.touch('/missing/a.txt')
    assert str(excinfo.value.path) == '/missing'


# --- echo ---


async def test_echo_overwrites(fs: Storix):
    await fs.echo(b'old', '/a.txt')
    await fs.echo(b'new', '/a.txt')
    assert await fs.cat('/a.txt') == b'new'


async def test_echo_appends(fs: Storix):
    await fs.echo(b'hello ', '/a.txt')
    await fs.echo(b'world', '/a.txt', mode='a')
    assert await fs.cat('/a.txt') == b'hello world'


async def test_echo_encodes_str(fs: Storix):
    await fs.echo('text data', '/a.txt')
    assert await fs.cat('/a.txt') == b'text data'


async def test_echo_accepts_iterable_of_chunks(fs: Storix):
    await fs.echo([b'a', b'b', b'c'], '/a.txt')
    assert await fs.cat('/a.txt') == b'abc'


async def test_echo_content_type_requires_capability(fs: Storix):
    with pytest.raises(UnsupportedOperationError) as excinfo:
        await fs.echo(b'x', '/a.txt', content_type='text/plain')
    assert excinfo.value.operation == 'content_type'


async def test_echo_metadata_follows_capability(fs: Storix):
    if fs.backend.capabilities.custom_metadata:
        await fs.echo(b'x', '/m.txt', metadata={'owner': 'tests'})
        assert (await fs.stat('/m.txt')).metadata == {'owner': 'tests'}
    else:
        with pytest.raises(UnsupportedOperationError) as excinfo:
            await fs.echo(b'x', '/m.txt', metadata={'owner': 'tests'})
        assert excinfo.value.operation == 'custom_metadata'


async def test_set_metadata_merge(fs: Storix):
    if not fs.backend.capabilities.custom_metadata:
        with pytest.raises(UnsupportedOperationError):
            await fs.set_metadata('/m.txt', {'a': '1'})
        return

    await fs.echo(b'x', '/m.txt', metadata={'a': '1', 'b': '2'})
    await fs.set_metadata('/m.txt', {'b': '9', 'c': '3'}, merge=True)
    assert (await fs.stat('/m.txt')).metadata == {'a': '1', 'b': '9', 'c': '3'}

    await fs.set_metadata('/m.txt', {'only': 'this'})  # replace, not merge
    assert (await fs.stat('/m.txt')).metadata == {'only': 'this'}


async def test_url_requires_capability(fs: Storix):
    await fs.touch('/a.txt')
    with pytest.raises(UnsupportedOperationError) as excinfo:
        await fs.url('/a.txt')
    assert excinfo.value.operation == 'presigned_urls'


async def test_data_url_works_on_any_backend(fs: Storix):
    await fs.echo(b'hello', '/a.txt')
    url = await fs.data_url('/a.txt')
    assert url.startswith('data:')
    assert url.endswith('aGVsbG8=')  # base64('hello')


async def test_echo_missing_parent_raises(fs: Storix):
    with pytest.raises(PathNotFoundError):
        await fs.echo(b'x', '/missing/a.txt')


# --- mkdir ---


async def test_mkdir_variadic(fs: Storix):
    await fs.mkdir('/a', '/b')
    assert await fs.isdir('/a')
    assert await fs.isdir('/b')


async def test_mkdir_parents(fs: Storix):
    await fs.mkdir('/a/b/c', parents=True)
    assert await fs.isdir('/a/b/c')


async def test_mkdir_existing_raises(fs: Storix):
    await fs.mkdir('/a')
    with pytest.raises(AlreadyExistsError):
        await fs.mkdir('/a')


# --- rm / rmdir ---


async def test_rm_files_variadic(fs: Storix):
    await fs.touch('/a.txt', '/b.txt')
    await fs.rm('/a.txt', '/b.txt')
    assert not await fs.exists('/a.txt')
    assert not await fs.exists('/b.txt')


async def test_rm_directory_without_recursive_raises(fs: Storix):
    await fs.mkdir('/d')
    with pytest.raises(IsADirectoryError):
        await fs.rm('/d')


async def test_rm_recursive_removes_tree(fs: Storix):
    await fs.mkdir('/d/sub', parents=True)
    await fs.touch('/d/a.txt', '/d/sub/b.txt')
    await fs.rm('/d', recursive=True)
    assert not await fs.exists('/d')


async def test_rm_validates_all_before_deleting(fs: Storix):
    """One bad target means nothing gets deleted."""
    await fs.touch('/a.txt')
    await fs.mkdir('/d')
    with pytest.raises(IsADirectoryError):
        await fs.rm('/a.txt', '/d')
    assert await fs.exists('/a.txt')


async def test_rm_missing_raises(fs: Storix):
    with pytest.raises(PathNotFoundError):
        await fs.rm('/nope')


async def test_rmdir_removes_empty_directories(fs: Storix):
    await fs.mkdir('/a', '/b')
    await fs.rmdir('/a', '/b')
    assert not await fs.exists('/a')


async def test_rmdir_non_empty_raises(fs: Storix):
    await fs.mkdir('/d')
    await fs.touch('/d/a.txt')
    with pytest.raises(DirectoryNotEmptyError):
        await fs.rmdir('/d')


async def test_rmdir_on_file_raises(fs: Storix):
    await fs.touch('/a.txt')
    with pytest.raises(NotADirectoryError):
        await fs.rmdir('/a.txt')


# --- mv ---


async def test_mv_renames_file(fs: Storix):
    await fs.echo(b'payload', '/old.txt')
    await fs.mv('/old.txt', '/new.txt')
    assert await fs.cat('/new.txt') == b'payload'
    assert not await fs.exists('/old.txt')


async def test_mv_into_existing_directory(fs: Storix):
    await fs.echo(b'x', '/a.txt')
    await fs.mkdir('/archive')
    await fs.mv('/a.txt', '/archive')
    assert await fs.exists('/archive/a.txt')


async def test_mv_multiple_sources_into_directory(fs: Storix):
    await fs.touch('/a.txt', '/b.txt')
    await fs.mkdir('/archive')
    await fs.mv('/a.txt', '/b.txt', '/archive')
    assert await fs.exists('/archive/a.txt')
    assert await fs.exists('/archive/b.txt')


async def test_mv_multiple_sources_require_directory_destination(fs: Storix):
    await fs.touch('/a.txt', '/b.txt', '/target.txt')
    with pytest.raises(NotADirectoryError):
        await fs.mv('/a.txt', '/b.txt', '/target.txt')


async def test_mv_moves_directory_tree(fs: Storix):
    await fs.mkdir('/d/sub', parents=True)
    await fs.echo(b'x', '/d/sub/a.txt')
    await fs.mv('/d', '/renamed')
    assert await fs.cat('/renamed/sub/a.txt') == b'x'
    assert not await fs.exists('/d')


async def test_mv_requires_destination(fs: Storix):
    with pytest.raises(TypeError):
        await fs.mv('/only-one')


async def test_mv_missing_source_raises(fs: Storix):
    with pytest.raises(PathNotFoundError):
        await fs.mv('/nope', '/dst')


# --- cp ---


async def test_cp_file(fs: Storix):
    await fs.echo(b'payload', '/a.txt')
    await fs.cp('/a.txt', '/b.txt')
    assert await fs.cat('/b.txt') == b'payload'
    assert await fs.cat('/a.txt') == b'payload'


async def test_cp_into_existing_directory(fs: Storix):
    await fs.echo(b'x', '/a.txt')
    await fs.mkdir('/backup')
    await fs.cp('/a.txt', '/backup')
    assert await fs.exists('/backup/a.txt')


async def test_cp_directory_without_recursive_raises(fs: Storix):
    await fs.mkdir('/d')
    with pytest.raises(IsADirectoryError):
        await fs.cp('/d', '/copy')


async def test_cp_recursive_copies_tree(fs: Storix):
    await fs.mkdir('/d/sub', parents=True)
    await fs.echo(b'x', '/d/sub/a.txt')
    await fs.cp('/d', '/copy', recursive=True)
    assert await fs.cat('/copy/sub/a.txt') == b'x'
    assert await fs.cat('/d/sub/a.txt') == b'x'


async def test_cp_requires_destination(fs: Storix):
    with pytest.raises(TypeError):
        await fs.cp('/only-one')


# --- stat / du / predicates ---


async def test_stat_shapes_file_properties(fs: Storix):
    await fs.echo(b'12345', '/a.txt')
    props = await fs.stat('/a.txt')
    assert isinstance(props, FileProperties)
    assert props.name == 'a.txt'
    assert props.size == 5
    assert props.kind == 'file'


async def test_stat_root_has_a_name(fs: Storix):
    props = await fs.stat('/')
    assert props.name == '/'
    assert props.kind == 'directory'


async def test_du_sums_tree(fs: Storix):
    await fs.mkdir('/d')
    await fs.echo(b'123', '/d/a.txt')
    await fs.echo(b'45', '/d/b.txt')
    assert await fs.du('/d') == 5


async def test_context_manager_closes_backend():
    class _ClosingBackend(MemoryBackend):
        closed = False

        async def close(self) -> None:
            self.closed = True

    backend = _ClosingBackend()
    async with Storix(backend) as fs:
        await fs.touch('/a.txt')
    assert backend.closed


async def test_predicates(fs: Storix):
    await fs.touch('/a.txt')
    await fs.mkdir('/d')
    assert await fs.isfile('/a.txt')
    assert not await fs.isfile('/d')
    assert not await fs.isfile('/nope')
    assert await fs.isdir('/d')
    assert not await fs.isdir('/a.txt')
    assert not await fs.isdir('/nope')
