"""`sx config`: seeing, explaining, and editing configuration."""

import os
import stat

from collections.abc import Generator
from pathlib import Path

import pytest

from typer.testing import CliRunner

from storix.cli import app as cli


runner = CliRunner()


def run(*args: str):
    """Invoke sx with `args`."""
    return runner.invoke(cli.app, list(args))


def unwrapped(text: str) -> str:
    """Output with rich's line wrapping undone, so paths can be matched."""
    return text.replace('\n', '')


@pytest.fixture
def sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Generator[Path]:
    """An isolated project cwd and XDG home, with no STORIX_* leakage."""
    project = tmp_path / 'project'
    project.mkdir()
    monkeypatch.chdir(project)
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path / 'xdg'))
    for var in [name for name in os.environ if name.startswith('STORIX_')]:
        monkeypatch.delenv(var, raising=False)
    yield project


def test_path_names_both_files_and_whether_they_exist(sandbox):
    """Given no config, when asked for paths, then both are named as absent."""
    result = run('config', 'path')

    assert result.exit_code == 0
    assert 'would be created' in unwrapped(result.stdout)
    assert 'storix.toml' in unwrapped(result.stdout)


def test_set_creates_the_project_file_and_get_reads_it_back(sandbox):
    """Given a set, when read back, then the value and its file are reported."""
    assert run('config', 'set', 's3.bucket', 'media').exit_code == 0

    result = run('config', 'get', 's3.bucket')

    assert result.exit_code == 0
    assert 'media' in result.stdout
    assert (sandbox / 'storix.toml').is_file()


def test_set_preserves_comments_and_other_keys(sandbox):
    """Given an edited file, when written again, then the rest survives."""
    (sandbox / 'storix.toml').write_text(
        '# keep me\nprovider = "local"\n\n[s3]\nbucket = "media"\n', encoding='utf-8'
    )

    run('config', 'set', 's3.region', 'auto')
    text = (sandbox / 'storix.toml').read_text(encoding='utf-8')

    assert '# keep me' in text
    assert 'provider = "local"' in text
    assert 'bucket = "media"' in text
    assert 'region = "auto"' in text


def test_set_refuses_a_secret_in_project_scope(sandbox):
    """Given a project file, when a secret is set, then it is refused by name."""
    result = run('config', 'set', 'azure.credential', 'hunter2')

    assert result.exit_code == 1
    assert 'secret' in unwrapped(result.stderr)
    assert not (sandbox / 'storix.toml').exists()


def test_set_allows_a_secret_in_user_scope_and_tightens_the_file(sandbox, tmp_path):
    """Given user scope, when a secret is set, then the file is owner-only."""
    result = run('config', 'set', 'azure.credential', 'hunter2', '--scope', 'user')

    user_file = tmp_path / 'xdg' / 'storix' / 'config.toml'
    assert result.exit_code == 0
    assert user_file.is_file()
    assert stat.S_IMODE(user_file.stat().st_mode) == 0o600


def test_set_refuses_a_key_the_provider_does_not_have(sandbox):
    """Given an unknown field, when set, then the file is left untouched."""
    result = run('config', 'set', 's3.nope', 'x')

    assert result.exit_code == 1
    assert not (sandbox / 'storix.toml').exists()


def test_unset_removes_only_that_key(sandbox):
    """Given two keys, when one is unset, then the other survives."""
    run('config', 'set', 's3.bucket', 'media')
    run('config', 'set', 's3.region', 'auto')

    assert run('config', 'unset', 's3.region').exit_code == 0
    text = (sandbox / 'storix.toml').read_text(encoding='utf-8')
    assert 'bucket = "media"' in text
    assert 'region' not in text


def test_show_redacts_secrets_including_inside_profiles(sandbox):
    """Given secrets anywhere, when shown, then none of them are printed."""
    (sandbox / 'storix.toml').write_text(
        '[azure]\ncredential = "top-secret"\n\n'
        '[profiles.media]\nprovider = "azure"\ncredential = "profile-secret"\n\n'
        '[profiles.media.environments.prod]\ncredential = "stage-secret"\n',
        encoding='utf-8',
    )

    result = run('config', 'show')

    assert result.exit_code == 0
    for literal in ('top-secret', 'profile-secret', 'stage-secret'):
        assert literal not in unwrapped(result.stdout)
    assert '***' in result.stdout


