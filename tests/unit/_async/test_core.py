# ruff: noqa: A004
import io

from pathlib import Path, PurePosixPath as P

import pytest

from storix._async import Storix
from storix._async.backends.local import LocalBackend
from storix._async.backends.memory import MemoryBackend
from storix.constants import DEFAULT_CONCURRENCY, DEFAULT_READ_CHUNK_SIZE
from storix.enums import Capability, PathKind
from storix.errors import (
    AlreadyExistsError,
    DirectoryNotEmptyError,
    IsADirectoryError,
    NotADirectoryError,
    PathNotFoundError,
    UnsupportedOperationError,
)
from storix.models import DirEntry, FileProperties


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


async def test_chroot_jails_a_new_session(fs: Storix):
    await fs.mkdir('/jail')
    await fs.echo(b'secret', '/top-secret.txt')

    jailed = fs.chroot('/jail')
    await jailed.touch('/inside.txt')

    assert await fs.exists('/jail/inside.txt')  # same store underneath
    assert not await jailed.exists('/top-secret.txt')  # cannot see above
    assert not await jailed.exists('/../top-secret.txt')  # cannot escape
    assert str(fs.pwd()) == '/'  # original untouched


async def test_resolve_returns_session_absolute_path(fs: Storix):
    await fs.mkdir('/docs')
    await fs.cd('/docs')
    assert str(fs.resolve('a.txt')) == '/docs/a.txt'
    assert str(fs.resolve('~/b.txt')) == '/b.txt'
    assert str(fs.resolve()) == '/docs'


async def test_locate_returns_physical_uri(fs: Storix):
    await fs.echo(b'x', '/a.txt')
    uri = fs.locate('/a.txt')
    assert '://' in uri  # a scheme-qualified locator
    if isinstance(fs.backend, LocalBackend):
        assert uri.startswith('file://')
        assert uri.endswith('/a.txt')


async def test_locate_through_sandbox_gives_real_path():
    from storix._async import SandboxLayer

    inner = MemoryBackend()
    await inner.make_dir(P('/jail'), parents=False)
    fs = Storix(SandboxLayer(inner, root='/jail'))
    await fs.echo(b'x', '/a.txt')
    # the session sees '/a.txt'; locate resolves to the real inner path
    assert fs.locate('/a.txt') == inner.locate(P('/jail/a.txt'))


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


# --- scandir / iterdir / is_empty ---


async def test_scandir_yields_rich_entries(fs: Storix):
    await fs.mkdir('/docs')
    await fs.echo(b'hello', '/a.txt')

    entries = {e.name: e async for e in fs.scandir('/')}

    assert entries.keys() == {'docs', 'a.txt'}
    docs = entries['docs']
    assert isinstance(docs, DirEntry)
    assert docs.kind is PathKind.DIRECTORY
    assert docs.is_dir and not docs.is_file
    assert docs.path == P('/docs')
    a = entries['a.txt']
    assert a.kind is PathKind.FILE
    assert a.is_file and not a.is_dir
    assert a.path == P('/a.txt')
    assert a.size == 5


def test_scandir_returns_a_lazy_iterator(fs: Storix):
    from collections.abc import AsyncIterator

    # a generator, not a materialized list: nothing is read until iterated
    assert isinstance(fs.scandir('/'), AsyncIterator)


async def test_scandir_hides_dotfiles_unless_all(fs: Storix):
    await fs.touch('/a.txt', '/.env')

    visible = {e.name async for e in fs.scandir('/')}
    every = {e.name async for e in fs.scandir('/', all=True)}

    assert visible == {'a.txt'}
    assert every == {'a.txt', '.env'}


async def test_scandir_on_file_yields_the_file(fs: Storix):
    await fs.echo(b'hi', '/a.txt')

    entries = [e async for e in fs.scandir('/a.txt')]

    assert len(entries) == 1
    assert entries[0].name == 'a.txt'
    assert entries[0].path == P('/a.txt')
    assert entries[0].is_file


