"""The unified configuration loader (ADR 0031): discovery, precedence,
provenance, path anchoring, and the secret policy.

config.py is a hand-written top-level module (not a codegen twin), so its
tests live here as a loose unit file, mirroring test_errors.py.
"""

import sys

from collections.abc import Generator
from pathlib import Path

import pytest

from pydantic import ValidationError

from storix import get_storage
from storix.config import (
    PROVIDER_MODELS,
    PROVIDER_REQUIRES,
    AzureConfig,
    DiscoveredConfig,
    LocalConfig,
    S3Config,
    StorixSettings,
    _resolve_secret,
    config_provenance,
    configured_profile,
    extra_installed,
    find_project_config,
    install_hint,
    installed_extras,
    is_secret,
    resolve_profile,
    secret_fields,
    upgrade_command,
    user_config_path,
)
from storix.errors import ConfigurationError


def host_absolute(*parts: str) -> str:
    """An absolute host path built from POSIX-shaped segments.

    ``base`` names a real directory, and the loader is right to treat
    ``/from/user`` as relative on Windows, where a path with no drive is
    relative to the current one. Anchoring at the temporary directory's
    drive keeps such test data absolute wherever it runs. The result
    carries backslashes there, so it belongs in a TOML literal string
    (single quotes), never a basic string that would read them as escapes.
    """
    import tempfile

    return str(Path(Path(tempfile.gettempdir()).anchor, *parts))


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
    user, project = host_absolute('from', 'user'), host_absolute('from', 'project')
    dotenv, env = host_absolute('from', 'dotenv'), host_absolute('from', 'env')
    _user_config(sandbox.parent, f"[local]\nbase = '{user}'\n")
    (sandbox / 'storix.toml').write_text(f"[local]\nbase = '{project}'\n")
    assert LocalConfig().base == project  # project beats user

    (sandbox / '.env').write_text(f'STORIX_LOCAL_BASE={dotenv}\n')
    assert LocalConfig().base == dotenv  # .env beats project

    monkeypatch.setenv('STORIX_LOCAL_BASE', env)
    assert LocalConfig().base == env  # env beats .env

    kwarg = host_absolute('from', 'kwarg')
    assert LocalConfig(base=kwarg).base == kwarg  # kwargs strongest


def test_storix_toml_wins_over_hidden_alias(sandbox):
    visible, hidden = host_absolute('visible'), host_absolute('hidden')
    (sandbox / 'storix.toml').write_text(f"[local]\nbase = '{visible}'\n")
    (sandbox / '.storix.toml').write_text(f"[local]\nbase = '{hidden}'\n")
    assert LocalConfig().base == visible


def test_pyproject_tool_storix_section(sandbox):
    proj = host_absolute('proj')
    (sandbox / 'pyproject.toml').write_text(f"[tool.storix.local]\nbase = '{proj}'\n")
    assert LocalConfig().base == proj


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


def test_a_profile_supplies_its_provider_and_settings(sandbox):
    """Given a profile, when selected, then it decides provider and settings."""
    (sandbox / 'data').mkdir()
    (sandbox / 'storix.toml').write_text(
        '[profiles.media]\nprovider = "local"\nbase = "data"\n'
        'read_chunk_size = "2MiB"\n',
        encoding='utf-8',
    )

    fs = get_storage(profile='media')

    assert fs.backend.base.name == 'data'
    assert fs.backend.default_read_chunk_size == 2 * 1024 * 1024


def test_an_environment_overlays_the_profile(sandbox):
    """Given a stage overlay, when selected, then it wins over the base."""
    (sandbox / 'dev').mkdir()
    (sandbox / 'prod').mkdir()
    (sandbox / 'storix.toml').write_text(
        '[profiles.media]\nprovider = "local"\nbase = "dev"\n\n'
        '[profiles.media.environments.prod]\nbase = "prod"\n',
        encoding='utf-8',
    )

    assert get_storage(profile='media').backend.base.name == 'dev'
    assert get_storage(profile='media', environment='prod').backend.base.name == 'prod'


