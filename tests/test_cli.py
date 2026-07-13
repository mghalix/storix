import pytest

from typer.testing import CliRunner

import storix.cli as cli_entry

from storix import Storix
from storix.backends import MemoryBackend
from storix.cli import app as cli


runner = CliRunner()


@pytest.fixture(autouse=True)
def fresh_session() -> None:
    """Each test gets a clean in-memory session (no disk, no env)."""
    cli.use_fs(Storix(MemoryBackend()))


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


def test_data_url_works_but_presigned_needs_capability():
    run('echo', 'hi', '-f', '/a.txt')
    assert run('url', '--data', '/a.txt').stdout.startswith('data:')
    unsupported = run('url', '/a.txt')  # memory has no presigned_urls
    assert unsupported.exit_code == 1
    assert 'presigned_urls' in unsupported.stderr


def test_apply_layers_composition_and_lookup():
    from storix import CacheLayer, SandboxLayer
    from storix.cli.app import _apply_layers, cache_layer, layer_summary

    fs = _apply_layers(
        Storix(MemoryBackend()), cache=True, cache_ttl=None, sandbox='/jail'
    )
    # sandbox innermost, cache outermost
    assert isinstance(fs.backend, CacheLayer)
    assert isinstance(fs.backend._inner, SandboxLayer)
    assert cache_layer(fs) is fs.backend
    summary = layer_summary(fs)
    assert summary is not None
    assert 'cache' in summary and 'sandbox' in summary
    assert 'InMemoryCacheStore' in summary  # names the store backing the cache


def test_apply_layers_none_is_passthrough():
    from storix.cli.app import _apply_layers, cache_layer, layer_summary

    base = Storix(MemoryBackend())
    fs = _apply_layers(base, cache=False, cache_ttl=None, sandbox=None)
    assert fs is base
    assert cache_layer(fs) is None
    assert layer_summary(fs) is None


def test_prompt_label_shows_base_backend_not_the_layer():
    from storix.cli.app import _apply_layers, base_backend, prompt_label

    plain = Storix(MemoryBackend())
    assert prompt_label(plain) == 'MemoryBackend'  # no layers -> just the backend

    fs = _apply_layers(
        Storix(MemoryBackend()), cache=True, cache_ttl=None, sandbox='/jail'
    )
    # the real provider is surfaced, annotated with the stack (not "CacheLayer")
    assert type(base_backend(fs)).__name__ == 'MemoryBackend'
    assert prompt_label(fs) == 'MemoryBackend(cache, sandbox)'


def test_url_expire_flag_is_accepted():
    from storix import DataUrlLayer

    cli.use_fs(Storix(DataUrlLayer(MemoryBackend())))
    run('echo', 'hi', '-f', '/a.txt')
    out = run('url', '/a.txt', '--expire', '60')
    assert out.exit_code == 0
    assert out.stdout.strip().startswith('data:')  # data URLs ignore expiry
