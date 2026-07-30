import dataclasses
import datetime as dt
import importlib
import io
import re
import sys

from collections.abc import Generator

import pytest

from rich.color import ColorSystem
from typer.testing import CliRunner

import storix.cli as cli_entry

from storix import Storix
from storix.backends import MemoryBackend
from storix.cli import app as cli
from storix.cli.state import reset_session
from storix.constants import DEFAULT_SOURCE_READ_SIZE


runner = CliRunner()


@pytest.fixture(autouse=True)
def fresh_session(tmp_path, monkeypatch) -> Generator[None]:
    """Each test gets a clean in-memory session and no ambient config.

    The prefs loader searches upward from the cwd, so a test run from a
    checkout would otherwise inherit the repo's own ``[tool.storix.cli]``.
    Anchor it at an empty directory instead.
    """
    from storix.cli.config import load_prefs

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path / 'xdg'))
    monkeypatch.delenv('STORIX_CLI_ICONS', raising=False)
    load_prefs.cache_clear()
    reset_session()
    cli.use_fs(Storix(MemoryBackend()))
    yield
    load_prefs.cache_clear()


def run(*args: str):
    return runner.invoke(cli.app, list(args))


def test_entrypoint_reports_missing_cli_extra(monkeypatch):
    def import_missing_cli(_name: str):
        error = ModuleNotFoundError(name='click')
        raise error

    monkeypatch.setattr(cli_entry, 'import_module', import_missing_cli)

    with pytest.raises(SystemExit) as exc_info:
        cli_entry.main()

    message = str(exc_info.value)
    assert 'cli extra not installed' in message
    assert 'storix[cli]' in message  # the install remedy names the extra


def test_entrypoint_does_not_mask_application_import_errors(monkeypatch):
    def import_broken_app(_name: str):
        error = ModuleNotFoundError(name='application_dependency')
        raise error

    monkeypatch.setattr(cli_entry, 'import_module', import_broken_app)

    with pytest.raises(ModuleNotFoundError) as exc_info:
        cli_entry.main()

    assert exc_info.value.name == 'application_dependency'


def test_mkdir_touch_ls_round_trip():
    assert run('mkdir', '-p', '/docs/sub').exit_code == 0
    assert run('touch', '/docs/a.txt', '/docs/.hidden').exit_code == 0

    listing = run('ls', '/docs')
    assert 'a.txt' in listing.stdout
    assert 'sub' in listing.stdout
    assert '.hidden' not in listing.stdout  # hidden unless -a

    assert '.hidden' in run('ls', '-a', '/docs').stdout


def test_echo_and_cat():
    run('echo', 'hello', '-f', '/a.txt')
    run('echo', 'world', '-a', '-f', '/a.txt')
    out = run('cat', '/a.txt')
    assert out.stdout == 'hello\nworld\n'


def test_cd_persists_across_invocations():
    run('mkdir', '/docs')
    run('cd', '/docs')
    run('touch', 'rel.txt')  # relative to the persisted cwd
    assert run('pwd').stdout.strip() == '/docs'
    assert 'rel.txt' in run('ls').stdout


def test_mv_cp_rm():
    run('echo', 'x', '-f', '/a.txt')
    run('mkdir', '/archive')
    run('cp', '/a.txt', '/b.txt')
    assert run('exists', '/b.txt').exit_code == 0
    run('mv', '/a.txt', '/b.txt', '/archive')
    assert run('exists', '/archive/a.txt', '/archive/b.txt').exit_code == 0

    assert run('rm', '/archive').exit_code == 1  # directory needs -r
    assert run('rm', '-r', '/archive').exit_code == 0
    assert run('exists', '/archive').exit_code == 1


def test_rmdir_is_strict():
    run('mkdir', '/d')
    run('touch', '/d/f.txt')
    assert run('rmdir', '/d').exit_code == 1  # non-empty
    run('rm', '/d/f.txt')
    assert run('rmdir', '/d').exit_code == 0


def test_missing_path_exits_nonzero_with_message():
    result = run('cat', '/nope.txt')
    assert result.exit_code == 1
    assert 'does not exist' in result.stderr  # errors go to stderr


def test_du_and_stat():
    run('echo', '12345', '-f', '/a.txt')  # 6 bytes incl newline
    assert run('du', '/a.txt').stdout.startswith('6')
    assert 'File: a.txt' in run('stat', '/a.txt').stdout


def _small_project() -> None:
    """/proj/src/main.py (5 bytes) and /proj/readme.txt (3 bytes)."""
    run('mkdir', '-p', '/proj/src')
    run('echo', 'aaaa', '-f', '/proj/src/main.py')  # 'aaaa\n' -> 5 bytes
    run('echo', 'bb', '-f', '/proj/readme.txt')  # 'bb\n' -> 3 bytes


def _du_lines(out: str) -> list[list[str]]:
    """Non-empty du lines split into (size, path); tolerant of tab/space."""
    return [line.split() for line in out.splitlines() if line.strip()]


def test_du_default_breakdown_lists_subdirs_with_total_last():
    _small_project()
    lines = _du_lines(run('du', '/proj').stdout)

    # every subdirectory appears with its cumulative size
    assert ['5', '/proj/src'] in lines
    # the argument's grand total is the last line
    assert lines[-1] == ['8', '/proj']
    # default is directories only, no file lines
    assert all(not cols[-1].endswith('.py') for cols in lines)


def test_du_summary_is_total_only():
    _small_project()
    lines = _du_lines(run('du', '-s', '/proj').stdout)

    assert lines == [['8', '/proj']]


def test_du_all_includes_files():
    _small_project()
    out = run('du', '-a', '/proj').stdout

    assert '/proj/src/main.py' in out
    assert '/proj/readme.txt' in out


def test_find_by_name_and_type():
    _small_project()

    by_name = run('find', '/proj', '--name', '*.py').stdout
    assert '/proj/src/main.py' in by_name
    assert 'readme.txt' not in by_name

    dirs = run('find', '/proj', '--type', 'd').stdout
    assert '/proj/src' in dirs
    assert 'main.py' not in dirs


def test_tree_level_caps_depth():
    _small_project()
    out = run('tree', '-L', '1', '/proj').stdout

    assert 'src' in out
    assert 'main.py' not in out  # depth 2 is not shown at level 1


def test_tree_long_shows_sizes():
    run('mkdir', '/proj')
    run('echo', 'aaaa', '-f', '/proj/main.py')  # 5 bytes
    out = run('tree', '-l', '/proj').stdout

    assert 'main.py' in out
    assert '5' in out  # the file's size column


def test_tree_delegates_traversal_to_core_walk(monkeypatch):
    """tree renders over one core ``walk`` (ADR 0028): it maps -L onto
    ``max_depth`` and never recurses over ``scandir`` itself."""
    _small_project()
    walk_calls: list[dict] = []
    real_walk = Storix.walk

    def counting_walk(self, *args, **kwargs):
        walk_calls.append(kwargs)
        return real_walk(self, *args, **kwargs)

    def forbidden_scandir(self, *args, **kwargs):
        message = 'tree must not traverse via scandir'
        raise AssertionError(message)

    monkeypatch.setattr(Storix, 'walk', counting_walk)
    monkeypatch.setattr(Storix, 'scandir', forbidden_scandir)

    result = run('tree', '-L', '2', '/proj')

    assert result.exit_code == 0
    assert 'main.py' in result.stdout
    assert len(walk_calls) == 1  # one core walk carries the traversal
    assert walk_calls[0].get('max_depth') == 2


def test_tree_streams_lines_while_walking(monkeypatch):
    """tree prints progressively while the walk runs: at least one line
    lands before the deepest directory is even listed, instead of the
    whole traversal completing first (unix tree streams the same way)."""
    # Given a 3-level tree on a backend that logs every list_dir call
    events: list[tuple[str, str]] = []

    class RecordingBackend(MemoryBackend):
        def list_dir(self, path):
            events.append(('list', str(path)))
            return super().list_dir(path)

    cli.use_fs(Storix(RecordingBackend()))
    run('mkdir', '-p', '/a/b/c')
    run('touch', '/a/b/c/f.txt')

    class RecordingConsole:
        def print(self, *args, **kwargs):
            events.append(('print', str(args[0]) if args else ''))

    monkeypatch.setattr(cli, 'console', RecordingConsole())
    events.clear()

    # When tree renders the whole hierarchy
    assert run('tree', '/').exit_code == 0

    # Then some output precedes the deepest directory's listing
    first_print = next(i for i, (kind, _) in enumerate(events) if kind == 'print')
    deepest_list = events.index(('list', '/a/b/c'))
    assert first_print < deepest_list


def test_find_streams_lines_while_walking(monkeypatch):
    """find prints progressively while the walk runs: at least one line
    lands before the deepest directory is even listed (unix find streams)."""
    events: list[tuple[str, str]] = []

    class RecordingBackend(MemoryBackend):
        def list_dir(self, path):
            events.append(('list', str(path)))
            return super().list_dir(path)

    cli.use_fs(Storix(RecordingBackend()))
    run('mkdir', '-p', '/a/b/c')
    run('touch', '/a/b/c/f.txt')

    class RecordingConsole:
        def print(self, *args, **kwargs):
            events.append(('print', str(args[0]) if args else ''))

    monkeypatch.setattr(cli, 'console', RecordingConsole())
    events.clear()

    assert run('find', '/').exit_code == 0

    first_print = next(i for i, (kind, _) in enumerate(events) if kind == 'print')
    deepest_list = events.index(('list', '/a/b/c'))
    assert first_print < deepest_list


def test_data_url_works_but_presigned_needs_capability():
    run('echo', 'hi', '-f', '/a.txt')
    assert run('url', '--data', '/a.txt').stdout.startswith('data:')
    unsupported = run('url', '/a.txt')  # memory has no presigned_urls
    assert unsupported.exit_code == 1
    assert 'presigned_urls' in unsupported.stderr


def test_provision_on_memory_reports_already_present():
    # memory's root is always present: provision is an idempotent no-op
    result = run('provision')
    assert result.exit_code == 0
    assert 'already present' in result.stdout


def test_provision_unsupported_on_opendal_points_at_provider_tooling():
    from storix.backends import S3Backend

    # an opendal backend is data-plane only; construction is offline
    # (credentials are validated on first I/O, which provision never reaches)
    cli.use_fs(Storix(S3Backend('bucket', region='us-east-1')))
    result = run('provision')
    assert result.exit_code == 1
    assert 'control-plane' in result.stderr  # points at provider tooling