async def test_iterdir_yields_absolute_paths(fs: Storix):
    await fs.mkdir('/docs')
    await fs.touch('/a.txt')

    paths = [p async for p in fs.iterdir('/')]
    scanned = [e.path async for e in fs.scandir('/')]

    assert paths == scanned  # iterdir is scandir's paths
    assert {str(p) for p in paths} == {'/docs', '/a.txt'}


async def test_is_empty_true_on_empty_dir(fs: Storix):
    await fs.mkdir('/empty')
    assert await fs.is_empty('/empty') is True


async def test_is_empty_false_on_populated_dir(fs: Storix):
    await fs.mkdir('/docs')
    await fs.touch('/docs/a.txt')
    assert await fs.is_empty('/docs') is False


async def test_is_empty_false_on_dotfile_only_dir(fs: Storix):
    await fs.mkdir('/docs')
    await fs.touch('/docs/.env')
    # a dir holding only a hidden file is not empty (rmdir would fail on it)
    assert await fs.is_empty('/docs') is False


async def test_is_empty_missing_raises(fs: Storix):
    with pytest.raises(PathNotFoundError):
        await fs.is_empty('/nope')


# --- empty_children (bulk emptiness) ---
#
# The fs fixture runs each case against memory (advertises bulk_listing, the
# one-request fast path) and local (does not, the concurrent fallback), so a
# single assertion pins both paths to the same answer.


async def test_empty_children_reports_each_child(fs: Storix):
    await fs.mkdir('/d')
    await fs.mkdir('/d/empty')
    await fs.mkdir('/d/full')
    await fs.touch('/d/full/a.txt')
    assert await fs.empty_children('/d') == {'empty': True, 'full': False}


async def test_empty_children_honors_explicit_names(fs: Storix):
    await fs.mkdir('/d')
    await fs.mkdir('/d/empty')
    await fs.mkdir('/d/full')
    await fs.touch('/d/full/a.txt')
    assert await fs.empty_children('/d', names=['full']) == {'full': False}


async def test_empty_children_with_names_uses_one_bulk_listing(
    monkeypatch: pytest.MonkeyPatch,
):
    backend = MemoryBackend()
    fs = Storix(backend)
    await fs.mkdir('/d/empty', parents=True)
    await fs.mkdir('/d/full')
    await fs.touch('/d/full/a.txt')
    calls = 0
    list_tree = backend.list_tree

    async def counting_list_tree(path: P):
        nonlocal calls
        calls += 1
        async for descendant in list_tree(path):
            yield descendant

    monkeypatch.setattr(backend, 'list_tree', counting_list_tree)

    assert await fs.empty_children('/d', names=['empty', 'full']) == {
        'empty': True,
        'full': False,
    }
    assert calls == 1


async def test_empty_children_ignores_file_children(fs: Storix):
    await fs.mkdir('/d')
    await fs.touch('/d/a.txt')
    # only a file child: nothing to report emptiness for
    assert await fs.empty_children('/d') == {}


async def test_empty_children_counts_a_nested_subdir_as_nonempty(fs: Storix):
    # a child holding only a subdirectory is non-empty, exactly like is_empty
    await fs.mkdir('/d')
    await fs.mkdir('/d/holder/sub', parents=True)
    assert await fs.empty_children('/d') == {'holder': False}


async def test_empty_children_still_correct_beyond_key_bound(
    fs: Storix, monkeypatch: pytest.MonkeyPatch
):
    # a tiny bound forces the fast path to bail mid-listing; the concurrent
    # fallback must still return the right answer
    monkeypatch.setattr('storix._async.core.BULK_LISTING_KEY_LIMIT', 1)
    await fs.mkdir('/d')
    await fs.mkdir('/d/empty')
    await fs.mkdir('/d/full')
    await fs.touch('/d/full/a.txt')
    assert await fs.empty_children('/d') == {'empty': True, 'full': False}


async def test_empty_children_falls_back_without_capability():
    import dataclasses

    backend = MemoryBackend()
    backend.capabilities = dataclasses.replace(backend.capabilities, bulk_listing=False)
    fs = Storix(backend)
    await fs.mkdir('/d')
    await fs.mkdir('/d/empty')
    await fs.mkdir('/d/full')
    await fs.touch('/d/full/a.txt')
    assert await fs.empty_children('/d') == {'empty': True, 'full': False}