def test_an_unknown_profile_lists_what_exists(sandbox):
    """Given a name that is not defined, when selected, then it says what is."""
    (sandbox / 'storix.toml').write_text(
        '[profiles.media]\nprovider = "local"\n', encoding='utf-8'
    )

    with pytest.raises(ConfigurationError, match='unknown profile'):
        get_storage(profile='archive')


def test_an_unknown_environment_lists_the_profile_stages(sandbox):
    """Given a stage that is not defined, when selected, then it says which are."""
    (sandbox / 'storix.toml').write_text(
        '[profiles.media]\nprovider = "local"\nbase = "."\n\n'
        '[profiles.media.environments.prod]\nbase = "."\n',
        encoding='utf-8',
    )

    with pytest.raises(ConfigurationError, match='available: prod'):
        get_storage(profile='media', environment='staging')


def test_an_environment_without_a_profile_is_an_error(sandbox):
    """Given no profile, when a stage is selected, then it is refused."""
    with pytest.raises(ConfigurationError, match='name one with profile='):
        get_storage(environment='prod')


def test_a_profile_refuses_a_conflicting_provider(sandbox):
    """Given a profile, when another provider is named, then it is an error."""
    (sandbox / 'storix.toml').write_text(
        '[profiles.media]\nprovider = "local"\nbase = "."\n',
        encoding='utf-8',
    )

    with pytest.raises(ConfigurationError, match='names its own provider'):
        get_storage('memory', profile='media')


def test_an_overlay_cannot_switch_the_provider(sandbox):
    """Given an overlay naming a provider, when read, then the file is refused."""
    (sandbox / 'storix.toml').write_text(
        '[profiles.media]\nprovider = "local"\n\n'
        '[profiles.media.environments.prod]\nprovider = "memory"\n',
        encoding='utf-8',
    )

    with pytest.raises(ConfigurationError, match='cannot change'):
        find_project_config()


def test_a_profile_must_name_a_known_provider(sandbox):
    """Given a profile without a usable provider, when read, then it is refused."""
    (sandbox / 'storix.toml').write_text(
        '[profiles.media]\nprovider = "nope"\n', encoding='utf-8'
    )

    with pytest.raises(ConfigurationError, match='unknown provider'):
        find_project_config()


def test_a_project_profile_shadows_a_user_profile_of_the_same_name(sandbox, tmp_path):
    """Given both scopes define a name, when resolved, then the project wins."""
    (sandbox / 'project').mkdir()
    _user_config(tmp_path, '[profiles.media]\nprovider = "memory"\n')
    (sandbox / 'storix.toml').write_text(
        '[profiles.media]\nprovider = "local"\nbase = "project"\n',
        encoding='utf-8',
    )

    resolved = resolve_profile('media')

    assert resolved.provider == 'local'
    assert resolved.source == sandbox / 'storix.toml'


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
    absolute = host_absolute('abs', 'dir')
    _user_config(sandbox.parent, f"[local]\nbase = '{absolute}'\n")
    assert LocalConfig().base == absolute


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


def test_an_env_reference_falls_back_to_the_project_dotenv(sandbox, monkeypatch):
    """Given a secret only in .env, when a config references it, then it resolves.

    `.env` is already a first-class source for `STORIX_*`, so the same file
    must not be invisible to an `env:` reference.
    """
    monkeypatch.delenv('MEDIA_SECRET', raising=False)
    (sandbox / '.env').write_text('MEDIA_SECRET=from-dotenv\n', encoding='utf-8')
    disc = DiscoveredConfig(sandbox / 'storix.toml', {}, 'project')

    assert _resolve_secret(disc, 'credential', 'env:MEDIA_SECRET') == 'from-dotenv'