def test_profiles_lists_stages_and_marks_the_default(sandbox):
    """Given a profile, when listed, then its stages and default are shown."""
    (sandbox / 'storix.toml').write_text(
        '[profiles.media]\nprovider = "local"\ndefault_environment = "dev"\n\n'
        '[profiles.media.environments.dev]\nbase = "."\n\n'
        '[profiles.media.environments.prod]\nbase = "."\n',
        encoding='utf-8',
    )

    result = run('config', 'profiles')

    assert result.exit_code == 0
    assert 'media' in result.stdout
    assert 'dev*' in result.stdout


def test_init_writes_a_skeleton_and_will_not_clobber(sandbox):
    """Given an existing file, when init runs again, then it refuses."""
    assert run('config', 'init').exit_code == 0
    assert (sandbox / 'storix.toml').is_file()

    second = run('config', 'init')

    assert second.exit_code == 1
    assert '--force' in unwrapped(second.stderr)


def test_validate_reports_the_offending_file(sandbox):
    """Given an invalid file, when validated, then it is named."""
    (sandbox / 'storix.toml').write_text('[s3]\nnope = 1\n', encoding='utf-8')

    result = run('config', 'validate')

    assert result.exit_code == 1
    assert 'storix.toml' in unwrapped(result.stderr)


# --- self-documenting: the value in force, and a global-config shorthand ---


def test_get_effective_reports_a_default_rather_than_not_set(sandbox):
    """Given nothing configured, when asked for the effective value, then it says.

    `sx config get key` answering "not set in any config file" is true but
    unhelpful: the question behind it is what storix will actually do.
    """
    result = run('config', 'get', '--effective', 'azure.read_prefetch_size')

    assert result.exit_code == 0
    assert '8388608' in unwrapped(result.stdout)
    assert 'default' in unwrapped(result.stdout)


def test_get_effective_names_the_file_that_supplies_a_value(sandbox):
    """Given a configured value, when asked, then the source is reported."""
    (sandbox / 'storix.toml').write_text(
        '[azure]\nread_prefetch_size = "32MiB"\n', encoding='utf-8'
    )

    result = run('config', 'get', '--effective', 'azure.read_prefetch_size')

    assert '33554432' in unwrapped(result.stdout)
    assert 'project' in unwrapped(result.stdout)


def test_get_effective_covers_cli_preferences_and_top_level_settings(sandbox):
    """Given either kind of setting, when asked, then both resolve."""
    assert run('config', 'get', '--effective', 'cli.icons').exit_code == 0
    assert run('config', 'get', '--effective', 'max_transfer_ranges').exit_code == 0


def test_get_effective_redacts_a_secret_that_is_set(sandbox, monkeypatch):
    """Given a secret in force, when asked, then its value is not printed."""
    monkeypatch.setenv('STORIX_AZURE_CREDENTIAL', 'top-secret')

    result = run('config', 'get', '--effective', 'azure.credential')

    assert 'top-secret' not in unwrapped(result.stdout)
    assert '***' in result.stdout


def test_get_effective_rejects_a_key_that_is_not_a_setting(sandbox):
    """Given a typo, when asked, then it says so rather than inventing a value."""
    result = run('config', 'get', '--effective', 'azure.nope')

    assert result.exit_code == 1
    assert 'not a storix setting' in unwrapped(result.stderr)


def test_get_points_at_effective_when_a_key_is_unset(sandbox):
    """Given an unset key, when read from files, then the next step is named."""
    result = run('config', 'get', 'azure.read_prefetch_size')

    assert result.exit_code == 1
    assert '--effective' in unwrapped(result.stderr)


def test_user_is_shorthand_for_scope_user(sandbox, tmp_path):
    """Given --user, when setting, then the global config is what changes."""
    result = run('config', 'set', 's3.bucket', 'media', '--user')

    assert result.exit_code == 0
    assert (tmp_path / 'xdg' / 'storix' / 'config.toml').is_file()
    assert not (sandbox / 'storix.toml').exists()