# --- walk / find / glob ---


async def _nested_tree(fs: Storix) -> None:
    """A small nested tree shared by the recursive-listing tests.

    /pkg, /pkg/sub, /pkg/mod.py, /pkg/sub/deep.py, /pkg/readme.txt.
    """
    await fs.mkdir('/pkg/sub', parents=True)
    await fs.echo(b'a', '/pkg/mod.py')
    await fs.echo(b'bb', '/pkg/sub/deep.py')
    await fs.echo(b'ccc', '/pkg/readme.txt')


class RecordingBackend(MemoryBackend):
    """A MemoryBackend that records every ``list_dir`` target."""

    def __init__(self):
        super().__init__()
        self.listed: list[str] = []

    async def list_dir(self, path):
        self.listed.append(str(path))
        async for entry in super().list_dir(path):
            yield entry


class FailingListBackend(MemoryBackend):
    """A MemoryBackend whose listing of one directory always fails."""

    def __init__(self, broken: str):
        super().__init__()
        self.broken = broken

    async def list_dir(self, path):
        if str(path) == self.broken:
            raise PathNotFoundError(path)
        async for entry in super().list_dir(path):
            yield entry


async def test_walk_recurses_into_every_descendant(fs: Storix):
    await _nested_tree(fs)

    names = {e.name async for e in fs.walk('/')}

    assert names == {'pkg', 'sub', 'mod.py', 'deep.py', 'readme.txt'}


def test_walk_returns_a_lazy_iterator(fs: Storix):
    from collections.abc import AsyncIterator

    # a generator, not a materialized list: nothing is read until iterated
    assert isinstance(fs.walk('/'), AsyncIterator)


async def test_walk_top_down_yields_a_directory_before_its_children(fs: Storix):
    await _nested_tree(fs)

    names = [e.name async for e in fs.walk('/')]

    assert names.index('pkg') < names.index('sub') < names.index('deep.py')


async def test_walk_post_order_yields_a_child_before_its_parent(fs: Storix):
    await _nested_tree(fs)

    names = [e.name async for e in fs.walk('/', top_down=False)]

    assert names.index('deep.py') < names.index('sub')  # file before its dir
    assert names.index('sub') < names.index('pkg')  # child dir before parent


async def test_walk_excludes_hidden_and_does_not_descend_them_unless_all(
    fs: Storix,
):
    await fs.mkdir('/pkg/.git', parents=True)
    await fs.touch('/pkg/.env', '/pkg/.git/config')

    visible = {e.name async for e in fs.walk('/pkg')}
    every = {e.name async for e in fs.walk('/pkg', all=True)}

    assert '.env' not in visible and '.git' not in visible
    assert 'config' not in visible  # a hidden directory is not descended
    assert {'.env', '.git', 'config'} <= every


async def test_walk_level_order_emits_whole_levels_in_listing_order(fs: Storix):
    await _nested_tree(fs)

    level_one = [e.name async for e in fs.scandir('/pkg')]
    walked = [e.name async for e in fs.walk('/pkg', order='level')]

    # the first level arrives whole, in scandir's listing order, before
    # anything deeper; completion timing cannot reorder it (``concurrent``
    # returns listings in submission order).
    assert walked == [*level_one, 'deep.py']


async def test_walk_level_order_post_order_emits_directories_deepest_first(
    fs: Storix,
):
    await fs.mkdir('/a/b/c', parents=True)

    names = [e.name async for e in fs.walk('/', top_down=False, order='level')]

    assert names == ['c', 'b', 'a']


async def _dfs_tree() -> Storix:
    """A tree with sibling directories, for the exact-order tests.

    /pkg/lib/inner/two.py, /pkg/lib/one.py, /pkg/bin/tool, /pkg/root.txt,
    created in that order on a MemoryBackend, whose listing order is
    insertion order; a deterministic reference the hardcoded expected
    sequences depend on (local disk listing order is OS-dependent).
    """
    fs = Storix(MemoryBackend())
    await fs.mkdir('/pkg/lib/inner', parents=True)
    await fs.mkdir('/pkg/bin')
    await fs.echo(b'1', '/pkg/lib/one.py')
    await fs.echo(b'2', '/pkg/lib/inner/two.py')
    await fs.echo(b'3', '/pkg/bin/tool')
    await fs.echo(b'4', '/pkg/root.txt')
    return fs


