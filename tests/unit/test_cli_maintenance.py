"""`sx update` and `sx doctor`: what they report and what they refuse."""

from collections.abc import Generator
from pathlib import Path

import pytest

from typer.testing import CliRunner

from storix.cli import app as cli, maintenance
from storix.cli.state import reset_session


runner = CliRunner()


def run(*args: str):
    """Invoke sx with `args`."""
    return runner.invoke(cli.app, list(args))


def unwrapped(text: str) -> str:
    """Output with rich's line wrapping undone."""
    return text.replace('\n', '')


@pytest.fixture
def sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Generator[Path]:
    """An isolated project cwd and XDG home."""
    project = tmp_path / 'project'
    project.mkdir()
    monkeypatch.chdir(project)
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path / 'xdg'))
    # sx keeps one session per process so cwd survives across shell commands;
    # each test needs its own, or the first one to build wins the file
    reset_session()
    yield project


def test_update_refuses_to_touch_an_installation_it_did_not_make(sandbox, monkeypatch):
    """Given a non-uv-tool install, when updating, then it prints the manual way.

    Rewriting someone else's environment is the one thing an updater must
    never do on a guess.
    """
    monkeypatch.setattr(maintenance, 'installation_kind', lambda: 'virtualenv')
    monkeypatch.setattr(
        maintenance,
        'upgrade_command',
        lambda: ['python', '-m', 'pip', 'install', '-U', 'storix'],
    )

    result = run('update')

    assert result.exit_code == 2
    assert 'will not modify' in unwrapped(result.stderr)
    assert 'pip install' in unwrapped(result.stderr)


def test_update_drives_uv_for_a_uv_tool_install(sandbox, monkeypatch):
    """Given a uv tool install, when updating, then uv is run, not pip."""
    ran: list[list[str]] = []
    monkeypatch.setattr(maintenance, 'installation_kind', lambda: 'uv-tool')
    monkeypatch.setattr(
        maintenance, 'upgrade_command', lambda: ['uv', 'tool', 'upgrade', 'storix']
    )
    monkeypatch.setattr(maintenance, '_run', lambda argv: ran.append(list(argv)) or 0)

    result = run('update')

    assert result.exit_code == 0
    assert ran == [['uv', 'tool', 'upgrade', 'storix']]


def test_update_check_reports_both_versions_without_installing(sandbox, monkeypatch):
    """Given --check, when a newer release exists, then it says so and stops."""
    ran: list[list[str]] = []
    monkeypatch.setattr(maintenance, 'installed_version', lambda: '0.4.9')
    monkeypatch.setattr(maintenance, 'latest_version', lambda: '0.5.0')
    monkeypatch.setattr(maintenance, '_run', lambda argv: ran.append(list(argv)) or 0)

    result = run('update', '--check')

    assert result.exit_code == 0
    assert '0.4.9' in unwrapped(result.stdout)
    assert '0.5.0' in unwrapped(result.stdout)
    assert ran == []


def test_update_check_says_so_when_pypi_is_unreachable(sandbox, monkeypatch):
    """Given no network, when checking, then it reports that, not a version."""
    monkeypatch.setattr(maintenance, 'latest_version', lambda: None)

    result = run('update', '--check')

    assert result.exit_code == 1
    assert 'could not reach' in unwrapped(result.stderr)


def test_doctor_reports_version_install_and_configuration(sandbox):
    """Given a config, when doctor runs, then it reports what is in force."""
    (sandbox / 'data').mkdir()
    (sandbox / 'storix.toml').write_text(
        'provider = "local"\n\n[local]\nbase = "data"\n', encoding='utf-8'
    )

    result = run('doctor')

    assert result.exit_code == 0
    output = unwrapped(result.stdout)
    assert 'storix.toml' in output
    assert 'provider' in output
    assert 'python' in output


def test_doctor_names_the_selected_profile_and_stage(sandbox):
    """Given a selection, when doctor runs, then it names it, not the default."""
    (sandbox / 'data').mkdir()
    (sandbox / 'storix.toml').write_text(
        '[profiles.media]\nprovider = "local"\ndefault_environment = "dev"\n\n'
        '[profiles.media.environments.dev]\nbase = "data"\n',
        encoding='utf-8',
    )

    result = run('--profile', 'media', 'doctor')

    assert result.exit_code == 0
    assert 'media' in unwrapped(result.stdout)
    assert 'dev' in unwrapped(result.stdout)


def test_doctor_lists_profiles_when_none_is_selected(sandbox):
    """Given profiles but no selection, when doctor runs, then it lists them."""
    (sandbox / 'storix.toml').write_text(
        '[profiles.media]\nprovider = "local"\nbase = "."\n', encoding='utf-8'
    )

    result = run('doctor')

    assert 'none selected' in unwrapped(result.stdout)
    assert 'media' in unwrapped(result.stdout)


def test_doctor_does_not_touch_the_network_by_default(sandbox, monkeypatch):
    """Given no --updates, when doctor runs, then PyPI is never asked."""
    asked = False

    def fail() -> str | None:
        nonlocal asked
        asked = True
        return None

    monkeypatch.setattr(maintenance, 'latest_version', fail)

    run('doctor')

    assert not asked