def test_the_process_environment_beats_the_dotenv(sandbox, monkeypatch):
    """Given both, when a reference resolves, then the export wins."""
    (sandbox / '.env').write_text('MEDIA_SECRET=from-dotenv\n', encoding='utf-8')
    monkeypatch.setenv('MEDIA_SECRET', 'from-environment')
    disc = DiscoveredConfig(sandbox / 'storix.toml', {}, 'project')

    assert _resolve_secret(disc, 'credential', 'env:MEDIA_SECRET') == 'from-environment'


def test_a_reference_set_nowhere_names_both_places(sandbox, monkeypatch):
    """Given a reference to nothing, when read, then it says where it looked."""
    monkeypatch.delenv('MEDIA_SECRET', raising=False)
    disc = DiscoveredConfig(sandbox / 'storix.toml', {}, 'project')

    with pytest.raises(ConfigurationError, match='neither in the environment nor'):
        _resolve_secret(disc, 'credential', 'env:MEDIA_SECRET')


def test_a_config_file_can_pin_a_default_profile(sandbox, tmp_path):
    """Given a pinned profile, when read, then the loader reports it.

    The pin is what ``sx`` selects from. It stops there: a library
    session is never steered by a file's default, only by an explicit
    ``profile=``.
    """
    (sandbox / 'data').mkdir()
    (sandbox / 'storix.toml').write_text(
        'profile = "media"\n\n[profiles.media]\nprovider = "local"\nbase = "data"\n',
        encoding='utf-8',
    )

    assert configured_profile() == 'media'
    assert get_storage().backend.base.name != 'data'
    assert get_storage(profile='media').backend.base.name == 'data'


def test_a_profile_refuses_a_setting_from_another_provider(sandbox):
    """Given a stray provider table, when read, then it is named, not ignored."""
    (sandbox / 'storix.toml').write_text(
        '[profiles.media]\nprovider = "azure"\nlocal = { base = "." }\n',
        encoding='utf-8',
    )

    with pytest.raises(ConfigurationError, match="has no setting 'local'"):
        find_project_config()


def test_a_default_environment_applies_without_a_flag(sandbox):
    """Given a default stage, when none is selected, then it is applied."""
    (sandbox / 'dev').mkdir()
    (sandbox / 'prod').mkdir()
    (sandbox / 'storix.toml').write_text(
        '[profiles.media]\nprovider = "local"\ndefault_environment = "dev"\n\n'
        '[profiles.media.environments.dev]\nbase = "dev"\n\n'
        '[profiles.media.environments.prod]\nbase = "prod"\n',
        encoding='utf-8',
    )

    assert get_storage(profile='media').backend.base.name == 'dev'
    assert get_storage(profile='media', environment='prod').backend.base.name == 'prod'


def test_a_default_environment_must_exist(sandbox):
    """Given a default naming nothing, when read, then the file is refused."""
    (sandbox / 'storix.toml').write_text(
        '[profiles.media]\nprovider = "local"\ndefault_environment = "nope"\n',
        encoding='utf-8',
    )

    with pytest.raises(ConfigurationError, match='not one of its environments'):
        find_project_config()


# --- the tracked example file stays in step with the schema ---


def _example_document() -> dict[str, object]:
    """The repository's storix.toml.example, parsed."""
    import tomllib

    root = Path(__file__).resolve().parents[2]
    return tomllib.loads((root / 'storix.toml.example').read_text(encoding='utf-8'))


def test_the_example_config_is_accepted_by_the_loader(sandbox):
    """Given the shipped example, when read as a project file, then it loads.

    The example is documentation that rots silently, so it is validated
    against the real models: a key that storix stopped accepting, or a
    provider table that grew a field the example never learned, fails here.
    """
    source = Path(__file__).resolve().parents[2] / 'storix.toml.example'
    (sandbox / 'storix.toml').write_text(
        source.read_text(encoding='utf-8'), encoding='utf-8'
    )

    discovered = find_project_config()

    assert discovered is not None
    assert discovered.path == sandbox / 'storix.toml'