def test_apply_layers_composition_and_lookup():
    from storix import CacheLayer, SandboxLayer
    from storix.cli.state import apply_layers, cache_layer, layer_summary

    base = Storix(MemoryBackend())
    base.mkdir('/jail')  # a sandbox root must exist: sx verifies it up front
    fs = apply_layers(base, cache=True, cache_ttl=None, sandbox='/jail')
    # sandbox innermost, cache outermost
    assert isinstance(fs.backend, CacheLayer)
    assert isinstance(fs.backend._inner, SandboxLayer)
    assert cache_layer(fs) is fs.backend
    summary = layer_summary(fs)
    assert summary is not None
    assert 'cache' in summary and 'sandbox' in summary
    assert 'InMemoryCacheStore' in summary  # names the store backing the cache


def test_apply_layers_none_is_passthrough():
    from storix.cli.state import apply_layers, cache_layer, layer_summary

    base = Storix(MemoryBackend())
    fs = apply_layers(base, cache=False, cache_ttl=None, sandbox=None)
    assert fs is base
    assert cache_layer(fs) is None
    assert layer_summary(fs) is None


def test_base_backend_surfaces_the_provider_under_the_stack():
    from storix.cli.state import apply_layers

    base = Storix(MemoryBackend())
    base.mkdir('/jail')
    fs = apply_layers(base, cache=True, cache_ttl=None, sandbox='/jail')

    # the real provider, not the outermost layer the shell would otherwise name
    assert type(fs.base_backend).__name__ == 'MemoryBackend'


def test_url_expire_flag_is_accepted():
    from storix import DataUrlLayer

    cli.use_fs(Storix(DataUrlLayer(MemoryBackend())))
    run('echo', 'hi', '-f', '/a.txt')
    out = run('url', '/a.txt', '--expire', '60')
    assert out.exit_code == 0
    assert out.stdout.strip().startswith('data:')  # data URLs ignore expiry


@pytest.fixture
def prefs_from(tmp_path, monkeypatch):
    """Point prefs loading at a fresh project dir holding one storix.toml."""
    from storix.cli.config import load_prefs

    def write(body: str):
        (tmp_path / 'storix.toml').write_text(body)
        monkeypatch.chdir(tmp_path)
        load_prefs.cache_clear()

    yield write
    load_prefs.cache_clear()


def test_config_layers_build_the_stack(prefs_from):
    from storix.cli.state import cache_layer, stack_from_prefs

    prefs_from('[cli]\n[[cli.layers]]\nname = "cache"\nttl = 5\n')

    fs = stack_from_prefs(Storix(MemoryBackend()))

    assert cache_layer(fs) is not None  # configured cache is live


def test_config_layers_unknown_name_dies_with_the_known_set(prefs_from):
    from storix.cli.state import stack_from_prefs

    prefs_from('[cli]\n[[cli.layers]]\nname = "warp"\n')

    with pytest.raises(SystemExit) as exc_info:
        stack_from_prefs(Storix(MemoryBackend()))

    assert 'warp' in str(exc_info.value)
    assert 'cache' in str(exc_info.value)  # the error names the known layers


def test_connection_key_in_the_cli_table_is_rejected_as_unknown(prefs_from):
    from storix.cli.config import load_prefs

    # provider tables are now the home for connection config (ADR 0031); an
    # account_name inside [cli] is simply an unknown preference now.
    prefs_from("[cli]\naccount_name = 'acme'\n")

    with pytest.raises(SystemExit) as exc_info:
        load_prefs()

    assert 'account_name' in str(exc_info.value)  # names the offending key


def test_configured_provider_opens_that_backend(prefs_from):
    from storix.cli.state import build_base

    prefs_from("[cli]\nprovider = 'memory'\n")

    assert type(build_base().base_backend).__name__ == 'MemoryBackend'
    # an explicit -p still wins over the configured default
    assert type(build_base('local').base_backend).__name__ == 'LocalBackend'


def test_sandbox_root_that_is_not_there_fails_fast(prefs_from):
    from storix.cli.state import apply_layers

    prefs_from('[cli]\n')
    fs = Storix(MemoryBackend())

    with pytest.raises(SystemExit) as exc_info:
        apply_layers(fs, cache=False, cache_ttl=None, sandbox='/videos')

    # names the real root, not the '/' the jail would rescope it to
    assert '/videos' in str(exc_info.value)
    assert 'does not exist' in str(exc_info.value)


def test_unknown_preference_is_rejected_with_the_known_set(prefs_from):
    from storix.cli.config import load_prefs

    prefs_from('[cli]\nicnos = true\n')  # typo

    with pytest.raises(SystemExit) as exc_info:
        load_prefs()

    assert 'icons' in str(exc_info.value)


def test_ls_long_format_outputs_kind_size_date_time():
    run('echo', 'hello world', '-f', '/a.txt')
    run('mkdir', '/docs')
    out = run('ls', '-l').stdout
    lines = out.splitlines()
    assert len(lines) == 2
    assert 'a.txt' in out
    assert 'docs' in out


def test_ls_long_format_on_a_file_lists_that_file(exit_keys):
    """Like unix ls, `ls -l FILE` reports the file, not FILE/FILE."""
    run('echo', 'hello world', '-f', '/a.txt')

    out = run('ls', '-l', '/a.txt')

    assert out.exit_code == 0
    assert 'a.txt' in out.stdout
    assert 'a.txt/a.txt' not in out.stdout


def test_ls_sorts_case_insensitively_like_coreutils_and_eza():
    for name in ('Zebra.txt', 'a.txt', 'apple.txt', 'B.md'):
        run('touch', f'/{name}')

    listed = run('ls').stdout.split()

    assert listed == ['a.txt', 'apple.txt', 'B.md', 'Zebra.txt']


def _tree_names(out: str) -> list[str]:
    """Entry names from tree output, in printed order (root and count dropped)."""
    return [
        line.split('── ', 1)[1].strip() for line in out.splitlines() if '── ' in line
    ]


def _by_size() -> None:
    """/big.txt (9 bytes), /mid.txt (5), /small.txt (2) and /d/."""
    run('echo', 'aaaaaaaa', '-f', '/big.txt')
    run('echo', 'aaaa', '-f', '/mid.txt')
    run('echo', 'a', '-f', '/small.txt')
    run('mkdir', '/d')


def _sizeless_session() -> list[str]:
    """Install a session whose listings omit sizes, and log every stat path.

    Mirrors a cloud listing that reports names and kinds only, which is
    what makes a size sort's stats (and their reuse) observable; memory
    listings carry the size for free and would hide both.
    """
    stats: list[str] = []

    class SizelessBackend(MemoryBackend):
        def list_dir(self, path):
            for entry in super().list_dir(path):
                yield entry._replace(size=None)

        def stat(self, path):
            stats.append(str(path))
            return super().stat(path)

    cli.use_fs(Storix(SizelessBackend()))
    return stats


def _stamp_mtimes(*oldest_first: str) -> None:
    """Install a session whose mtimes follow the given order, oldest first.

    Scripted rather than clock-driven: two writes can land in the same tick
    on a coarse timer, and a tie would leave the expected order ambiguous.
    """
    stamps = {
        name: dt.datetime(2026, 1, 1, tzinfo=dt.UTC) + dt.timedelta(minutes=minute)
        for minute, name in enumerate(oldest_first)
    }

    class StampedBackend(MemoryBackend):
        def stat(self, path):
            raw = super().stat(path)
            stamp = stamps.get(path.name)
            return raw if stamp is None else dataclasses.replace(raw, modified=stamp)

    cli.use_fs(Storix(StampedBackend()))


def test_ls_sorts_by_size_largest_first_with_directories_last():
    """Given files of different sizes beside a directory,
    When ls sorts by size,
    Then the largest file leads and the directory (no size of its own) trails."""
    _by_size()

    listed = run('ls', '--sort', 'size').stdout.split()

    assert listed == ['big.txt', 'mid.txt', 'small.txt', 'd/']


def test_ls_sorts_by_size_reusing_the_long_listing_stat_batch():
    """Given a listing that carries no sizes, so ls -l has to batch a stat per entry,
    When that long listing is sorted by size,
    Then the batch is reused instead of a second pass over the same entries."""
    stats = _sizeless_session()
    _by_size()

    stats.clear()
    unsorted_ = run('ls', '-l')
    baseline = len(stats)
    stats.clear()
    by_size = run('ls', '-l', '--sort', 'size')

    assert unsorted_.exit_code == by_size.exit_code == 0
    assert baseline > 0  # the long listing does stat every entry
    assert len(stats) == baseline


def test_ls_stats_per_entry_only_when_the_sort_asks_for_it():
    """Given a listing that carries no sizes,
    When a plain ls runs and then the same listing is sorted by size,
    Then only the size sort pays for the per-entry stats it needs."""
    stats = _sizeless_session()
    _by_size()

    stats.clear()
    run('ls')
    plain = [path for path in stats if path.endswith('.txt')]
    stats.clear()
    run('ls', '--sort', 'size')
    by_size = [path for path in stats if path.endswith('.txt')]

    assert plain == []
    assert len(by_size) == 3  # the three files, in one batch, never /d


def test_ls_sorts_by_modification_time_newest_first():
    """Given entries written at known, distinct times,
    When ls sorts by time, whether spelled --sort time or the -t shorthand,
    Then the newest entry leads in both spellings."""
    _stamp_mtimes('old.txt', 'middle.txt', 'new.txt')
    for name in ('middle.txt', 'new.txt', 'old.txt'):
        run('touch', f'/{name}')

    by_option = run('ls', '--sort', 'time').stdout.split()

    assert by_option == ['new.txt', 'middle.txt', 'old.txt']
    assert run('ls', '-t').stdout.split() == by_option


def test_ls_reverse_inverts_whichever_order_was_chosen():
    """Given a listing ordered by name, by time or by size,
    When -r is added,
    Then each order comes out exactly inverted."""
    _stamp_mtimes('small.txt', 'big.txt', 'mid.txt')
    _by_size()

    for order in (('ls',), ('ls', '-t'), ('ls', '--sort', 'size')):
        forward = run(*order).stdout.split()

        assert run(*order, '-r').stdout.split() == forward[::-1]


def test_tree_sorts_siblings_by_size_largest_first_with_directories_last():
    """Given a directory holding files of different sizes and a subdirectory,
    When tree sorts siblings by size,
    Then the largest file leads and the subdirectory trails, as in ls."""
    _by_size()

    listed = _tree_names(run('tree', '-L', '1', '/', '--sort', 'size').stdout)

    assert listed == ['big.txt', 'mid.txt', 'small.txt', 'd']


