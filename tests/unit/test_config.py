"""The unified configuration loader (ADR 0031): discovery, precedence,
provenance, path anchoring, and the secret policy.

config.py is a hand-written top-level module (not a codegen twin), so its
tests live here as a loose unit file, mirroring test_errors.py.
"""

from collections.abc import Generator
from pathlib import Path

import pytest

from pydantic import ValidationError

from storix import get_storage
from storix.config import (
    AzureConfig,
    LocalConfig,
    S3Config,
    StorixSettings,
    config_provenance,
    find_project_config,
    is_secret,
    secret_fields,
)
from storix.errors import ConfigurationError


_STORIX_ENV = (
    'STORIX_PROVIDER',
    'STORIX_LOCAL_BASE',
    'STORIX_S3_BUCKET',
    'STORIX_S3_REGION',
    'STORIX_S3_ROOT',
    'STORIX_S3_ACCESS_KEY_ID',
)


@pytest.fixture
def sandbox(tmp_path, monkeypatch) -> Generator[Path]:
    """An isolated project cwd and empty XDG home, with no STORIX_* leakage."""
    project = tmp_path / 'project'
    project.mkdir()
    monkeypatch.chdir(project)
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path / 'xdg'))
    for var in _STORIX_ENV:
        monkeypatch.delenv(var, raising=False)
    yield project


def _user_config(tmp_path: Path, body: str) -> Path:
    """Write and return the XDG user config file for this sandbox."""
    file = tmp_path / 'xdg' / 'storix' / 'config.toml'
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(body)
    return file


# --- discovery and precedence ---


def test_project_toml_takes_effect(sandbox):
    # the previously silently-dropped [local] base now acts (gap 4 fixed)
    (sandbox / 'storix.toml').write_text('[local]\nbase = "data"\n')
    assert LocalConfig().base == str(sandbox / 'data')


def test_provider_table_reaches_get_storage(sandbox):
    (sandbox / 'storix.toml').write_text('[local]\nbase = "."\n')
    fs = get_storage('local')
    assert fs.backend._base == sandbox.resolve()


def test_precedence_env_beats_dotenv_beats_project_beats_user(sandbox, monkeypatch):
    _user_config(sandbox.parent, '[local]\nbase = "/from/user"\n')
    (sandbox / 'storix.toml').write_text('[local]\nbase = "/from/project"\n')
    assert LocalConfig().base == '/from/project'  # project beats user

    (sandbox / '.env').write_text('STORIX_LOCAL_BASE=/from/dotenv\n')
    assert LocalConfig().base == '/from/dotenv'  # .env beats project

    monkeypatch.setenv('STORIX_LOCAL_BASE', '/from/env')
    assert LocalConfig().base == '/from/env'  # env beats .env

    assert LocalConfig(base='/from/kwarg').base == '/from/kwarg'  # kwargs strongest


def test_storix_toml_wins_over_hidden_alias(sandbox):
    (sandbox / 'storix.toml').write_text('[local]\nbase = "/visible"\n')
    (sandbox / '.storix.toml').write_text('[local]\nbase = "/hidden"\n')
    assert LocalConfig().base == '/visible'


def test_pyproject_tool_storix_section(sandbox):
    (sandbox / 'pyproject.toml').write_text('[tool.storix.local]\nbase = "/proj"\n')
    assert LocalConfig().base == '/proj'


def test_upward_walk_anchors_at_the_first_file(sandbox):
    (sandbox / 'storix.toml').write_text('[local]\nbase = "shared"\n')
    nested = sandbox / 'sub' / 'deep'
    nested.mkdir(parents=True)
    import os

    os.chdir(nested)
    # the walk finds the ancestor file; its base anchors at that file's dir
    assert LocalConfig().base == str(sandbox / 'shared')


# --- unknown keys and tables ---


def test_unknown_section_key_errors_naming_file_and_key(sandbox):
    (sandbox / 'storix.toml').write_text('[local]\nbaze = "x"\n')
    with pytest.raises(ConfigurationError) as exc:
        LocalConfig()
    assert 'baze' in str(exc.value)
    assert 'storix.toml' in str(exc.value)


def test_unknown_top_level_table_errors(sandbox):
    (sandbox / 'storix.toml').write_text('[databse]\nx = 1\n')
    with pytest.raises(ConfigurationError) as exc:
        find_project_config()
    assert 'databse' in str(exc.value)
    assert 'known' in str(exc.value)


def test_profiles_are_rejected_with_a_clear_message(sandbox):
    (sandbox / 'storix.toml').write_text('[profiles.media]\nprovider = "azure"\n')
    with pytest.raises(ConfigurationError) as exc:
        find_project_config()
    assert 'profiles' in str(exc.value)


def test_malformed_toml_names_the_file(sandbox):
    (sandbox / 'storix.toml').write_text('[local\nbase = "x"\n')
    with pytest.raises(ConfigurationError) as exc:
        find_project_config()
    assert 'storix.toml' in str(exc.value)
    assert 'TOML' in str(exc.value)


# --- relative path anchoring per scope ---


def test_project_relative_path_anchors_to_file_dir(sandbox):
    (sandbox / 'storix.toml').write_text('[local]\nbase = "."\n')
    assert LocalConfig().base == str(sandbox)


def test_user_relative_path_is_rejected(sandbox):
    _user_config(sandbox.parent, '[local]\nbase = "relative/dir"\n')
    with pytest.raises(ConfigurationError) as exc:
        LocalConfig()
    assert 'absolute' in str(exc.value)