def test_the_example_config_shows_every_provider_and_setting():
    """Given a new provider or setting, when it lands, then the example has it.

    Fails the moment a provider model gains a field the example does not
    mention, which is the point: the next configuration PR updates it.
    """
    document = _example_document()

    for provider, model in PROVIDER_MODELS.items():
        assert provider in document, f'{provider} missing from storix.toml.example'
        section = document[provider]
        assert isinstance(section, dict)
        documented = set(section)
        missing = set(model.model_fields) - documented
        assert not missing, f'[{provider}] is missing {sorted(missing)}'

    top_level = set(StorixSettings.model_fields) | {'profile'}
    assert top_level <= set(document), sorted(top_level - set(document))


# --- the user config lives where each platform expects it ---


def test_the_user_config_follows_xdg_when_it_is_set(monkeypatch, tmp_path):
    """Given XDG_CONFIG_HOME, when resolved, then it wins on any platform."""
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path))

    assert user_config_path() == tmp_path / 'storix' / 'config.toml'


def test_the_user_config_uses_appdata_on_windows(monkeypatch, tmp_path):
    """Given Windows, when resolved, then it is %APPDATA%, not ~/.config.

    A Windows user expects per-user application data under APPDATA; storix
    installs itself with PowerShell there, so it should not scatter a unix
    convention across their home directory.
    """
    monkeypatch.delenv('XDG_CONFIG_HOME', raising=False)
    monkeypatch.setattr(sys, 'platform', 'win32')
    monkeypatch.setenv('APPDATA', str(tmp_path / 'Roaming'))

    assert user_config_path() == tmp_path / 'Roaming' / 'storix' / 'config.toml'


def test_the_user_config_uses_dot_config_elsewhere(monkeypatch):
    """Given a unix platform, when resolved, then it is ~/.config."""
    monkeypatch.delenv('XDG_CONFIG_HOME', raising=False)
    monkeypatch.setattr(sys, 'platform', 'linux')

    assert user_config_path().parts[-3:] == ('.config', 'storix', 'config.toml')


def test_a_stage_supplied_field_is_reported_apart_from_its_profile(
    tmp_path, monkeypatch
):
    """Given a stage overlay, when provenance is read, then the stage is named.

    "Why is dev pointing at the prod bucket" is answered by which of the
    two supplied the value, not by knowing a profile was involved.
    """
    from storix.config import config_provenance

    (tmp_path / 'storix.toml').write_text(
        '[profiles.media]\nprovider = "s3"\nregion = "auto"\n\n'
        '[profiles.media.environments.prod]\nbucket = "media-prod"\n',
        encoding='utf-8',
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path / 'xdg'))

    sources = config_provenance('s3', profile='media', environment='prod')

    assert sources['bucket'] == 'environment'
    assert sources['region'] == 'profile'


def test_a_pinned_profile_does_not_reach_the_library(tmp_path, monkeypatch):
    """Given a pinned profile, when get_storage names a provider, then it wins.

    A pin is a person's convenience at a prompt. Letting it steer the
    library means a personal file can point an application at another
    account, and that two providers cannot be opened side by side.
    """
    from storix import get_storage

    (tmp_path / 'storix.toml').write_text(
        'profile = "azurish"\n\n[profiles.azurish]\nprovider = "azure"\n'
        'container = "raw"\naccount_name = "acct"\n',
        encoding='utf-8',
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path / 'xdg'))
    monkeypatch.setenv('STORIX_LOCAL_BASE', str(tmp_path / 'data'))

    fs = get_storage('local')

    assert fs.backend.base == tmp_path / 'data'