def test_tree_sorts_siblings_by_modification_time_newest_first():
    """Given siblings written at known, distinct times,
    When tree sorts them by time,
    Then the newest sibling leads."""
    _stamp_mtimes('old.txt', 'middle.txt', 'new.txt')
    for name in ('middle.txt', 'new.txt', 'old.txt'):
        run('touch', f'/{name}')

    listed = _tree_names(run('tree', '--sort', 'time', '/').stdout)

    assert listed == ['new.txt', 'middle.txt', 'old.txt']


def test_tree_reverse_inverts_the_sibling_order():
    """Given siblings ordered by name or by size,
    When -r is added,
    Then each order comes out exactly inverted, as in ls."""
    _by_size()

    for order in (('tree', '-L', '1', '/'), ('tree', '-L', '1', '/', '--sort', 'size')):
        forward = _tree_names(run(*order).stdout)

        assert _tree_names(run(*order, '-r').stdout) == forward[::-1]


@pytest.mark.parametrize('command', ['ls', 'tree'])
def test_listing_commands_reject_an_unknown_sort_key(command):
    """Given a sort key neither listing command knows,
    When it is passed to either of them,
    Then the invocation is rejected and the message names the known keys."""
    result = run(command, '--sort', 'bogus')

    assert result.exit_code != 0
    assert 'bogus' in result.output  # the value that was rejected
    # asserted token by token: the exact phrasing belongs to click, and the
    # panel wraps it at the terminal width
    assert all(key in result.output for key in ('name', 'time', 'size'))


def test_cat_reproduces_file_bytes_exactly():
    """`sx cat f > copy` must be byte-identical: no wrapping, no tab expansion."""
    long_line = 'x' * 300
    run('echo', long_line, '-f', '/long.txt')
    run('echo', 'a\tb   ', '-f', '/ws.txt')

    assert run('cat', '/long.txt').stdout == f'{long_line}\n'
    assert run('cat', '/ws.txt').stdout == 'a\tb   \n'


def test_cat_streams_rather_than_buffering_whole_files(monkeypatch):
    """cat renders over the core's bounded ``stream`` (never ``cat``), so a
    file larger than memory is printable."""
    run('echo', 'hello', '-f', '/a.txt')

    def forbidden_cat(self, *args, **kwargs):
        message = 'sx cat must stream, not materialize the whole file'
        raise AssertionError(message)

    monkeypatch.setattr(Storix, 'cat', forbidden_cat)

    result = run('cat', '/a.txt')

    assert result.exit_code == 0
    assert result.stdout == 'hello\n'


def test_cat_names_a_missing_file_before_writing_anything():
    run('echo', 'hello', '-f', '/a.txt')

    result = run('cat', '/a.txt', '/nope.txt')

    assert result.exit_code == 1
    assert 'does not exist' in result.stderr


def test_echo_prints_text_literally():
    """Text is data, not rich markup - unix echo never interprets it."""
    assert run('echo', '[bold]hi[/bold]').stdout == '[bold]hi[/bold]\n'

    unbalanced = run('echo', 'a[/]b')  # a lone closing tag crashed rich

    assert unbalanced.exit_code == 0
    assert unbalanced.stdout == 'a[/]b\n'


class _Pipe(io.BytesIO):
    """Stand-in for the process pipe, with its reads on the record.

    ``CliRunner`` installs any ``input`` that can ``read`` as the buffer
    under the text layer it puts on ``sys.stdin``, so this object is
    exactly what the command pulls from, and it answers ``isatty`` for the
    whole session.
    """

    def __init__(self, data: bytes = b'', *, tty: bool = False) -> None:
        super().__init__(data)
        self.reads: list[int | None] = []
        self._tty = tty

    def isatty(self) -> bool:
        return self._tty

    def read(self, size: int | None = -1, /) -> bytes:
        self.reads.append(size)
        return super().read(size)


def test_echo_appends_a_newline_without_n():
    """Given no -n, when echoing to either sink, then one newline ends it."""
    assert run('echo', 'hi').stdout_bytes == b'hi\n'

    run('echo', 'hi', '-f', '/a.txt')

    assert run('cat', '-b', '/a.txt').stdout_bytes == b'hi\n'


def test_echo_n_prints_without_the_trailing_newline():
    """Given -n, when printing, then the text stands alone, like echo -n."""
    assert run('echo', '-n', 'hi').stdout_bytes == b'hi'


def test_echo_n_writes_a_file_without_the_trailing_newline():
    """Given -n and -f, when writing, then the file holds the text only.

    The gap this closes: no other flag produced a file whose last byte is
    not a newline.
    """
    assert run('echo', '-n', 'hi', '-f', '/a.txt').exit_code == 0

    assert run('cat', '-b', '/a.txt').stdout_bytes == b'hi'


def test_echo_keeps_a_lone_dash_literal():
    """Given a dash as the text, when echoing, then a dash is printed.

    The text argument is content, not a file name, so the usual stdin
    spelling would cost the only way to write a dash.
    """
    assert run('echo', '-').stdout_bytes == b'-\n'


def test_echo_writes_a_pipe_verbatim():
    """Given piped bytes and no text, when -f is given, then they are stored.

    Arbitrary bytes are not text: nothing decodes them, and nothing
    appends the newline that a text operand would get.
    """
    payload = b'\xff\xfe\x00 not utf-8'

    result = runner.invoke(cli.app, ['echo', '-f', '/raw.bin'], input=_Pipe(payload))

    assert result.exit_code == 0
    assert run('cat', '-b', '/raw.bin').stdout_bytes == payload


def test_echo_prints_a_pipe_verbatim():
    """Given piped bytes and no -f, when echoing, then stdout gets them raw."""
    payload = b'\x00\x9c binary'

    result = runner.invoke(cli.app, ['echo'], input=_Pipe(payload))

    assert result.exit_code == 0
    assert result.stdout_bytes == payload


def test_echo_n_leaves_piped_data_unchanged():
    """Given -n on a pipe, when writing, then the bytes match the pipe.

    Piped data never grows a newline, so -n asks for what already holds.
    """
    payload = b'ends without a newline'

    result = runner.invoke(
        cli.app, ['echo', '-n', '-f', '/raw.bin'], input=_Pipe(payload)
    )

    assert result.exit_code == 0
    assert run('cat', '-b', '/raw.bin').stdout_bytes == payload


def test_echo_pulls_a_large_pipe_in_bounded_reads():
    """Given a pipe past one read size, when written, then reads stay bounded.

    A pipe larger than memory has to reach the backend in pieces, so the
    stream itself is handed over: every pull asks for a fixed size, and a
    materializing ``read()`` or ``read(-1)`` would show up here as an
    unbounded request.
    """
    payload = b'p' * (2 * DEFAULT_SOURCE_READ_SIZE + 7)
    pipe = _Pipe(payload)

    result = runner.invoke(cli.app, ['echo', '-f', '/big.bin'], input=pipe)

    assert result.exit_code == 0
    pulls = [size for size in pipe.reads if size]  # the runner probes with read(0)
    assert len(pulls) > 2
    assert all(size == DEFAULT_SOURCE_READ_SIZE for size in pulls)
    assert run('cat', '-b', '/big.bin').stdout_bytes == payload


def test_echo_without_text_at_a_terminal_prints_one_newline():
    """Given a terminal, when no text is given, then only a newline prints.

    A terminal is the user typing, not data: the REPL would otherwise
    swallow the next prompt line, and unix echo with no operands prints
    just the newline.
    """
    pipe = _Pipe(b'not data', tty=True)

    result = runner.invoke(cli.app, ['echo'], input=pipe)

    assert result.stdout_bytes == b'\n'
    assert not [size for size in pipe.reads if size]  # the runner probes read(0)


def test_tree_on_a_file_counts_one_file_and_no_directory():
    run('echo', 'hello', '-f', '/a.txt')

    out = run('tree', '/a.txt').stdout

    assert '0 directories, 1 file' in out


def test_icons_lookup_and_namespace():
    from storix.cli.icons import Icons, lookup_entry_decor

    # Check Icons constants
    assert Icons.LANG_PYTHON == '\ue606'
    assert Icons.FOLDER == '\ue5ff'
    assert Icons.FOLDER_OPEN == '\uf115'

    # Directory lookup
    assert lookup_entry_decor('src', is_dir=True)[0] == '\U000f08de'

    assert (
        lookup_entry_decor('random', is_dir=True, dir_state='closed')[0] == Icons.FOLDER
    )
    assert (
        lookup_entry_decor('random', is_dir=True, dir_state='empty')[0]
        == Icons.FOLDER_OPEN
    )

    # Extension lookup
    assert lookup_entry_decor('script.py', is_dir=False) == (Icons.LANG_PYTHON, 'green')
    assert lookup_entry_decor('main.rs', is_dir=False) == (Icons.LANG_RUST, 'green')
    assert lookup_entry_decor('archive.tar.gz', is_dir=False) == (
        Icons.COMPRESSED,
        'red',
    )

    # Filename match
    assert lookup_entry_decor('Dockerfile', is_dir=False) == (Icons.DOCKER, 'cyan')
    assert lookup_entry_decor('.gitignore', is_dir=False) == (Icons.GIT, 'cyan')

    # Generic fallback
    assert lookup_entry_decor('unknown_file', is_dir=False) == (Icons.FILE, '')


def test_push_and_pull_user_tilde_expansion(monkeypatch, tmp_path):
    monkeypatch.setenv('HOME', str(tmp_path))
    local_file = tmp_path / 'home_file.txt'
    local_file.write_text('tilde content')

    # Push with ~/home_file.txt
    res_push = run('push', '~/home_file.txt', '/remote_tilde.txt')
    assert res_push.exit_code == 0
    assert run('cat', '/remote_tilde.txt').stdout == 'tilde content'

    # Pull with ~/pulled_tilde.txt
    res_pull = run('pull', '/remote_tilde.txt', '~/pulled_tilde.txt')
    assert res_pull.exit_code == 0
    assert (tmp_path / 'pulled_tilde.txt').read_text() == 'tilde content'


def test_push_and_pull_paths_with_spaces(tmp_path):
    space_dir = tmp_path / 'Black Bird'
    space_dir.mkdir()
    (space_dir / 'episode 1.mp4').write_text('video stream')

    # Push local directory with spaces in path
    res_push = run('push', str(space_dir), '/remote series/Black Bird')
    assert res_push.exit_code == 0
    assert (
        run('cat', '/remote series/Black Bird/episode 1.mp4').stdout == 'video stream'
    )

    # Pull back to local path with spaces
    pull_dest = tmp_path / 'pulled series' / 'Black Bird'
    res_pull = run('pull', '/remote series/Black Bird', str(pull_dest))
    assert res_pull.exit_code == 0
    assert (pull_dest / 'episode 1.mp4').read_text() == 'video stream'


