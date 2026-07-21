import pytest

from typer.testing import CliRunner

import storix.cli as cli_entry

from storix import Storix
from storix.backends import MemoryBackend
from storix.cli import app as cli


runner = CliRunner()


@pytest.fixture(autouse=True)
def fresh_session(tmp_path, monkeypatch) -> None:
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

    assert str(exc_info.value) == (
        "cli extra not installed. Install it by running `uv add 'storix[cli]'`."
    )


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


def test_data_url_works_but_presigned_needs_capability():
    run('echo', 'hi', '-f', '/a.txt')
    assert run('url', '--data', '/a.txt').stdout.startswith('data:')
    unsupported = run('url', '/a.txt')  # memory has no presigned_urls
    assert unsupported.exit_code == 1
    assert 'presigned_urls' in unsupported.stderr


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


def test_credentials_in_the_cli_table_are_rejected_not_ignored(prefs_from):
    from storix.cli.config import load_prefs

    prefs_from("[cli]\naccount_name = 'acme'\n")  # shared config, belongs in env

    with pytest.raises(SystemExit) as exc_info:
        load_prefs()

    assert 'STORIX_AZURE' in str(exc_info.value)  # names where it belongs


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

    assert _parse_completion_context('push') == ('push', 0, 'push')
    assert _parse_completion_context('push ') == ('push', 1, '')
    assert _parse_completion_context('push sr') == ('push', 1, 'sr')
    assert _parse_completion_context('push sr ') == ('push', 2, '')
    assert _parse_completion_context('push sr rem') == ('push', 2, 'rem')
    assert _parse_completion_context('pull ') == ('pull', 1, '')
    assert _parse_completion_context('pull rem ') == ('pull', 2, '')


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