def test_two_providers_open_side_by_side_under_a_pin(tmp_path, monkeypatch):
    """Given a pin, when two providers are opened, then neither is redirected.

    The shape every migration takes: read from one store, write to
    another, in one process.
    """
    from storix import get_storage

    (tmp_path / 'storix.toml').write_text(
        'profile = "azurish"\n\n[profiles.azurish]\nprovider = "azure"\n'
        'container = "raw"\naccount_name = "acct"\n',
        encoding='utf-8',
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path / 'xdg'))
    monkeypatch.setenv('STORIX_LOCAL_BASE', str(tmp_path / 'data'))

    src = get_storage('memory')
    dst = get_storage('local')

    assert type(src.backend).__name__ == 'MemoryBackend'
    assert type(dst.backend).__name__ == 'LocalBackend'


def test_the_library_still_selects_a_profile_when_asked(tmp_path, monkeypatch):
    """Given profile=, when get_storage runs, then the profile applies."""
    from storix import get_storage

    (tmp_path / 'data').mkdir()
    (tmp_path / 'storix.toml').write_text(
        f'[profiles.here]\nprovider = "local"\nbase = \'{tmp_path / "data"}\'\n',
        encoding='utf-8',
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path / 'xdg'))

    fs = get_storage(profile='here')

    assert fs.backend.base == tmp_path / 'data'


def test_a_profile_layers_over_the_provider_table(tmp_path, monkeypatch):
    """Given shared settings in [s3], when a profile is used, then it inherits.

    This is what keeps several buckets on one account from repeating the
    endpoint and keys, which is the pressure that makes people model
    unrelated buckets as stages.
    """
    from storix.config import config_provenance

    (tmp_path / 'storix.toml').write_text(
        '[s3]\nregion = "auto"\n\n[profiles.media]\nprovider = "s3"\n'
        'bucket = "media"\n',
        encoding='utf-8',
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path / 'xdg'))

    sources = config_provenance('s3', profile='media')

    assert sources['bucket'] == 'profile'
    assert sources['region'] == 'project'


def test_a_singular_environment_table_names_the_right_spelling(tmp_path, monkeypatch):
    """Given [environment], when loaded, then the error names [environments].

    The plain unknown-key message sends the reader looking for a provider
    setting that was never the problem.
    """
    from storix.config import find_project_config

    (tmp_path / 'storix.toml').write_text(
        '[profiles.media]\nprovider = "s3"\n\n'
        '[profiles.media.environment.dev]\nbucket = "media-dev"\n',
        encoding='utf-8',
    )
    monkeypatch.chdir(tmp_path)

    with pytest.raises(ConfigurationError) as exc_info:
        find_project_config()

    assert 'environments' in str(exc_info.value)
    assert 'profiles.media.environments.dev' in str(exc_info.value)


def test_installed_extras_reads_the_uv_receipt(tmp_path, monkeypatch):
    """Given a uv tool layout, when read, then the requested extras come back.

    The environment holds the resulting packages, not the request that
    produced them; uv's receipt is the only place the answer exists.
    """
    (tmp_path / 'uv-receipt.toml').write_text(
        '[tool]\nrequirements = [{ name = "storix", extras = ["cli", "s3"] }]\n',
        encoding='utf-8',
    )
    monkeypatch.setattr(sys, 'prefix', str(tmp_path))

    assert installed_extras() == frozenset({'cli', 's3'})


def test_installed_extras_is_empty_without_a_receipt(tmp_path, monkeypatch):
    """Given no receipt, when read, then it reports nothing rather than raising.

    Every other installation kind reaches this, and the callers that care
    check installation_kind() before acting on it.
    """
    monkeypatch.setattr(sys, 'prefix', str(tmp_path))

    assert installed_extras() == frozenset()