def test_local_completions_space_escaping(monkeypatch, tmp_path):
    from storix.cli.shell import _escape_shell_path, _get_local_completions

    assert _escape_shell_path('Black Bird') == 'Black\\ Bird'

    monkeypatch.setattr('pathlib.Path.cwd', lambda: tmp_path)
    (tmp_path / 'Black Bird').mkdir()

    completions = list(_get_local_completions('Bl'))
    assert len(completions) == 1
    assert completions[0].text == 'Black\\ Bird/'


def test_expand_alias_subcommand_expansion():
    from storix.cli.config import expand_alias

    aliases = {'lt': 'tree -L 1', 'la': 'ls -a'}
    assert expand_alias(['lt', '/docs'], aliases) == ['tree', '-L', '1', '/docs']
    assert expand_alias(['sx', '-p', 'memory', 'lt'], aliases) == [
        'sx',
        '-p',
        'memory',
        'tree',
        '-L',
        '1',
    ]


def test_expand_alias_does_not_expand_positional_arguments():
    from storix.cli.config import expand_alias

    aliases = {'lt': 'tree -L 1'}
    # 'lt' is a positional argument to 'touch', so it must NOT be expanded
    assert expand_alias(['touch', 'lt'], aliases) == ['touch', 'lt']


def test_expand_alias_handles_self_aliasing_and_cycles():
    from storix.cli.config import expand_alias

    # Self-aliasing: 'ls' -> 'ls -a'
    assert expand_alias(['ls', '/docs'], {'ls': 'ls -a'}) == ['ls', '-a', '/docs']

    # Cycle: 'a' -> 'b' and 'b' -> 'a'
    assert expand_alias(['a'], {'a': 'b', 'b': 'a'}) == ['a']


def test_config_alias_parsing(prefs_from):
    from storix.cli.config import load_prefs

    prefs_from('[cli.alias]\nla = "ls -a"\nlt = "tree -L 2"\n')
    prefs = load_prefs()
    assert prefs.alias == {'la': 'ls -a', 'lt': 'tree -L 2'}


def test_config_top_level_alias_and_aliases_parsing(prefs_from):
    from storix.cli.config import load_prefs

    # Top level alias section in storix.toml
    prefs_from('[alias]\nlt = "tree"\n')
    assert load_prefs().alias == {'lt': 'tree'}

    # Top level aliases section in storix.toml
    prefs_from('[aliases]\nla = "ls -a"\n')
    assert load_prefs().alias == {'la': 'ls -a'}

    # Nested cli.aliases table in storix.toml
    prefs_from('[cli.aliases]\nll = "ls -l"\n')
    assert load_prefs().alias == {'ll': 'ls -l'}


def test_push_and_pull_and_legacy_aliases(tmp_path):
    local_file = tmp_path / 'sample.txt'
    local_file.write_text('hello push pull')

    # Push local file to backend
    res_push = run('push', str(local_file), '/remote_sample.txt')
    assert res_push.exit_code == 0
    assert run('cat', '/remote_sample.txt').stdout == 'hello push pull'

    # Pull backend file back to local file
    out_file = tmp_path / 'pulled.txt'
    res_pull = run('pull', '/remote_sample.txt', str(out_file))
    assert res_pull.exit_code == 0
    assert out_file.read_text() == 'hello push pull'


def test_completion_context_parsing():
    from storix.cli.shell import _parse_completion_context

    # command-name position
    assert _parse_completion_context('push') == ('push', 0, 'push')
    # first argument
    assert _parse_completion_context('push ') == ('push', 1, '')
    assert _parse_completion_context('push sr') == ('push', 1, 'sr')
    # second argument, mid-word (this already worked)
    assert _parse_completion_context('push sr rem') == ('push', 2, 'rem')
    assert _parse_completion_context('pull ') == ('pull', 1, '')
    # regression: an empty word after a trailing space must count every
    # completed token, not collapse to index 1 (that sent push<2>/pull<2>
    # completion to the wrong side).
    assert _parse_completion_context('push sr ') == ('push', 2, '')
    assert _parse_completion_context('pull rem ') == ('pull', 2, '')
    assert _parse_completion_context('cp a b ') == ('cp', 3, '')
    # an escaped trailing space stays within the current token
    assert _parse_completion_context('cat my\\ ') == ('cat', 1, 'my ')


def test_shell_help_is_derived_from_the_registered_commands(capsys):
    """The REPL's command list cannot drift from the real command set: a
    hand-written one advertised the hidden `provider` alias and never
    learned about `find`."""
    from typer.main import get_command

    from storix.cli import shell

    shell._help(get_command(cli.app).commands)
    listed = capsys.readouterr().out

    assert 'provider' not in listed  # hidden deprecated alias for whereami
    for command in ('ls', 'find', 'whereami', 'doctor', 'config', 'exit'):
        assert command in listed


def test_shell_history_persists_between_sessions(tmp_path, monkeypatch):
    from storix.cli import shell

    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path))

    history = shell._history()
    history.append_string('pwd')

    assert 'pwd' in list(shell._history().load_history_strings())


def test_push_pull_completion_side(monkeypatch):
    """push<1>/pull<2> complete from the local host, push<2>/pull<1> remote."""
    from prompt_toolkit.completion import CompleteEvent, Completion
    from prompt_toolkit.document import Document

    from storix.cli import shell

    def fake_local(word):
        yield Completion('LOCAL')

    def fake_remote(word):
        yield Completion('REMOTE')

    monkeypatch.setattr(shell, '_get_local_completions', fake_local)
    monkeypatch.setattr(shell, '_get_remote_completions', fake_remote)

    completer = shell._ShellCompleter({'push': '', 'pull': ''})

    def side(text: str) -> str | None:
        doc = Document(text, len(text))
        comps = list(completer.get_completions(doc, CompleteEvent()))
        return comps[0].text if comps else None

    assert side('push ') == 'LOCAL'  # push arg1 -> local host
    assert side('push src ') == 'REMOTE'  # push arg2 -> remote backend
    assert side('pull ') == 'REMOTE'  # pull arg1 -> remote backend
    assert side('pull remote ') == 'LOCAL'  # pull arg2 -> local host


def test_push_and_pull_directory_recursive(tmp_path):
    local_dir = tmp_path / 'my_dataset'
    local_dir.mkdir()
    (local_dir / 'a.txt').write_text('content A')
    sub = local_dir / 'sub'
    sub.mkdir()
    (sub / 'b.txt').write_text('content B')

    # Push directory to remote
    res_push = run('push', str(local_dir), '/remote_dir')
    assert res_push.exit_code == 0
    assert run('cat', '/remote_dir/a.txt').stdout == 'content A'
    assert run('cat', '/remote_dir/sub/b.txt').stdout == 'content B'

    # Pull remote directory back to local
    dest_dir = tmp_path / 'downloaded_dataset'
    res_pull = run('pull', '/remote_dir', str(dest_dir))
    assert res_pull.exit_code == 0
    assert (dest_dir / 'a.txt').read_text() == 'content A'
    assert (dest_dir / 'sub' / 'b.txt').read_text() == 'content B'


def test_push_directory_creates_each_unique_remote_parent_once(tmp_path, monkeypatch):
    # Given a tree whose five files share only three distinct directories
    local_dir = tmp_path / 'tree'
    (local_dir / 'sub' / 'deep').mkdir(parents=True)
    (local_dir / 'a.txt').write_text('a')
    (local_dir / 'b.txt').write_text('b')
    (local_dir / 'sub' / 'c.txt').write_text('c')
    (local_dir / 'sub' / 'd.txt').write_text('d')
    (local_dir / 'sub' / 'deep' / 'e.txt').write_text('e')

    backend = cli.current_fs().backend
    made: list[str] = []
    real_make_dir = backend.make_dir

    def counting_make_dir(path, *, parents):
        made.append(str(path))
        return real_make_dir(path, parents=parents)

    monkeypatch.setattr(backend, 'make_dir', counting_make_dir)

    # When the directory is pushed
    assert run('push', str(local_dir), '/remote_dir').exit_code == 0

    # Then each unique remote directory is created once, none per file
    assert sorted(made) == ['/remote_dir', '/remote_dir/sub', '/remote_dir/sub/deep']


def test_push_and_pull_directory_many_files(tmp_path):
    # Given a nested tree with more files than one thread would carry
    local_dir = tmp_path / 'many'
    contents: dict[str, str] = {}
    for i in range(12):
        rel = f'sub{i % 3}/file{i}.txt'
        target = local_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        contents[rel] = f'payload-{i}-{"x" * i}'
        target.write_text(contents[rel])

    # When pushed, every file lands with its exact bytes
    assert run('push', str(local_dir), '/many').exit_code == 0
    for rel, body in contents.items():
        assert run('cat', f'/many/{rel}').stdout == body

    # And a pull brings every file back byte-identical
    dest = tmp_path / 'back'
    assert run('pull', '/many', str(dest)).exit_code == 0
    for rel, body in contents.items():
        assert (dest / rel).read_text() == body


def test_transfer_progress_totals_interleaved_events(monkeypatch):
    updates: list[int] = []

    class FakeProgress:
        def __init__(self, *columns, **options): ...

        def __enter__(self):
            return self

        def __exit__(self, *exc_info):
            return None

        def add_task(self, description, total=None):
            return 0

        def update(self, task_id, *, completed):
            updates.append(completed)

    monkeypatch.setattr(cli, 'Progress', FakeProgress)

    # Given two files streaming through one progress session
    fs = Storix(MemoryBackend())
    fs.echo('aaaaa', '/a.bin')
    fs.echo('bbb', '/b.bin')

    # When their per-chunk events interleave (round-robin, 1-byte chunks)
    with cli._transfer_progress(fs, 'batch', 8) as obs:
        streams = [
            obs.stream('/a.bin', chunk_size=1),
            obs.stream('/b.bin', chunk_size=1),
        ]
        while streams:
            for stream in list(streams):
                if next(stream, None) is None:
                    streams.remove(stream)

    # Then the bar sums per-path bytes: monotonic, ending at the true total
    assert updates[-1] == 8
    assert updates == sorted(updates)