def test_user_absolute_path_is_accepted(sandbox):
    _user_config(sandbox.parent, '[local]\nbase = "/abs/dir"\n')
    assert LocalConfig().base == '/abs/dir'


# --- secret policy ---


def test_literal_secret_in_project_scope_is_rejected(sandbox):
    (sandbox / 'storix.toml').write_text('[s3]\naccess_key_id = "AKIALITERAL"\n')
    with pytest.raises(ConfigurationError) as exc:
        S3Config()
    assert 'access_key_id' in str(exc.value)
    assert 'secret' in str(exc.value)


def test_env_reference_resolves_a_secret(sandbox, monkeypatch):
    monkeypatch.setenv('MY_S3_KEY', 'resolved-value')
    (sandbox / 'storix.toml').write_text('[s3]\naccess_key_id = "env:MY_S3_KEY"\n')
    assert S3Config().access_key_id == 'resolved-value'


def test_env_reference_missing_variable_errors_naming_var_and_file(sandbox):
    (sandbox / 'storix.toml').write_text('[s3]\naccess_key_id = "env:ABSENT_KEY"\n')
    with pytest.raises(ConfigurationError) as exc:
        S3Config()
    assert 'ABSENT_KEY' in str(exc.value)
    assert 'storix.toml' in str(exc.value)


def test_world_readable_user_file_with_secret_warns(sandbox):
    file = _user_config(sandbox.parent, '[s3]\naccess_key_id = "literal-ok-in-user"\n')
    file.chmod(0o644)  # group/world readable
    with pytest.warns(UserWarning, match='group/world-readable'):
        assert S3Config().access_key_id == 'literal-ok-in-user'


# --- provenance and field markers ---


def test_provenance_reports_the_effective_source(sandbox, monkeypatch):
    (sandbox / 'storix.toml').write_text('[s3]\nbucket = "b"\nregion = "us"\n')
    monkeypatch.setenv('STORIX_S3_REGION', 'from-env')
    prov = config_provenance('s3', endpoint='http://x')
    assert prov['endpoint'] == 'override'
    assert prov['region'] == 'env'  # env beats the project TOML region
    assert prov['bucket'] == 'project'
    assert prov['root'] == 'default'


def test_provenance_of_unknown_provider_is_empty(sandbox):
    assert config_provenance('memory') == {}


def test_secret_fields_are_marked_on_the_models():
    assert secret_fields(S3Config) == {'access_key_id', 'secret_access_key'}
    assert is_secret(S3Config, 'bucket') is False


@pytest.mark.parametrize(
    ('spelled', 'expected'),
    [
        ('8388608', 8388608),  # a plain byte count still works
        ('8MiB', 8 * 1024 * 1024),  # IEC: a power of two
        ('8MB', 8_000_000),  # SI: a power of ten, and not a synonym
        ('8 MiB', 8 * 1024 * 1024),  # a space is allowed
        ('8mib', 8 * 1024 * 1024),  # case does not matter
        ('512KiB', 512 * 1024),
    ],
)
def test_transfer_sizes_accept_human_readable_spellings(
    monkeypatch, spelled: str, expected: int
):
    """Given a size as text, when settings load, then it resolves to bytes."""
    monkeypatch.setenv('STORIX_AZURE_READ_CHUNK_SIZE', spelled)

    assert AzureConfig().read_chunk_size == expected


def test_every_provider_shares_the_spelling(monkeypatch):
    """Given each provider's variable, when set, then all parse the same way."""
    monkeypatch.setenv('STORIX_S3_WRITE_CHUNK_SIZE', '2MiB')
    monkeypatch.setenv('STORIX_LOCAL_READ_CHUNK_SIZE', '512KiB')

    assert S3Config().write_chunk_size == 2 * 1024 * 1024
    assert LocalConfig().read_chunk_size == 512 * 1024


def test_a_nonsense_size_is_rejected_by_name(monkeypatch):
    """Given an unreadable size, when settings load, then it says so."""
    monkeypatch.setenv('STORIX_AZURE_READ_CHUNK_SIZE', '8 potatoes')

    with pytest.raises(ValidationError, match='byte unit'):
        AzureConfig()


def test_a_non_positive_size_is_rejected(monkeypatch):
    """Given zero, when settings load, then the positive bound still holds."""
    monkeypatch.setenv('STORIX_AZURE_WRITE_CHUNK_SIZE', '0')

    with pytest.raises(ValidationError, match='greater than 0'):
        AzureConfig()


def test_transfer_ranges_stays_a_count(monkeypatch):
    """Given a range ceiling, when settings load, then it is a plain count."""
    monkeypatch.setenv('STORIX_MAX_TRANSFER_RANGES', '4')

    assert StorixSettings().max_transfer_ranges == 4


def test_transfer_knobs_are_legal_in_toml(sandbox):
    """Given transfer settings in a file, when loaded, then they take effect.

    The knobs shipped as environment-only; ADR 0031's loader is what gives
    them a file. Top-level keys are derived from ``StorixSettings``, so a
    new one is legal the day it is added rather than erroring as unknown.
    """
    (sandbox / 'storix.toml').write_text(
        'max_transfer_ranges = 2\n\n[local]\nbase = "."\nread_chunk_size = 262144\n',
        encoding='utf-8',
    )

    assert StorixSettings().max_transfer_ranges == 2
    assert LocalConfig().read_chunk_size == 262144