def test_a_uv_tool_install_is_told_to_use_sx_install(tmp_path, monkeypatch):
    """Given a uv tool install, when an extra is missing, then sx offers itself.

    sx can rewrite its own tool environment, so quoting a uv command the
    reader has to retype is advice that predates the capability.
    """
    (tmp_path / 'uv-receipt.toml').write_text('[tool]\n', encoding='utf-8')
    monkeypatch.setattr(sys, 'prefix', str(tmp_path))

    assert install_hint('s3') == 'sx install s3'
    # except for cli itself: sx cannot run to install what makes it run
    assert 'uv tool install' in install_hint('cli')


def test_a_project_install_still_gets_the_pip_form(tmp_path, monkeypatch):
    """Given no receipt, when an extra is missing, then the remedy is pip."""
    monkeypatch.setattr(sys, 'prefix', str(tmp_path))

    assert 'pip install' in install_hint('s3')


def test_an_absent_module_makes_its_extra_not_installed(monkeypatch):
    """Given a provider whose module is missing, when probed, then it is absent.

    The dev environment installs every extra, so the missing case is only
    reachable by naming a module that cannot exist.
    """
    monkeypatch.setitem(PROVIDER_REQUIRES, 'local', ('storix_no_such_engine',))

    assert extra_installed('local') is False
    assert extra_installed('memory') is True


def test_a_provider_reports_its_missing_extra_before_its_missing_config(monkeypatch):
    """Given no engine, when a session opens, then the extra is what fails.

    A credential message is not actionable advice for someone who has no
    engine to use the credential with (ADR 0031 D7).
    """
    monkeypatch.setitem(PROVIDER_REQUIRES, 's3', ('storix_no_such_engine',))
    monkeypatch.delenv('STORIX_S3_BUCKET', raising=False)

    with pytest.raises(ModuleNotFoundError) as exc_info:
        get_storage('s3')

    assert 'storix[s3]' in str(exc_info.value)


def test_an_unknown_provider_needs_no_extra(monkeypatch):
    """Given a registered third-party provider, when opened, then nothing blocks.

    PROVIDER_REQUIRES lists what storix ships; a backend it has never heard
    of brings its own dependencies and must not be gated on this table.
    """
    from storix import register_backend
    from storix.backends import MemoryBackend

    register_backend('storix_test_plugin', lambda **_: MemoryBackend())

    assert extra_installed('storix_test_plugin') is True
    assert get_storage('storix_test_plugin') is not None


def test_upgrade_command_crosses_a_pin_and_keeps_the_extras(tmp_path, monkeypatch):
    """Given a pinned uv tool install, when upgrading, then it reinstalls at
    @latest with the receipt's extras.

    `sx install` pins to the running version every time it adds an extra,
    and `uv tool upgrade` will not cross that pin - so upgrading that way
    is a permanent no-op for anyone who ever added a backend.
    """
    (tmp_path / 'uv-receipt.toml').write_text(
        '[tool]\nrequirements = [{ name = "storix", extras = ["cli", "s3"] }]\n',
        encoding='utf-8',
    )
    monkeypatch.setattr(sys, 'prefix', str(tmp_path))

    argv = upgrade_command()

    assert argv == [
        'uv',
        'tool',
        'install',
        '--force',
        '--refresh-package=storix',
        'storix[cli,s3]@latest',
    ]


def test_upgrade_command_can_target_an_exact_version(tmp_path, monkeypatch):
    (tmp_path / 'uv-receipt.toml').write_text(
        '[tool]\nrequirements = [{ name = "storix", extras = ["cli"] }]\n',
        encoding='utf-8',
    )
    monkeypatch.setattr(sys, 'prefix', str(tmp_path))

    assert upgrade_command('0.5.1')[-1] == 'storix[cli]@0.5.1'


def test_upgrade_command_outside_a_uv_tool_stays_the_printed_pip_form(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(sys, 'prefix', str(tmp_path))

    assert upgrade_command()[1:] == ['-m', 'pip', 'install', '--upgrade', 'storix']
    assert upgrade_command('0.5.1')[-1] == 'storix==0.5.1'