def test_push_file_creates_missing_remote_parents(tmp_path):
    """Single-file push scaffolds nested destination parents (ADR 0029)."""
    local_file = tmp_path / 'video.mp4'
    local_file.write_text('stream')

    res = run('push', str(local_file), '/storix/demos/video.mp4')

    assert res.exit_code == 0
    assert run('cat', '/storix/demos/video.mp4').stdout == 'stream'


def test_push_file_with_existing_parent_overwrites_destination(tmp_path):
    local_file = tmp_path / 'v.txt'
    local_file.write_text('old')
    run('mkdir', '-p', '/media')
    assert run('push', str(local_file), '/media/v.txt').exit_code == 0

    local_file.write_text('new')
    res = run('push', str(local_file), '/media/v.txt')

    assert res.exit_code == 0
    assert run('cat', '/media/v.txt').stdout == 'new'


def test_push_file_to_root_and_omitted_destination(tmp_path):
    local_file = tmp_path / 'r.txt'
    local_file.write_text('x')

    assert run('push', str(local_file), '/r.txt').exit_code == 0
    assert run('cat', '/r.txt').stdout == 'x'

    run('mkdir', '/inbox')
    run('cd', '/inbox')
    assert run('push', str(local_file)).exit_code == 0  # dst = cwd/r.txt
    assert run('cat', '/inbox/r.txt').stdout == 'x'


def test_push_file_through_a_file_component_dies(tmp_path):
    """unix mkdir -p faithful: a file as the immediate parent is 'already
    exists'; a file deeper in the chain is 'not a directory'."""
    local_file = tmp_path / 'v.txt'
    local_file.write_text('x')
    run('touch', '/blocker')

    parent_is_file = run('push', str(local_file), '/blocker/v.txt')
    assert parent_is_file.exit_code == 1
    assert 'already exists' in parent_is_file.stderr

    ancestor_is_file = run('push', str(local_file), '/blocker/deep/v.txt')
    assert ancestor_is_file.exit_code == 1
    assert 'not a directory' in ancestor_is_file.stderr


def test_push_directory_mkdir_failure_is_not_swallowed(tmp_path, monkeypatch):
    """A real mkdir failure (permission, missing bucket) must die, not be
    suppressed into a confusing downstream write error (ADR 0029)."""
    from storix.errors import PermissionDeniedError

    local_dir = tmp_path / 'tree'
    local_dir.mkdir()
    (local_dir / 'a.txt').write_text('a')

    def denied(path, *, parents):
        raise PermissionDeniedError(path)

    monkeypatch.setattr(cli.current_fs().backend, 'make_dir', denied)

    res = run('push', str(local_dir), '/remote')

    assert res.exit_code == 1
    assert 'permission denied' in res.stderr


def test_debug_flag_prints_the_exception_chain():
    plain = run('cat', '/nope.txt')
    assert 'Traceback' not in plain.stderr  # concise by default

    res = run('--debug', 'cat', '/nope.txt')

    assert res.exit_code == 1
    assert 'Traceback' in res.stderr
    assert 'does not exist' in res.stderr


def test_stopped_pull_reports_130_and_leaves_no_partial_files(tmp_path, monkeypatch):
    """Given a stop asked for, when pulling, then nothing half-written survives."""
    import contextlib
    import threading

    cli.use_fs(Storix(MemoryBackend()))
    run('mkdir', '/d')
    assert run('echo', 'payload', '-f', '/d/a.bin').exit_code == 0
    assert run('echo', 'payload', '-f', '/d/b.bin').exit_code == 0

    @contextlib.contextmanager
    def already_stopped():
        stop = threading.Event()
        stop.set()
        yield stop

    monkeypatch.setattr(cli, '_cancellable', already_stopped)
    out = tmp_path / 'pulled'
    result = run('pull', '/d', str(out))

    assert result.exit_code == 130
    assert 'stopped' in result.stdout
    assert [path for path in out.rglob('*') if path.is_file()] == []


def test_stopped_push_reports_130(tmp_path, monkeypatch):
    """Given a stop asked for, when pushing, then the command reports it."""
    import contextlib
    import threading

    cli.use_fs(Storix(MemoryBackend()))
    source = tmp_path / 'src'
    source.mkdir()
    (source / 'a.bin').write_bytes(b'payload')

    @contextlib.contextmanager
    def already_stopped():
        stop = threading.Event()
        stop.set()
        yield stop

    monkeypatch.setattr(cli, '_cancellable', already_stopped)
    result = run('push', str(source), '/dst')

    assert result.exit_code == 130
    assert 'stopped' in result.stdout


def test_stop_survives_a_broad_exception_handler() -> None:
    """A stop request must not be swallowed by `except Exception` in between."""
    from storix.errors import StorageError, TransferStoppedError

    def a_sink_that_stops() -> None:
        raise TransferStoppedError

    with pytest.raises(TransferStoppedError):
        try:
            a_sink_that_stops()
        except Exception:  # noqa: BLE001 - a layer or SDK in between might
            pytest.fail('a stop request was swallowed by a broad handler')

    assert not issubclass(TransferStoppedError, StorageError)


# --- unified configuration: --version, coordinate flags, --set (ADR 0031) ---


def test_version_prints_the_metadata_version():
    from importlib.metadata import version

    result = run('--version')
    assert result.exit_code == 0
    assert f'sx {version("storix")}' in result.stdout


def test_base_flag_anchors_a_local_session_at_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / 'marker.txt').write_text('x')

    result = run('-p', 'local', '--base', '.', 'ls', '-a')

    assert result.exit_code == 0
    assert 'marker.txt' in result.stdout  # listed cwd, not ~/.storix


def test_foreign_flag_names_the_provider_and_its_accepted_flags():
    from storix.cli.state import build_overrides

    with pytest.raises(SystemExit) as exc:
        build_overrides('local', flags={'bucket': 'x'}, sets=[])

    message = str(exc.value)
    assert "provider 'local'" in message
    assert '--bucket' in message
    assert '--base' in message  # names what local does accept


def test_set_parses_type_aware_and_rejects_unknown_fields():
    from storix.cli.state import build_overrides

    overrides = build_overrides(
        's3', flags={'bucket': 'b'}, sets=['s3.root=/tenants/a']
    )
    assert overrides == {'bucket': 'b', 'root': '/tenants/a'}

    with pytest.raises(SystemExit) as exc:
        build_overrides('s3', flags={}, sets=['s3.nope=1'])
    assert 'nope' in str(exc.value)


def test_set_of_a_secret_field_is_refused():
    from storix.cli.state import build_overrides

    with pytest.raises(SystemExit) as exc:
        build_overrides('s3', flags={}, sets=['s3.access_key_id=AKIA'])

    message = str(exc.value)
    assert 'access_key_id' in message
    assert 'STORIX_S3_ACCESS_KEY_ID' in message  # points at the safe home


def test_set_targeting_another_provider_is_rejected():
    from storix.cli.state import build_overrides

    with pytest.raises(SystemExit) as exc:
        build_overrides('s3', flags={}, sets=['azure.container=x'])
    assert 'azure' in str(exc.value)


def test_missing_extra_gives_one_line_error_not_a_traceback(monkeypatch):
    from storix.cli import state

    def missing_extra(*_args, **_kwargs):
        msg = 'opendal missing'
        raise ImportError(msg)

    monkeypatch.setattr(state, 'get_storage', missing_extra)
    state.set_debug(False)

    with pytest.raises(SystemExit) as exc:
        state.build_base('s3')

    message = str(exc.value)
    assert 's3 extra' in message
    assert 'storix[s3]' in message  # the install remedy
    assert 'Traceback' not in message  # one line, no traceback


def test_missing_extra_reraises_under_traceback(monkeypatch):
    from storix.cli import state

    def missing_extra(*_args, **_kwargs):
        msg = 'opendal missing'
        raise ImportError(msg)

    monkeypatch.setattr(state, 'get_storage', missing_extra)
    state.set_debug(True)  # --traceback/--debug reveals everything
    try:
        with pytest.raises(ImportError):
            state.build_base('s3')
    finally:
        state.set_debug(False)


def test_a_message_carrying_exit_still_reaches_the_user(capsys, monkeypatch):
    """Given an exit that carries a message, when sx exits hard, then it prints.

    `main` ends in `os._exit`, which skips the interpreter's own SystemExit
    handling, so a `SystemExit('sx: ...')` raised by the config loader or the
    override validator would otherwise vanish into a bare exit status.
    """
    import storix.cli.app as app_module

    printed: list[str] = []
    monkeypatch.setattr(app_module.err, 'print', lambda text: printed.append(text))
    monkeypatch.setattr(
        app_module, 'app', lambda: (_ for _ in ()).throw(SystemExit('sx: boom'))
    )
    monkeypatch.setattr(
        app_module.os, '_exit', lambda code: (_ for _ in ()).throw(SystemExit(code))
    )

    with pytest.raises(SystemExit) as exit_info:
        app_module.main()

    assert exit_info.value.code == 1
    assert any('sx: boom' in text for text in printed)


def test_profile_and_environment_select_the_session(tmp_path, monkeypatch):
    """Given a profile and a stage, when sx runs, then the overlay is in force."""
    project = tmp_path / 'project'
    (project / 'dev').mkdir(parents=True)
    (project / 'prod').mkdir(parents=True)
    (project / 'dev' / 'in-dev.txt').write_text('x')
    (project / 'prod' / 'in-prod.txt').write_text('x')
    (project / 'storix.toml').write_text(
        '[profiles.media]\nprovider = "local"\nbase = "dev"\n\n'
        '[profiles.media.environments.prod]\nbase = "prod"\n',
        encoding='utf-8',
    )
    monkeypatch.chdir(project)
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path / 'xdg'))

    assert 'in-dev.txt' in run('--profile', 'media', 'ls', '/').stdout
    assert 'in-prod.txt' in run('--profile', 'media', '--env', 'prod', 'ls', '/').stdout