async def test_walk_default_order_is_exact_pre_order():
    """The default emission is the sequential pre-0.4.8 contract: each
    directory immediately followed by its whole subtree, siblings in
    backend listing order, files and directories interleaved as listed."""
    fs = await _dfs_tree()

    names = [e.name async for e in fs.walk('/pkg')]

    assert names == ['lib', 'inner', 'two.py', 'one.py', 'bin', 'tool', 'root.txt']


async def test_walk_default_order_is_exact_post_order():
    """top_down=False keeps files in encounter order and emits every
    directory only after its entire subtree, like the sequential walk."""
    fs = await _dfs_tree()

    names = [e.name async for e in fs.walk('/pkg', top_down=False)]

    assert names == ['two.py', 'inner', 'one.py', 'lib', 'tool', 'bin', 'root.txt']


async def test_walk_max_depth_one_includes_only_immediate_children(fs: Storix):
    await _nested_tree(fs)

    names = {e.name async for e in fs.walk('/pkg', max_depth=1)}

    assert names == {'sub', 'mod.py', 'readme.txt'}


async def test_walk_negative_max_depth_raises(fs: Storix):
    with pytest.raises(ValueError, match='max_depth'):
        _ = [entry async for entry in fs.walk('/', max_depth=-1)]


async def test_walk_max_depth_zero_yields_nothing_and_lists_nothing():
    backend = RecordingBackend()
    fs = Storix(backend)
    await fs.mkdir('/pkg/sub', parents=True)

    backend.listed.clear()

    assert [entry async for entry in fs.walk('/pkg', max_depth=0)] == []
    assert backend.listed == []


async def test_walk_max_depth_stops_excluded_listings_before_the_backend():
    backend = RecordingBackend()
    fs = Storix(backend)
    await fs.mkdir('/pkg/sub/deep', parents=True)

    backend.listed.clear()
    _ = [entry async for entry in fs.walk('/pkg', max_depth=1)]

    assert backend.listed == ['/pkg']  # /pkg/sub is never listed


async def test_walk_does_not_list_hidden_directories_unless_all():
    backend = RecordingBackend()
    fs = Storix(backend)
    await fs.mkdir('/pkg/.git', parents=True)
    await fs.touch('/pkg/.git/config')

    backend.listed.clear()
    _ = [entry async for entry in fs.walk('/pkg')]
    assert '/pkg/.git' not in backend.listed

    backend.listed.clear()
    _ = [entry async for entry in fs.walk('/pkg', all=True)]
    assert '/pkg/.git' in backend.listed


async def test_walk_lists_each_level_through_bounded_concurrent_batches(monkeypatch):
    """Sibling listings are handed to ``concurrent`` together, chunked.

    One level's directories go out as whole chunks of at most
    DEFAULT_CONCURRENCY thunks per ``concurrent`` call - never one call
    per directory, never an unbounded batch. The overlap and in-flight
    ceiling inside a chunk are ``concurrent``'s own tested semantics.
    """
    from storix._async import core as engine

    fs = Storix(MemoryBackend())
    width = DEFAULT_CONCURRENCY + 3
    await fs.mkdir('/pkg')
    await fs.mkdir(*(f'/pkg/d{i:03d}' for i in range(width)))

    batches: list[int] = []
    real = engine.concurrent

    async def recording(thunks, **kwargs):
        materialized = list(thunks)
        batches.append(len(materialized))
        return await real(materialized, **kwargs)

    monkeypatch.setattr(engine, 'concurrent', recording)

    _ = [entry async for entry in fs.walk('/pkg')]

    assert batches == [1, DEFAULT_CONCURRENCY, 3]


async def test_walk_propagates_backend_errors_unwrapped():
    fs = Storix(FailingListBackend('/pkg/sub'))
    await fs.mkdir('/pkg/sub', parents=True)

    with pytest.raises(PathNotFoundError):
        _ = [entry async for entry in fs.walk('/')]