def test_install_adds_an_extra_without_dropping_the_others(sandbox, monkeypatch):
    """Given a cli install, when adding s3, then cli survives the rewrite.

    uv tool install replaces the requirement rather than amending it, so
    the receipt has to be read back or every add is also a removal.
    """
    ran: list[list[str]] = []
    monkeypatch.setattr(maintenance, 'installation_kind', lambda: 'uv-tool')
    monkeypatch.setattr(maintenance, 'installed_extras', lambda: frozenset({'cli'}))
    monkeypatch.setattr(maintenance, 'installed_version', lambda: '0.5.0')
    monkeypatch.setattr(maintenance, '_run', lambda argv: ran.append(list(argv)) or 0)

    result = run('install', 's3')

    assert result.exit_code == 0
    assert ran == [['uv', 'tool', 'install', '--force', 'storix[cli,s3]==0.5.0']]


def test_install_pins_the_running_version(sandbox, monkeypatch):
    """Given an outdated install, when adding an extra, then it stays outdated.

    Adding a backend is not a moment to also move versions; `sx update` is
    the command that does that, deliberately and on its own.
    """
    ran: list[list[str]] = []
    monkeypatch.setattr(maintenance, 'installation_kind', lambda: 'uv-tool')
    monkeypatch.setattr(maintenance, 'installed_extras', lambda: frozenset({'cli'}))
    monkeypatch.setattr(maintenance, 'installed_version', lambda: '0.4.2')
    monkeypatch.setattr(maintenance, '_run', lambda argv: ran.append(list(argv)) or 0)

    run('install', 'gcs')

    assert ran[0][-1].endswith('==0.4.2')


def test_install_is_a_no_op_when_the_extra_is_already_there(sandbox, monkeypatch):
    """Given s3 installed, when adding s3, then nothing is rewritten."""
    ran: list[list[str]] = []
    monkeypatch.setattr(maintenance, 'installation_kind', lambda: 'uv-tool')
    monkeypatch.setattr(
        maintenance, 'installed_extras', lambda: frozenset({'cli', 's3'})
    )
    monkeypatch.setattr(maintenance, '_run', lambda argv: ran.append(list(argv)) or 0)

    result = run('install', 's3')

    assert result.exit_code == 0
    assert 'already installed' in unwrapped(result.stdout)
    assert ran == []


def test_install_rejects_a_name_that_is_not_an_extra(sandbox, monkeypatch):
    """Given a typo, when installing, then it stops before uv resolves.

    uv would spend a full resolve and then name a package rather than the
    typo, which is the slower half of a worse message.
    """
    ran: list[list[str]] = []
    monkeypatch.setattr(maintenance, '_run', lambda argv: ran.append(list(argv)) or 0)

    result = run('install', 'sthree')

    assert result.exit_code == 2
    assert 'no such extra' in unwrapped(result.stderr)
    assert 's3' in unwrapped(result.stderr)
    assert ran == []


def test_install_refuses_an_installation_it_did_not_make(sandbox, monkeypatch):
    """Given a virtualenv, when installing, then it prints the manual way.

    The same rail as `sx update`: rewriting someone else's environment is
    the one thing this must never do on a guess.
    """
    monkeypatch.setattr(maintenance, 'installation_kind', lambda: 'virtualenv')
    monkeypatch.setattr(maintenance, 'installed_extras', lambda: frozenset())

    result = run('install', 's3')

    assert result.exit_code == 2
    assert 'will not modify' in unwrapped(result.stderr)
    assert 'pip install' in unwrapped(result.stderr)


def test_uninstall_removes_one_extra_and_keeps_the_rest(sandbox, monkeypatch):
    """Given cli, s3 and gcs, when removing s3, then cli and gcs remain."""
    ran: list[list[str]] = []
    monkeypatch.setattr(maintenance, 'installation_kind', lambda: 'uv-tool')
    monkeypatch.setattr(
        maintenance, 'installed_extras', lambda: frozenset({'cli', 's3', 'gcs'})
    )
    monkeypatch.setattr(maintenance, 'installed_version', lambda: '0.5.0')
    monkeypatch.setattr(maintenance, '_run', lambda argv: ran.append(list(argv)) or 0)

    result = run('uninstall', 's3')

    assert result.exit_code == 0
    assert ran == [['uv', 'tool', 'install', '--force', 'storix[cli,gcs]==0.5.0']]


def test_uninstall_refuses_to_remove_the_extra_that_makes_sx_run(sandbox, monkeypatch):
    """Given cli named, when removing, then it refuses and says how to go.

    Dropping cli leaves an sx that cannot start, and therefore no command
    left to put it back with.
    """
    ran: list[list[str]] = []
    monkeypatch.setattr(maintenance, 'installation_kind', lambda: 'uv-tool')
    monkeypatch.setattr(maintenance, '_run', lambda argv: ran.append(list(argv)) or 0)

    result = run('uninstall', 'cli')

    assert result.exit_code == 2
    assert 'uv tool uninstall storix' in unwrapped(result.stderr)
    assert ran == []