def test_an_environment_without_a_profile_is_refused(tmp_path, monkeypatch):
    """Given no profile, when a stage is named, then sx says which flag to add."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path / 'xdg'))

    result = run('--env', 'prod', 'ls', '/')

    assert result.exit_code != 0
    assert 'name one with --profile' in str(result.exception) + result.stdout


def _plain(text: str) -> str:
    """Rendered help as words only.

    Help is styled and wrapped to the terminal, both of which differ between
    a developer's shell and CI, so a substring assertion has to read the
    words rather than the rendering.
    """
    return re.sub(r'\s+', ' ', re.sub(r'\x1b\[[0-9;]*m', '', text))


def test_help_groups_commands_and_options_by_what_they_do():
    """Given --help, when read, then it is grouped, not one flat list.

    A first-time reader should see which commands touch files, which move
    bytes, and which are about sx itself, without reading the docs.
    """
    text = _plain(run('--help').stdout)

    for panel in ('Navigate', 'Read', 'Write', 'Transfer', 'Session and setup'):
        assert panel in text, panel
    for panel in ('Connection', 'Profile and overrides', 'Session', 'Inspect'):
        assert panel in text, panel


def test_help_points_at_the_commands_that_explain_the_session():
    """Given --help, when read, then it names the way to inspect a session."""
    text = _plain(run('--help').stdout)

    assert 'sx config show --effective' in text
    assert 'sx doctor' in text


def _pinned_and_named(tmp_path) -> object:
    """A project with a pinned profile and a second one to override it with."""
    project = tmp_path / 'project'
    (project / 'pinned').mkdir(parents=True)
    (project / 'other').mkdir(parents=True)
    (project / 'storix.toml').write_text(
        'profile = "pinned"\n\n'
        '[profiles.pinned]\nprovider = "local"\nbase = "pinned"\n\n'
        '[profiles.other]\nprovider = "local"\nbase = "other"\n',
        encoding='utf-8',
    )
    return project


def test_the_flag_overrides_a_pinned_profile_in_every_view(tmp_path, monkeypatch):
    """Given a pinned profile, when --profile names another, then views follow.

    A command that re-resolves the selection instead of reading what the
    root callback decided reports the pin while the session uses the flag,
    which reads as "the flag did nothing".
    """
    project = _pinned_and_named(tmp_path)
    monkeypatch.chdir(project)
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path / 'xdg'))

    effective = run('--profile', 'other', 'config', 'show', '--effective').stdout
    assert "profile 'other'" in _plain(effective)
    assert 'other' in _plain(effective).split('local.base')[1].split('<-')[0]


def test_doctor_attributes_a_field_to_the_profile_that_supplies_it(
    tmp_path, monkeypatch
):
    """Given a profile that sets base, when doctor runs, then it says so."""
    project = _pinned_and_named(tmp_path)
    monkeypatch.chdir(project)
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path / 'xdg'))

    text = _plain(run('--profile', 'other', 'doctor').stdout)

    assert 'profile other' in text
    assert 'base <- profile' in text


def test_doctor_does_not_call_an_importable_extra_ready(tmp_path, monkeypatch):
    """Given an installed extra, when doctor runs, then it claims no more.

    Nothing here opens a connection, so "ready" would be a diagnosis
    storix has not made.
    """
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path / 'xdg'))

    text = _plain(run('doctor').stdout)

    assert 'provider extras' in text
    assert 'ready' not in text


def test_doctor_reports_an_uninstalled_extra_as_missing(tmp_path, monkeypatch):
    """Given an absent engine, when doctor runs, then it does not claim it.

    Doctor used to read the builder registry, which lists what get_storage
    accepts rather than what this environment can import, so every built-in
    provider reported as installed on a CLI-only install.
    """
    from storix.config import PROVIDER_REQUIRES

    monkeypatch.setitem(PROVIDER_REQUIRES, 's3', ('storix_no_such_engine',))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path / 'xdg'))

    text = _plain(run('doctor').stdout)

    assert 's3 not installed' in text
    assert 'local installed' in text


def test_listing_profiles_survives_an_unresolvable_credential(tmp_path, monkeypatch):
    """Given a profile whose env: secret is unset, when listed, then it prints.

    Naming the backend is a question about the file; opening it is a
    question about credentials. A broken credential is exactly when a user
    reaches for the listing.
    """
    project = tmp_path / 'project'
    project.mkdir()
    (project / 'storix.toml').write_text(
        'profile = "media"\n\n[profiles.media]\nprovider = "azure"\n'
        'account_name = "acct"\ncontainer = "raw"\n'
        'credential = "env:NOT_SET_ANYWHERE"\n',
        encoding='utf-8',
    )
    monkeypatch.chdir(project)
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path / 'xdg'))
    monkeypatch.delenv('NOT_SET_ANYWHERE', raising=False)

    result = run('config', 'profiles')

    assert result.exit_code == 0
    assert 'media' in _plain(result.stdout)


def test_config_show_renders_profiles_as_rows_not_dotted_keys(tmp_path, monkeypatch):
    """Given a profile with stages, when shown, then no key names a stage."""
    project = tmp_path / 'project'
    project.mkdir()
    (project / 'storix.toml').write_text(
        '[profiles.media]\nprovider = "local"\nbase = "."\n\n'
        '[profiles.media.environments.prod]\nbase = "."\n',
        encoding='utf-8',
    )
    monkeypatch.chdir(project)
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path / 'xdg'))

    text = _plain(run('config', 'show').stdout)

    assert 'profiles.media.environments.prod.base' not in text
    assert 'media' in text
    assert 'prod' in text


def test_a_shell_command_keeps_the_flags_the_shell_started_with(tmp_path, monkeypatch):
    """Given a shell started on a profile, when a line runs, then it stays.

    Every line typed in the shell re-enters the root callback carrying no
    flags. Re-deriving the session there swaps the named profile for
    whatever a config file pins, one command in.
    """
    project = _pinned_and_named(tmp_path)
    (project / 'pinned' / 'in-pinned.txt').write_text('x')
    (project / 'other' / 'in-other.txt').write_text('x')
    monkeypatch.chdir(project)
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path / 'xdg'))

    run('--profile', 'other', 'ls', '/')  # the shell's first command
    listing = run('ls', '/').stdout  # a later line, no flags of its own

    assert 'in-other.txt' in listing
    assert 'in-pinned.txt' not in listing


def test_a_later_shell_line_can_still_switch_the_session(tmp_path, monkeypatch):
    """Given a running session, when a line names a profile, then it moves."""
    project = _pinned_and_named(tmp_path)
    (project / 'pinned' / 'in-pinned.txt').write_text('x')
    (project / 'other' / 'in-other.txt').write_text('x')
    monkeypatch.chdir(project)
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path / 'xdg'))

    run('--profile', 'other', 'ls', '/')

    assert 'in-pinned.txt' in run('--profile', 'pinned', 'ls', '/').stdout


def test_whereami_names_the_profile_and_stage_in_force(tmp_path, monkeypatch):
    """Given a session, when asked, then it says what it is connected to."""
    project = _pinned_and_named(tmp_path)
    monkeypatch.chdir(project)
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path / 'xdg'))

    text = _plain(run('--profile', 'other', 'whereami').stdout)

    assert 'LocalBackend' in text
    assert 'profile: other' in text
    assert 'cwd: /' in text


def test_the_old_provider_name_still_answers(tmp_path, monkeypatch):
    """Given a script calling `sx provider`, when it runs, then it works."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path / 'xdg'))

    result = run('provider')

    assert result.exit_code == 0
    assert 'backend' in _plain(result.stdout)


def test_an_explicit_provider_steps_off_a_pinned_profile(tmp_path, monkeypatch):
    """Given a pin, when -p names another provider, then the flag wins.

    A pin is a default. Refusing `sx -p memory` because a file names an
    azure profile makes one line in a personal file a lock on the CLI.
    """
    (tmp_path / 'storix.toml').write_text(
        'profile = "azurish"\n\n[profiles.azurish]\nprovider = "azure"\n'
        'container = "raw"\naccount_name = "acct"\n',
        encoding='utf-8',
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path / 'xdg'))

    result = run('-p', 'memory', 'ls', '/')

    assert result.exit_code == 0


def test_two_flags_that_disagree_are_still_refused(tmp_path, monkeypatch):
    """Given --profile and a conflicting -p, when run, then it is an error."""
    (tmp_path / 'storix.toml').write_text(
        '[profiles.azurish]\nprovider = "azure"\ncontainer = "raw"\n'
        'account_name = "acct"\n',
        encoding='utf-8',
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path / 'xdg'))

    result = run('--profile', 'azurish', '-p', 'memory', 'ls', '/')

    assert result.exit_code != 0


def test_an_error_naming_a_toml_table_survives_rendering(tmp_path, monkeypatch):
    """Given a message holding [brackets], when printed, then they show.

    Rich reads `[environments]` as a style tag and prints nothing where
    the name should be, which is worst in exactly the messages that name
    a table the reader has to go and fix.
    """
    (tmp_path / 'storix.toml').write_text(
        '[profiles.media]\nprovider = "s3"\n\n'
        '[profiles.media.environment.dev]\nbucket = "media-dev"\n',
        encoding='utf-8',
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path / 'xdg'))

    result = run('config', 'validate')

    assert '[environments]' in _plain(result.stdout + result.stderr)


class _ScriptedPrompt:
    """A PromptSession stand-in that replays typed lines and interrupts.

    Each script entry is ``(buffer_text, result)``: ``result`` is either a
    line to return or an exception to raise, and ``buffer_text`` is what
    the user had typed when it happened - which is what prompt_toolkit
    leaves on ``default_buffer`` after a Ctrl+C.
    """

    def __init__(self, script, **_kwargs) -> None:
        self._script = list(script)
        self.default_buffer = type('B', (), {'text': ''})()

    def prompt(self, *_args, **_kwargs):
        typed, result = self._script.pop(0)
        self.default_buffer.text = typed
        if isinstance(result, type) and issubclass(result, BaseException):
            raise result
        return result


def _run_shell_over(monkeypatch, fs, script) -> None:
    from storix.cli import shell

    monkeypatch.setattr(
        shell, 'PromptSession', lambda **kwargs: _ScriptedPrompt(script, **kwargs)
    )
    shell.start_shell(fs)


def _run_shell(monkeypatch, script) -> None:
    _run_shell_over(monkeypatch, Storix(MemoryBackend()), script)


class _FakeApp:
    """Enough of prompt_toolkit's Application for the exit-key bindings."""

    def __init__(self) -> None:
        self.redraws = 0
        self.exited_with: type[BaseException] | None = None
        self.tasks: list[object] = []

    def invalidate(self) -> None:
        self.redraws += 1

    def create_background_task(self, coro) -> None:
        # kept rather than awaited, so a test can fire one expiry on demand
        self.tasks.append(coro)

    def close_tasks(self) -> None:
        for coro in self.tasks:
            coro.close()
        self.tasks.clear()

    def exit(self, *, exception=None) -> None:
        self.exited_with = exception


class _FakeSession:
    """A prompt session stand-in exposing only the toolbar and the app."""

    def __init__(self) -> None:
        self.bottom_toolbar: str | None = None
        self.app = _FakeApp()