async def test_find_filters_by_name_glob(fs: Storix):
    await _nested_tree(fs)

    py = {e.name async for e in fs.find('/', name='*.py')}

    assert py == {'mod.py', 'deep.py'}


async def test_find_filters_by_kind(fs: Storix):
    await _nested_tree(fs)

    dirs = {e.name async for e in fs.find('/', kind='directory')}
    files = {e.name async for e in fs.find('/pkg', kind=PathKind.FILE)}

    assert dirs == {'pkg', 'sub'}
    assert files == {'mod.py', 'deep.py', 'readme.txt'}


async def test_find_and_glob_reach_hidden_entries_only_with_all(fs: Storix):
    await fs.echo(b'x', '/.env')
    await fs.mkdir('/.git')
    await fs.echo(b'x', '/.git/config')

    # excluded by default (and hidden directories are not descended)
    assert [e.name async for e in fs.find(name='.env')] == []
    assert [p async for p in fs.glob('**/config')] == []
    # all=True reaches the dotfile and descends the hidden directory
    assert [e.name async for e in fs.find(name='.env', all=True)] == ['.env']
    assert [str(p) async for p in fs.glob('**/config', all=True)] == ['/.git/config']


async def test_glob_matches_direct_children_recursive_and_subdirs(fs: Storix):
    await _nested_tree(fs)

    direct = {str(p) async for p in fs.glob('*.py', '/pkg')}
    recursive = {str(p) async for p in fs.glob('**/*.py', '/pkg')}
    subdir = {str(p) async for p in fs.glob('sub/*', '/pkg')}

    assert direct == {'/pkg/mod.py'}  # '*' stops at a separator
    assert recursive == {'/pkg/mod.py', '/pkg/sub/deep.py'}  # '**' spans depth
    assert subdir == {'/pkg/sub/deep.py'}


# --- cat ---


async def test_cat_single(fs: Storix):
    await fs.echo(b'hello', '/a.txt')
    assert await fs.cat('/a.txt') == b'hello'


async def test_cat_concatenates_in_order(fs: Storix):
    await fs.echo(b'one', '/a.txt')
    await fs.echo(b'two', '/b.txt')
    assert await fs.cat('/a.txt', '/b.txt') == b'onetwo'


async def test_cat_fan_out_propagates_underlying_error_unwrapped(fs: Storix):
    """One missing target in a fan-out raises the storix error unwrapped.

    The sync flavor fans out over a thread pool; the error must arrive as
    the raw ``PathNotFoundError``, not an ``ExceptionGroup``, so callers'
    ``except PathNotFoundError`` keeps working.
    """
    await fs.echo(b'here', '/exists.txt')
    with pytest.raises(PathNotFoundError):
        await fs.cat('/exists.txt', '/missing.txt')


async def test_stream_yields_content_in_chunks(fs: Storix):
    await fs.echo(b'streamed payload', '/a.bin')
    chunks = [chunk async for chunk in fs.stream('/a.bin')]
    assert b''.join(chunks) == b'streamed payload'


async def test_stream_default_is_bounded_for_reference_backends(fs: Storix):
    payload = b'x' * (DEFAULT_READ_CHUNK_SIZE + 1)
    await fs.echo(payload, '/a.bin')

    chunks = [chunk async for chunk in fs.stream('/a.bin')]

    assert [len(chunk) for chunk in chunks] == [DEFAULT_READ_CHUNK_SIZE, 1]


async def test_stream_concatenates_multiple_paths(fs: Storix):
    await fs.echo(b'one', '/a.txt')
    await fs.echo(b'two', '/b.txt')
    joined = b''.join([c async for c in fs.stream('/a.txt', '/b.txt')])
    assert joined == b'onetwo'


async def test_stream_honors_maximum_chunk_size(fs: Storix):
    await fs.echo(b'0123456789', '/a.txt')
    chunks = [chunk async for chunk in fs.stream('/a.txt', chunk_size=4)]
    assert b''.join(chunks) == b'0123456789'
    assert all(0 < len(chunk) <= 4 for chunk in chunks)