class _FakeEvent:
    """A key press carrying a buffer and the app the handler talks to."""

    def __init__(self, app: _FakeApp, text: str = '') -> None:
        self.app = app
        self.current_buffer = _FakeBuffer(text)


class _FakeBuffer:
    def __init__(self, text: str) -> None:
        self.text = text
        self.complete_state = None

    def reset(self) -> None:
        self.text = ''


@pytest.fixture
def exit_keys():
    """The hint plus the c-c and c-d handlers bound over it.

    A fixture rather than a helper so the teardown closes any expiry
    coroutine a test armed and did not fire: an un-awaited one is collected
    later and reported against whichever test happens to be running then.
    """
    from storix.cli.shell import _ExitHint, _key_bindings

    session = _FakeSession()
    hint = _ExitHint(session)
    handlers = {
        binding.keys[0]: binding.handler for binding in _key_bindings(hint).bindings
    }
    yield session, hint, handlers
    session.app.close_tasks()


def test_ctrl_c_shows_its_hint_under_the_prompt_instead_of_printing_it(
    exit_keys, capsys
):
    """Given one Ctrl+C, when it lands, then the hint is the prompt toolbar.

    Printing it would push a fresh prompt out below the message; the
    toolbar keeps it under the line being typed.
    """
    session, _hint, handlers = exit_keys

    handlers['c-c'](_FakeEvent(session.app))

    assert session.bottom_toolbar is not None
    assert 'again to exit' in session.bottom_toolbar
    assert 'again to exit' not in capsys.readouterr().out
    assert session.app.exited_with is None


def test_ctrl_c_clears_a_typed_line_and_that_press_still_counts(exit_keys):
    """Given a half-typed line, when Ctrl+C lands, then it clears and arms.

    Two presses, never three: the one that discards the line is still the
    first of the pair.
    """
    session, _hint, handlers = exit_keys
    event = _FakeEvent(session.app, 'cat a.tx')

    handlers['c-c'](event)

    assert event.current_buffer.text == ''
    assert session.bottom_toolbar is not None
    assert session.app.exited_with is None


def test_a_second_ctrl_c_exits_and_takes_the_hint_with_it(exit_keys):
    """Given an armed hint, when Ctrl+C repeats, then the shell leaves."""
    session, _hint, handlers = exit_keys
    handlers['c-c'](_FakeEvent(session.app))

    handlers['c-c'](_FakeEvent(session.app))

    assert session.app.exited_with is EOFError
    assert session.bottom_toolbar is None


def test_ctrl_d_does_nothing_at_all_while_the_line_has_text(exit_keys):
    """Given text on the line, when Ctrl+D lands, then nothing happens.

    A terminal delivers the pending line on Ctrl+D and reports end of input
    only on an empty one, so there is nothing to clear and nothing to warn
    about.
    """
    session, _hint, handlers = exit_keys
    event = _FakeEvent(session.app, 'half typed')

    handlers['c-d'](event)

    assert event.current_buffer.text == 'half typed'
    assert session.bottom_toolbar is None
    assert session.app.exited_with is None


def test_ctrl_d_twice_on_an_empty_line_exits(exit_keys):
    """Given an empty line, when Ctrl+D repeats, then the shell leaves."""
    session, _hint, handlers = exit_keys

    handlers['c-d'](_FakeEvent(session.app))
    assert session.bottom_toolbar is not None
    handlers['c-d'](_FakeEvent(session.app))

    assert session.app.exited_with is EOFError


def test_the_two_exit_keys_do_not_satisfy_each_other(exit_keys):
    """Given Ctrl+C then Ctrl+D, when both land, then neither exits.

    "Press Ctrl+C again" means that key; a different key is a different
    intention, and guessing would exit on a keystroke nobody repeated.
    """
    session, _hint, handlers = exit_keys

    handlers['c-c'](_FakeEvent(session.app))
    handlers['c-d'](_FakeEvent(session.app))

    assert session.app.exited_with is None
    assert 'Ctrl+D' in (session.bottom_toolbar or '')


def test_a_lapsed_hint_no_longer_exits(exit_keys):
    """Given a hint that timed out, when the key repeats, then it re-arms.

    The pair has to be a pair: a press now and another one minutes later
    are two intentions, not an exit.
    """
    session, hint, handlers = exit_keys
    handlers['c-c'](_FakeEvent(session.app))

    hint.disarm()  # what the expiry does when it fires
    handlers['c-c'](_FakeEvent(session.app))

    assert session.app.exited_with is None
    assert session.bottom_toolbar is not None


def test_a_later_press_supersedes_an_earlier_expiry(exit_keys, monkeypatch):
    """Given a re-arm, when the first expiry fires, then the hint survives.

    Otherwise the second press inherits the first press's countdown and the
    hint vanishes while it is still the live one.
    """
    import asyncio

    from storix.cli import shell

    monkeypatch.setattr(shell, '_HINT_SECONDS', 0)
    session, _hint, handlers = exit_keys
    # a different key re-arms; the same key twice would exit instead
    handlers['c-c'](_FakeEvent(session.app))
    handlers['c-d'](_FakeEvent(session.app))
    first_expiry = session.app.tasks[0]

    asyncio.run(first_expiry)

    assert session.bottom_toolbar is not None
    assert 'Ctrl+D' in session.bottom_toolbar


def test_an_expiry_that_is_still_the_live_one_clears_the_hint(exit_keys, monkeypatch):
    """Given no second press, when the expiry fires, then the row goes away."""
    import asyncio

    from storix.cli import shell

    monkeypatch.setattr(shell, '_HINT_SECONDS', 0)
    session, _hint, handlers = exit_keys
    handlers['c-c'](_FakeEvent(session.app))

    asyncio.run(session.app.tasks[0])

    assert session.bottom_toolbar is None


@pytest.mark.parametrize(
    ('mode', 'fragment', 'expected'),
    [
        ('sensitive', 'li', False),  # the default: LICENSE is not offered
        ('sensitive', 'LI', True),
        ('insensitive', 'li', True),
        ('insensitive', 'LI', True),
        ('smart', 'li', True),  # no uppercase typed -> ignore case
        ('smart', 'LI', True),  # uppercase typed, and it matches exactly
        ('smart', 'Li', False),  # uppercase typed, so 'i' no longer matches 'I'
    ],
)
def test_completion_case_preference(mode, fragment, expected, prefs_from):
    from storix.cli.shell import _completion_matches

    prefs_from(f'[cli]\ncompletion_case = "{mode}"\n')

    assert _completion_matches('LICENSE', fragment) is expected


def test_completion_case_defaults_to_smart():
    """Modern shells ignore case on a lowercase prefix; sx follows."""
    from storix.cli.config import CliPrefs

    assert CliPrefs().completion_case == 'smart'


def test_cd_dash_returns_and_echoes_the_directory():
    run('mkdir', '/a', '/b')
    run('cd', '/a')
    run('cd', '/b')

    back = run('cd', '-')

    assert back.exit_code == 0
    assert back.stdout.strip() == '/a'  # unix cd echoes where '-' landed
    assert run('pwd').stdout.strip() == '/a'


def test_cd_dash_before_any_move_stays_where_the_session_opened():
    """No error path: a fresh session's previous directory is its start."""
    result = run('cd', '-')

    assert result.exit_code == 0
    assert result.stdout.strip().endswith('/')
    assert run('pwd').stdout.strip() == '/'


@pytest.mark.parametrize(
    ('line', 'expected'),
    [
        ('cat a.txt > b.txt', (['cat', 'a.txt'], 'b.txt', False)),
        ('cat a.txt >b.txt', (['cat', 'a.txt'], 'b.txt', False)),
        ('echo hi >> log.txt', (['echo', 'hi'], 'log.txt', True)),
        ('echo hi >>log.txt', (['echo', 'hi'], 'log.txt', True)),
        ('ls', (['ls'], None, False)),
    ],
)
def test_split_redirect(line, expected):
    import shlex

    from storix.cli.shell import _split_redirect

    assert _split_redirect(shlex.split(line)) == expected


@pytest.mark.parametrize('line', ['cat a.txt >', 'cat a.txt > one two', 'ls > > x'])
def test_split_redirect_rejects_a_target_it_cannot_name(line):
    import shlex

    from storix.cli.shell import _split_redirect

    with pytest.raises(ValueError, match='redirect'):
        _split_redirect(shlex.split(line))


def test_shell_redirects_command_output_into_a_backend_file(monkeypatch, capsys):
    fs = Storix(MemoryBackend())
    fs.echo('hello\n', '/a.txt')

    _run_shell_over(
        monkeypatch,
        fs,
        [
            ('', 'cat /a.txt > /copy.txt'),
            ('', 'echo more >> /copy.txt'),
            ('', EOFError),
        ],
    )

    assert fs.cat('/copy.txt') == b'hello\nmore\n'


def test_shell_redirection_writes_text_not_a_rendering(monkeypatch, capsys):
    """Given a styled listing, when redirected, then the file holds no escapes.

    The console is built at import time, so under a real terminal rich
    caches a color system and keeps emitting escapes even once stdout has
    been replaced by a buffer. Pytest's stdout is a pipe, where nothing is
    ever styled, so the cached value has to be set here for this to be a
    test of anything.
    """
    from storix.cli.render import console

    monkeypatch.setattr(console, '_color_system', ColorSystem.TRUECOLOR)
    fs = Storix(MemoryBackend())
    fs.mkdir('/docs')
    fs.echo('hello\n', '/a.txt')

    _run_shell_over(monkeypatch, fs, [('', 'ls -l > /out.txt'), ('', EOFError)])

    written = fs.cat('/out.txt').decode()
    assert '\x1b[' not in written
    assert 'a.txt' in written
    assert not any(line.endswith((' ', '\t')) for line in written.splitlines())


def test_shell_redirection_reports_a_bad_target_instead_of_writing(monkeypatch, capsys):
    fs = Storix(MemoryBackend())
    fs.echo('hello\n', '/a.txt')

    _run_shell_over(monkeypatch, fs, [('', 'cat /a.txt >'), ('', EOFError)])

    assert 'redirect' in capsys.readouterr().out
    assert not fs.exists('/copy.txt')


def test_edit_writes_the_editors_changes_back(monkeypatch):
    """The point of the command: edit a backend file with a local editor."""
    run('echo', 'hello', '-f', '/a.txt')
    monkeypatch.setenv('EDITOR', 'sed -i s/hello/edited/')

    result = run('edit', '/a.txt')

    assert result.exit_code == 0
    assert run('cat', '/a.txt').stdout == 'edited\n'


def test_edit_does_not_write_when_the_file_is_untouched(monkeypatch):
    """A no-op edit must not cost a write (or a new version on an object
    store), so the content decides, not the fact that an editor ran."""
    run('echo', 'hello', '-f', '/a.txt')
    monkeypatch.setenv('EDITOR', 'true')
    writes: list[str] = []
    real_echo = Storix.echo

    def counting_echo(self, data, path, **kwargs):
        writes.append(str(path))
        return real_echo(self, data, path, **kwargs)

    monkeypatch.setattr(Storix, 'echo', counting_echo)

    result = run('edit', '/a.txt')

    assert result.exit_code == 0
    assert writes == []
    assert 'unchanged' in result.stdout


def test_edit_creates_a_missing_file_from_what_you_type(monkeypatch, tmp_path):
    # sed cannot write into an empty file (no lines to act on), so this one
    # needs an editor that just puts content there
    script = tmp_path / 'fake_editor.py'
    script.write_text(
        "import pathlib, sys\npathlib.Path(sys.argv[1]).write_text('new\\n')\n"
    )
    monkeypatch.setenv('EDITOR', f'{sys.executable} {script}')

    result = run('edit', '/fresh.txt')

    assert result.exit_code == 0
    assert run('cat', '/fresh.txt').stdout == 'new\n'


def test_edit_leaves_a_missing_file_missing_when_nothing_is_typed(monkeypatch):
    monkeypatch.setenv('EDITOR', 'true')

    result = run('edit', '/fresh.txt')

    assert result.exit_code == 0
    assert run('exists', '/fresh.txt').exit_code == 1


def test_edit_refuses_a_directory(monkeypatch):
    run('mkdir', '/docs')
    monkeypatch.setenv('EDITOR', 'true')

    result = run('edit', '/docs')

    assert result.exit_code == 1
    assert 'is a directory' in result.stderr


def test_edit_says_which_variable_to_set_when_there_is_no_editor(monkeypatch):
    run('echo', 'hello', '-f', '/a.txt')
    monkeypatch.delenv('EDITOR', raising=False)
    monkeypatch.delenv('VISUAL', raising=False)

    result = run('edit', '/a.txt')

    assert result.exit_code == 1
    assert 'EDITOR' in result.stderr


def test_editor_preference_beats_the_environment(prefs_from, monkeypatch):
    """A user who names an editor for sx means it - and on a fresh Windows
    shell it is the only way to have one."""
    from storix.cli.render import resolve_editor

    monkeypatch.setenv('EDITOR', 'vi')
    monkeypatch.setenv('VISUAL', 'vim')
    prefs_from('[cli]\neditor = "nvim"\n')

    assert resolve_editor() == 'nvim'


def test_visual_beats_editor_when_no_preference_is_set(monkeypatch):
    from storix.cli.render import resolve_editor

    monkeypatch.setenv('EDITOR', 'vi')
    monkeypatch.setenv('VISUAL', 'vim')

    assert resolve_editor() == 'vim'


def test_windows_falls_back_to_notepad(monkeypatch):
    """A fresh Windows shell has neither variable set but always has this."""
    from storix.cli import render

    monkeypatch.delenv('EDITOR', raising=False)
    monkeypatch.delenv('VISUAL', raising=False)
    monkeypatch.setattr(render.sys, 'platform', 'win32')

    assert render.resolve_editor() == 'notepad'


def test_unix_has_no_editor_fallback(monkeypatch):
    """vi and nano are both plausible; choosing for someone is worse than
    saying there is nothing to choose."""
    from storix.cli import render

    monkeypatch.delenv('EDITOR', raising=False)
    monkeypatch.delenv('VISUAL', raising=False)
    monkeypatch.setattr(render.sys, 'platform', 'linux')

    assert render.resolve_editor() is None


def test_edit_uses_the_configured_editor(prefs_from, monkeypatch, tmp_path):
    script = tmp_path / 'fake_editor.py'
    script.write_text(
        "import pathlib, sys\npathlib.Path(sys.argv[1]).write_text('via prefs\\n')\n"
    )
    monkeypatch.delenv('EDITOR', raising=False)
    prefs_from(f'[cli]\neditor = "{sys.executable} {script}"\n')

    assert run('edit', '/a.txt').exit_code == 0
    assert run('cat', '/a.txt').stdout == 'via prefs\n'


def test_cd_dash_marks_the_destination_with_the_jump_glyph(monkeypatch):
    """zoxide's convention: the arrow says "you were moved here", so the
    line does not read as one more piece of output."""
    from storix.cli import app as app_module
    from storix.cli.icons import Icons

    run('mkdir', '/a')
    run('cd', '/a')
    monkeypatch.setattr(app_module, 'icons_enabled', lambda: True)
    monkeypatch.setattr(
        type(app_module.console), 'is_terminal', property(lambda _: True)
    )

    out = run('cd', '-').stdout

    assert Icons.ARROW_JUMP in out


@pytest.mark.parametrize(
    'style_str',
    [
        'class:completion-menu',
        'class:completion-menu.completion',
        'class:completion-menu.meta.completion',
        'class:completion-menu.multi-column-meta',
        'class:scrollbar.background',
        'class:bottom-toolbar',
        'class:bottom-toolbar.text',
    ],
)
def test_the_prompt_paints_no_background_of_its_own(style_str):
    """Given a terminal the user made transparent, when the prompt draws, then
    it stays transparent.

    Every prompt_toolkit default here paints an opaque grey or a reversed
    bar, which becomes a slab over the terminal's own surface.
    """
    from prompt_toolkit.styles import merge_styles
    from prompt_toolkit.styles.defaults import default_ui_style

    from storix.cli.shell import _MENU_STYLE

    merged = merge_styles([default_ui_style(), _MENU_STYLE])

    attrs = merged.get_attrs_for_style_str(style_str)

    assert attrs.bgcolor in {'default', ''}, style_str
    assert not attrs.reverse, style_str


def test_a_menu_entry_keeps_a_readable_foreground():
    """Given a transparent background, when an entry renders, then its text is
    not the black the grey default paired with."""
    from prompt_toolkit.styles import merge_styles
    from prompt_toolkit.styles.defaults import default_ui_style

    from storix.cli.shell import _MENU_STYLE

    merged = merge_styles([default_ui_style(), _MENU_STYLE])

    plain = merged.get_attrs_for_style_str('class:completion-menu.completion')
    directory = merged.get_attrs_for_style_str(
        'class:completion-menu.completion fg:ansibrightblue bold'
    )

    assert plain.color == ''  # the terminal's own foreground
    assert directory.color == 'ansibrightblue'  # the entry's type color survives


def test_the_selected_entry_inverts_rather_than_choosing_colors():
    """Given a selection, when it highlights, then it reverses the entry.

    A chosen pair would fight both the terminal theme and the per-entry
    color a directory carries; reversing follows both.
    """
    from prompt_toolkit.styles import merge_styles
    from prompt_toolkit.styles.defaults import default_ui_style

    from storix.cli.shell import _MENU_STYLE

    merged = merge_styles([default_ui_style(), _MENU_STYLE])

    attrs = merged.get_attrs_for_style_str(
        'class:completion-menu.completion.current fg:ansibrightblue bold'
    )

    assert attrs.reverse
    assert attrs.color == 'ansibrightblue'


def test_the_completion_menu_is_a_grid_not_a_column():
    """Given many entries, when the menu opens, then it uses the shell grid.

    A single tall column pushes a directory of twenty entries off the line
    it is completing.
    """
    from prompt_toolkit.shortcuts import CompleteStyle

    from storix.cli import shell

    captured: dict[str, object] = {}

    class _Recorder:
        def __init__(self, **kwargs) -> None:
            captured.update(kwargs)
            self.default_buffer = type('B', (), {'text': ''})()
            self.key_bindings = None
            self.bottom_toolbar = None

        def prompt(self, *_args, **_kwargs) -> str:
            raise EOFError

    shell.PromptSession = _Recorder  # type: ignore[misc]
    try:
        shell.start_shell(Storix(MemoryBackend()))
    finally:
        importlib.reload(shell)

    assert captured['complete_style'] is CompleteStyle.MULTI_COLUMN


def test_completions_follow_the_order_a_shell_lists_them_in():
    """Given dunder modules, when completions sort, then punctuation is ignored.

    Byte order opens a python package with a block of underscores;
    glibc collation under a UTF-8 locale, which coreutils `ls` and a zsh
    completion list both follow, files them by their letters.
    """
    from storix.cli.shell import _completion_order

    names = [
        'azblob.py',
        'azure.py',
        'base.py',
        'gcs.py',
        'generic.py',
        '__init__.py',
        'local.py',
        'memory.py',
        'opendal.py',
        '_proto.py',
        '__pycache__',
        's3.py',
    ]

    # the exact output of `/usr/bin/ls` over these names under en_US.UTF-8
    assert sorted(names, key=_completion_order) == names


def test_completions_still_break_ties_case_insensitively():
    """Given mixed case, when completions sort, then case does not decide."""
    from storix.cli.shell import _completion_order

    assert sorted(['Zebra.txt', 'apple.txt'], key=_completion_order) == [
        'apple.txt',
        'Zebra.txt',
    ]


def test_the_completion_grid_starts_at_the_left_edge():
    """Given a menu float anchored at the caret, when adjusted, then it is not.

    prompt_toolkit floats the menu at the cursor, which pushes the grid
    right and wastes the width to its left; every shell lists from column
    zero.

    The float is built here rather than taken from a real session:
    constructing one needs a terminal and a running event loop, and at the
    dependency floor it refuses outright when pytest has replaced stdin.
    """
    from prompt_toolkit.layout.containers import Float, FloatContainer, Window
    from prompt_toolkit.layout.menus import MultiColumnCompletionsMenu

    from storix.cli.shell import _left_align_menu, _menu_floats

    anchored = Float(content=MultiColumnCompletionsMenu(), xcursor=True, ycursor=True)
    container = FloatContainer(content=Window(), floats=[anchored])
    session = type('S', (), {'layout': type('L', (), {'container': container})()})()

    assert list(_menu_floats(session)) == [anchored]

    _left_align_menu(session)

    assert anchored.xcursor is False
    assert anchored.left == 0
    # the row still sits directly under the prompt line
    assert anchored.ycursor is True


def test_left_aligning_the_menu_tolerates_a_session_without_a_layout():
    """Given no layout, when adjusted, then nothing raises.

    A cosmetic adjustment must never be what stops the prompt opening.
    """
    from storix.cli.shell import _left_align_menu

    _left_align_menu(type('S', (), {})())