@pytest.mark.parametrize('chunk_size', [0, -1])
async def test_stream_rejects_non_positive_chunk_size(fs: Storix, chunk_size: int):
    await fs.echo(b'x', '/a.txt')
    with pytest.raises(ValueError, match='chunk_size must be positive'):
        [chunk async for chunk in fs.stream('/a.txt', chunk_size=chunk_size)]


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


async def test_echo_accepts_chunk_size(fs: Storix):
    await fs.echo([b'ab', b'cd', b'ef'], '/a.txt', chunk_size=4)
    assert await fs.cat('/a.txt') == b'abcdef'


@pytest.mark.parametrize('chunk_size', [0, -1])
async def test_echo_rejects_non_positive_chunk_size_without_writing(
    fs: Storix, chunk_size: int
):
    with pytest.raises(ValueError, match='chunk_size must be positive'):
        await fs.echo(b'x', '/a.txt', chunk_size=chunk_size)
    assert not await fs.exists('/a.txt')


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


# --- provisioning ---


async def test_provision_on_capable_backend_reports_present():
    # Given a session over a backend whose root is always present
    fs = Storix(MemoryBackend())
    # When provision runs, the capable backend answers directly
    assert await fs.provision() is False


async def test_provision_unsupported_backend_names_provider_tooling():
    # Given a session over an opendal backend (data-plane only)
    from storix._async.backends.opendal import OpendalBackend

    fs = Storix(OpendalBackend('memory'))

    # When provision runs, the core gate rejects it
    with pytest.raises(UnsupportedOperationError) as exc_info:
        await fs.provision()

    # Then the error names the missing capability and points at provider tooling
    assert exc_info.value.operation == Capability.PROVISIONING
    assert 'control-plane' in str(exc_info.value)


async def test_provision_targets_the_base_backend_under_layers():
    # Given a capable backend wrapped in a sandbox layer
    from storix._async import SandboxLayer

    inner = MemoryBackend()
    await inner.make_dir(P('/jail'), parents=False)
    fs = Storix(SandboxLayer(inner, root='/jail'))

    # When provision runs, it reaches the base backend beneath the layer
    assert await fs.provision() is False


async def test_download_writes_the_whole_file(tmp_path):
    """Given a file, when downloaded to a sink, then the bytes match."""
    fs = Storix(MemoryBackend())
    payload = bytes(range(256)) * 4096
    await fs.echo(payload, '/big.bin')
    dest = tmp_path / 'out.bin'

    with dest.open('wb') as handle:
        written = await fs.download('/big.bin', handle)

    assert written == len(payload)
    assert dest.read_bytes() == payload


async def test_download_in_parallel_ranges_matches_sequential(tmp_path):
    """Given several ranges, when downloaded, then the file is assembled in order."""
    fs = Storix(MemoryBackend())
    payload = bytes(range(256)) * 4096
    await fs.echo(payload, '/big.bin')
    dest = tmp_path / 'out.bin'

    with dest.open('wb') as handle:
        written = await fs.download('/big.bin', handle, ranges=4, chunk_size=1024)

    assert written == len(payload)
    assert dest.read_bytes() == payload


async def test_download_to_a_buffer_falls_back_to_sequential():
    """Given a sink with no descriptor, when downloaded, then it still works."""
    fs = Storix(MemoryBackend())
    await fs.echo(b'payload', '/small.bin')
    sink = io.BytesIO()

    written = await fs.download('/small.bin', sink, ranges=4)

    assert written == 7
    assert sink.getvalue() == b'payload'


async def test_download_rejects_a_directory(tmp_path):
    """Given a directory, when downloaded, then it raises."""
    fs = Storix(MemoryBackend())
    await fs.mkdir('/dir')

    with (tmp_path / 'out.bin').open('wb') as handle, pytest.raises(IsADirectoryError):
        await fs.download('/dir', handle)


@pytest.mark.parametrize('ranges', [0, -1])
async def test_download_rejects_a_non_positive_range_count(tmp_path, ranges):
    """Given ranges below one, when downloaded, then it raises ValueError."""
    fs = Storix(MemoryBackend())
    await fs.echo(b'x', '/f.bin')

    with (tmp_path / 'out.bin').open('wb') as handle, pytest.raises(ValueError):
        await fs.download('/f.bin', handle, ranges=ranges)
