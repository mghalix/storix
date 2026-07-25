"""Standardized, namespaced configuration for storix backends.

One brand prefix, one model per backend: ``STORIX_PROVIDER`` picks the
backend, ``STORIX_<PROVIDER>_*`` configures it, and every field can be
overridden per-call through ``get_storage(**overrides)``. Values are
read, strongest first, from explicit overrides, the process environment,
a local ``.env`` file, the nearest project TOML, and the XDG user file
(ADR 0031).

This is the single loader shared by the library and the ``sx`` CLI: it
discovers the config files once (``find_project_config`` /
``find_user_config``), extracts each provider section, validates it
through the per-provider pydantic-settings models below, and records
which source supplied each effective field (``config_provenance``).
"""

from __future__ import annotations

import os
import re
import sys
import tempfile
import tomllib
import warnings

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, Final, Literal, cast, get_args

from dotenv import dotenv_values
from pydantic import ByteSize, Field
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

from storix.constants import (
    DEFAULT_AZURE_READ_CHUNK_SIZE,
    DEFAULT_AZURE_READ_PREFETCH_SIZE,
    DEFAULT_AZURE_WRITE_CHUNK_SIZE,
    DEFAULT_READ_CHUNK_SIZE,
    DEFAULT_TRANSFER_RANGES,
    DEFAULT_WRITE_CHUNK_SIZE,
)
from storix.errors import ConfigurationError
from storix.types import StorageProvider


if TYPE_CHECKING:
    from collections.abc import Callable

    from pydantic.fields import FieldInfo


type ConfigSource = Literal[
    'override', 'profile', 'env', 'dotenv', 'project', 'user', 'default'
]
"""Where an effective config field came from, strongest first: an explicit
``get_storage`` keyword or CLI flag (``override``), the process environment
(``env``), the project ``.env`` (``dotenv``), the project TOML (``project``),
the XDG user file (``user``), or the model's built-in default (``default``)."""

type _Scope = Literal['project', 'user']


# --- config file discovery (shared by provider config and CLI preferences) ---


@dataclass(frozen=True)
class DiscoveredConfig:
    """A parsed storix config file plus where it came from.

    Args:
        path: The file on disk (a ``storix.toml``, ``.storix.toml``, a
            ``pyproject.toml``, or the XDG ``config.toml``).
        data: The storix table: the whole document for a standalone file,
            the ``[tool.storix]`` subtree for a ``pyproject.toml``.
        scope: ``'project'`` for an upward-walked project file, ``'user'``
            for the XDG user file. Governs relative-path and secret policy.
    """

    path: Path
    data: dict[str, Any]
    scope: _Scope


_PROJECT_FILES: Final[tuple[str, ...]] = ('storix.toml', '.storix.toml')
"""Standalone project files, most-preferred first (``storix.toml`` wins;
``.storix.toml`` is a compatibility-only read alias, ADR 0031)."""


def _read_toml(path: Path) -> dict[str, Any]:
    """Parse a TOML file; an unreadable file is treated as absent.

    Raises:
        ConfigurationError: If the file exists but is not valid TOML,
            naming the file.
    """
    try:
        return tomllib.loads(path.read_text('utf-8'))
    except tomllib.TOMLDecodeError as exc:
        msg = f'{path}: invalid TOML ({exc})'
        raise ConfigurationError(msg) from exc
    except OSError:
        return {}


def _table(document: object, *keys: str) -> dict[str, Any] | None:
    """Descend ``keys`` into a parsed TOML document; None when absent."""
    node: object = document
    for key in keys:
        if not isinstance(node, dict):
            return None
        section = cast('dict[str, Any]', node)
        if key not in section:
            return None
        node = section[key]
    return cast('dict[str, Any]', node) if isinstance(node, dict) else None


def find_project_config() -> DiscoveredConfig | None:
    """The nearest project config, ruff-style: walk upward from cwd.

    Per directory, ``storix.toml`` wins over ``.storix.toml``, else a
    ``pyproject.toml`` carrying a ``[tool.storix]`` table. The first file
    found anchors the project and stops the walk, even when it holds no
    settings.

    Raises:
        ConfigurationError: If the anchored file is malformed or holds an
            unknown top-level table.
    """
    cwd = Path.cwd()
    for directory in (cwd, *cwd.parents):
        for name in _PROJECT_FILES:
            file = directory / name
            if file.is_file():
                data = _read_toml(file)
                _validate_document(file, data)
                return DiscoveredConfig(file, data, 'project')
        pyproject = directory / 'pyproject.toml'
        if pyproject.is_file():
            tool = _table(_read_toml(pyproject), 'tool', 'storix')
            if tool is not None:
                _validate_document(pyproject, tool)
                return DiscoveredConfig(pyproject, tool, 'project')
    return None


def find_user_config() -> DiscoveredConfig | None:
    """The personal defaults, at this platform's user config location.

    Raises:
        ConfigurationError: If the file is malformed or holds an unknown
            top-level table.
    """
    file = user_config_path()
    if not file.is_file():
        return None
    data = _read_toml(file)
    _validate_document(file, data)
    return DiscoveredConfig(file, data, 'user')


def _validate_document(path: Path, data: dict[str, Any]) -> None:
    """Reject unknown top-level tables so a typo never silently does nothing.

    Raises:
        ConfigurationError: If a top-level key is not a known section, or if
            the ``[profiles]`` table is malformed.
    """
    _validate_profiles(path, data)
    unknown = [key for key in data if key not in _KNOWN_TOP_LEVEL]
    if unknown:
        known = ', '.join(sorted(_KNOWN_TOP_LEVEL))
        msg = f'{path}: unknown table {unknown[0]!r}; known: {known}'
        raise ConfigurationError(msg)


# --- per-source value extraction (section, path anchoring, secret policy) ---


def _section_values(
    disc: DiscoveredConfig, settings_cls: type[BaseSettings]
) -> dict[str, Any]:
    """Pull a provider section out of a discovered file, applying policy.

    Unknown keys are rejected, path fields are anchored per scope, and
    secret fields are resolved (``env:`` references) or refused (literal
    secrets in project scope).

    Raises:
        ConfigurationError: On an unknown key, a relative user-scope path,
            a literal project-scope secret, or a missing ``env:`` variable.
    """
    section_name: str | None = getattr(settings_cls, 'TOML_SECTION', None)
    fields = settings_cls.model_fields
    raw: dict[str, Any]
    if section_name is None:
        raw = {k: v for k, v in disc.data.items() if k in fields}
    else:
        node: Any = disc.data.get(section_name)
        raw = cast('dict[str, Any]', node) if isinstance(node, dict) else {}

    out: dict[str, Any] = {}
    for key, value in raw.items():
        if key not in fields:
            known = ', '.join(fields)
            where = f'[{section_name}]' if section_name else 'the top level'
            msg = f'{disc.path}: unknown key {key!r} in {where}; known: {known}'
            raise ConfigurationError(msg)
        if is_secret(settings_cls, key):
            out[key] = _resolve_secret(disc, key, value)
        elif is_path(settings_cls, key):
            out[key] = _anchor_path(disc, key, value)
        else:
            out[key] = value
    return out


def _dotenv_value(var: str) -> str | None:
    """Read one variable from the project ``.env``, if there is one.

    ``.env`` is already a first-class source for ``STORIX_*`` settings, so
    an ``env:`` reference looks there too rather than treating the same
    file as invisible depending on which spelling the user reached for.
    The process environment still wins: an explicit export beats a file.
    """
    file = Path.cwd() / '.env'
    if not file.is_file():
        return None
    return dotenv_values(file).get(var)


def _resolve_secret(disc: DiscoveredConfig, field: str, value: object) -> object:
    """Resolve a secret field's TOML value under the secret policy (D4).

    ``env:VAR`` resolves from the process environment, then the project
    ``.env``, in any scope; a literal is refused in project scope and
    warned about in user scope.

    Raises:
        ConfigurationError: On a literal secret in project scope, or an
            ``env:`` reference whose variable is set in neither place.
    """
    if isinstance(value, str) and value.startswith('env:'):
        var = value[len('env:') :]
        resolved = os.environ.get(var) or _dotenv_value(var)
        if resolved is None:
            msg = (
                f'{disc.path}: {field} references env:{var}, but {var} is set '
                f'neither in the environment nor in {Path.cwd() / ".env"}'
            )
            raise ConfigurationError(msg)
        return resolved
    if disc.scope == 'project':
        msg = (
            f'{disc.path}: {field} is a secret and project files are committed; '
            f'use env:VAR, the STORIX_* environment, or the user config '
            f'(~/.config/storix/config.toml)'
        )
        raise ConfigurationError(msg)
    _warn_if_world_readable(disc.path)
    return value


def _anchor_path(disc: DiscoveredConfig, field: str, value: object) -> object:
    """Anchor a relative path field per scope; ``~`` expands everywhere.

    Project paths resolve against the file's directory (``base = "."`` means
    this project); user paths must be absolute or ``~``-prefixed.

    Raises:
        ConfigurationError: On a relative path in the user scope.
    """
    if not isinstance(value, str):
        return value
    expanded = os.path.expanduser(value)  # noqa: PTH111 - normalize the raw string
    if Path(expanded).is_absolute():
        return expanded
    if disc.scope == 'user':
        msg = (
            f'{disc.path}: {field} must be an absolute or ~-prefixed path; a '
            f'relative user-global path is meaningless'
        )
        raise ConfigurationError(msg)
    return str(disc.path.parent / expanded)


def _warn_if_world_readable(path: Path) -> None:
    """Warn when a secret-bearing user file is group- or world-readable."""
    try:
        mode = path.stat().st_mode
    except OSError:
        return
    if mode & 0o077:
        warnings.warn(
            f'{path} holds a secret and is group/world-readable; tighten it '
            f'with: chmod 600 {path}',
            stacklevel=2,
        )


# --- secret/path field markers (single source of truth on the models) ---


def _field_extra(settings_cls: type[BaseSettings], field: str) -> dict[str, Any]:
    """Field policy metadata, empty for a name the model does not have."""
    info = settings_cls.model_fields.get(field)
    if info is None:
        return {}
    extra = info.json_schema_extra
    return cast('dict[str, Any]', extra) if isinstance(extra, dict) else {}


def is_secret(settings_cls: type[BaseSettings], field: str) -> bool:
    """Whether ``field`` is a secret (redacted, kept out of project TOML)."""
    return bool(_field_extra(settings_cls, field).get('secret'))


def is_path(settings_cls: type[BaseSettings], field: str) -> bool:
    """Whether ``field`` is a filesystem path (anchored per scope)."""
    return bool(_field_extra(settings_cls, field).get('path'))


def secret_fields(settings_cls: type[BaseSettings]) -> frozenset[str]:
    """The secret field names of a provider model."""
    return frozenset(f for f in settings_cls.model_fields if is_secret(settings_cls, f))


# --- pydantic-settings TOML source: sits below env/.env, above defaults ---


class _TomlSource(PydanticBaseSettingsSource):
    """A settings source reading one provider section from a config file.

    Appended after the dotenv source so TOML values sit below the process
    environment and ``.env`` but above the model defaults (ADR 0031).
    """

    def __init__(
        self,
        settings_cls: type[BaseSettings],
        finder: Callable[[], DiscoveredConfig | None],
    ) -> None:
        super().__init__(settings_cls)
        self._finder = finder

    def get_field_value(
        self, field: FieldInfo, field_name: str
    ) -> tuple[object, str, bool]:
        # unused: __call__ returns the whole section in one pass
        return None, field_name, False

    def __call__(self) -> dict[str, Any]:
        disc = self._finder()
        if disc is None:
            return {}
        return _section_values(disc, self.settings_cls)


class _ConfigBase(BaseSettings):
    """Base for every storix settings model: env, ``.env``, then TOML.

    Subclasses set ``TOML_SECTION`` to the table they read (``None`` reads
    matching top-level keys, as ``StorixSettings`` does for ``provider``).
    """

    TOML_SECTION: ClassVar[str | None] = None

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            _TomlSource(settings_cls, find_project_config),
            _TomlSource(settings_cls, find_user_config),
        )


class StorixSettings(_ConfigBase):
    """Top-level selection: which backend ``get_storage()`` builds."""

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_prefix='STORIX_', env_file='.env', extra='ignore'
    )

    provider: StorageProvider = 'local'
    """Which backend ``get_storage()`` builds when none is named."""

    max_transfer_ranges: int = Field(default=DEFAULT_TRANSFER_RANGES, ge=1)
    """Ceiling on how many ranges of one file a bulk transfer may open.

    Range parallelism makes a single large file transfer at more than one
    connection's speed, at the cost of one request per range (ADR 0032).
    Set ``STORIX_MAX_TRANSFER_RANGES=1`` to keep every transfer on one
    stream per file, which is what a provider quota or a
    transaction-sensitive bill may prefer."""


class TransferConfig(_ConfigBase):
    """Transfer sizes every provider understands.

    Inherited by each provider's settings, so the same two knobs are
    spelled ``STORIX_LOCAL_READ_CHUNK_SIZE``, ``STORIX_S3_READ_CHUNK_SIZE``,
    and so on. Sizes are in bytes and must be positive. What they trade
    against each other (memory per in-flight transfer against requests per
    byte) is documented in the Tune transfers recipe.
    """

    read_chunk_size: ByteSize = Field(default=ByteSize(DEFAULT_READ_CHUNK_SIZE), gt=0)
    """Maximum chunk a read yields, and the engine's read request size.

    Accepts a plain byte count or a human-readable size: ``8MiB`` is
    8388608, ``8MB`` is 8000000, and the IEC and SI spellings mean what
    they say rather than being treated as synonyms."""

    write_chunk_size: ByteSize = Field(default=ByteSize(DEFAULT_WRITE_CHUNK_SIZE), gt=0)
    """Batch size a write accumulates before sending a request.

    Accepts a plain byte count or a human-readable size (``4MiB``)."""


class RemoteTransferConfig(TransferConfig):
    """Transfer sizes for providers that fetch over the network."""

    read_prefetch_size: ByteSize | None = Field(default=None, gt=0)
    """Size of a stream's opening read, which is the buffer a download holds
    before it yields anything. ``None`` means the read chunk size, so a
    stream costs one chunk; a larger value trades resident memory per
    in-flight transfer for fewer round trips on a lone stream. Accepts a
    plain byte count or a human-readable size (``32MiB``)."""


class LocalConfig(TransferConfig):
    """``STORIX_LOCAL_*`` settings for the real-disk backend."""

    TOML_SECTION: ClassVar[str | None] = 'local'
    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_prefix='STORIX_LOCAL_', env_file='.env', extra='ignore'
    )

    base: str = Field(default='~/.storix', json_schema_extra={'path': True})
    """Base directory anchoring the filesystem (created if missing)."""


class S3Config(RemoteTransferConfig):
    """``STORIX_S3_*`` settings for the Amazon S3 backend."""

    TOML_SECTION: ClassVar[str | None] = 's3'
    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_prefix='STORIX_S3_', env_file='.env', extra='ignore'
    )

    bucket: str | None = None
    """Bucket anchoring the session; required."""

    region: str | None = None
    """Bucket region; defaults to the standard AWS environment/config chain."""

    access_key_id: str | None = Field(default=None, json_schema_extra={'secret': True})
    """Static access key; omitted means the standard AWS credential chain."""

    secret_access_key: str | None = Field(
        default=None, json_schema_extra={'secret': True}
    )
    """Secret for ``access_key_id``."""

    endpoint: str | None = None
    """Custom endpoint URL for S3-compatible stores (MinIO, R2, ...)."""

    root: str = '/'
    """Key prefix anchoring the session's ``/`` inside the bucket."""


class GcsConfig(RemoteTransferConfig):
    """``STORIX_GCS_*`` settings for the Google Cloud Storage backend."""

    TOML_SECTION: ClassVar[str | None] = 'gcs'
    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_prefix='STORIX_GCS_', env_file='.env', extra='ignore'
    )

    bucket: str | None = None
    """Bucket anchoring the session; required."""

    credential: str | None = Field(default=None, json_schema_extra={'secret': True})
    """Service-account JSON as a string; omitted means Google's default chain."""

    credential_path: str | None = Field(default=None, json_schema_extra={'path': True})
    """Path to a service-account JSON file."""

    endpoint: str | None = None
    """Custom endpoint URL for GCS-compatible stores and emulators."""

    root: str = '/'
    """Key prefix anchoring the session's ``/`` inside the bucket."""


class AzureConfig(RemoteTransferConfig):
    """``STORIX_AZURE_*`` settings for both Azure backends.

    One schema serves both account kinds: container, account name, and
    credential are all it takes. The default ``kind='auto'`` detects
    whether the account has hierarchical namespaces (one
    account-properties request at build time) and picks the surface:
    the native Data Lake Gen2 backend (atomic renames, true appends)
    for HNS accounts, the blob-endpoint backend for flat ones.
    """

    TOML_SECTION: ClassVar[str | None] = 'azure'
    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_prefix='STORIX_AZURE_', env_file='.env', extra='ignore'
    )

    kind: Literal['auto', 'adls', 'blob'] = 'auto'
    """Which Azure surface to speak: detected from the account by
    default. Set ``'adls'`` or ``'blob'`` explicitly to skip the
    detection request - required when the credential cannot read
    account properties (container-scoped SAS, anonymous access)."""

    container: str | None = None
    """Container (filesystem) name; required."""

    account_name: str | None = None
    """Storage account name; required. The adls kind needs HNS enabled."""

    credential: str | None = Field(default=None, json_schema_extra={'secret': True})
    """SAS token or account key; required for adls, optional for blob
    (``None`` means anonymous access to a public container)."""

    endpoint: str | None = None
    """Custom blob endpoint URL (emulators, sovereign clouds); blob kind only."""

    read_chunk_size: ByteSize = Field(
        default=ByteSize(DEFAULT_AZURE_READ_CHUNK_SIZE), gt=0
    )
    """Default consumer and SDK range chunk size (4 MiB, the SDK's own
    native download chunk). Accepts ``4MiB`` as readily as 4194304."""

    write_chunk_size: ByteSize = Field(
        default=ByteSize(DEFAULT_AZURE_WRITE_CHUNK_SIZE), gt=0
    )
    """Default append-request batch size (4 MiB)."""

    read_prefetch_size: ByteSize | None = Field(
        default=ByteSize(DEFAULT_AZURE_READ_PREFETCH_SIZE), gt=0
    )
    """Initial SDK download request size (8 MiB)."""


PROVIDER_MODELS: Final[dict[str, type[_ConfigBase]]] = {
    'local': LocalConfig,
    's3': S3Config,
    'gcs': GcsConfig,
    'azure': AzureConfig,
}
"""Provider name -> its configuration model. ``memory`` takes no config and
is deliberately absent, so any ``[memory]`` table or memory coordinate flag
reads as unknown."""

_KNOWN_TOP_LEVEL: Final[frozenset[str]] = frozenset(
    {
        'cli',
        'alias',
        'aliases',
        'profile',
        'profiles',
        *PROVIDER_MODELS,
        *StorixSettings.model_fields,
    }
)
"""Legal top-level keys in a storix config document (or ``[tool.storix]``):
the provider sections, every field of ``StorixSettings`` (``provider``,
``max_transfer_ranges``, ...), the ``[cli]`` table, the ``profile``
selection and its ``[profiles]`` table, and the ``alias`` / ``aliases``
compatibility spellings. Derived from the model rather than
listed by hand, so a new top-level setting is legal in TOML the day it is
added instead of erroring as unknown."""


# --- profiles and environment overlays (ADR 0031 D8, D9) ---


_PROFILE_NAME: Final[re.Pattern[str]] = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]*')
"""Legal profile and environment names, per ADR 0031 D8."""

_PROFILE_PROVIDERS: Final[frozenset[str]] = frozenset(
    get_args(StorageProvider.__value__)
)
"""Providers a profile may name: every one the factory builds, not only the
ones with a settings model. ``memory`` takes no configuration, so a profile
naming it carries no provider section."""

_ENVIRONMENTS: Final[str] = 'environments'
"""Sub-table of a profile holding its stage overlays."""

_RESERVED_PROFILE_KEYS: Final[frozenset[str]] = frozenset(
    {'provider', 'default_environment', _ENVIRONMENTS}
)
"""Profile keys that are the profile's own rather than a provider setting."""


@dataclass(frozen=True)
class ResolvedProfile:
    """A profile selection resolved into one provider and its settings."""

    name: str
    """The selected profile."""

    provider: str
    """The provider the profile connects to; a profile always names one."""

    values: dict[str, Any]
    """Provider settings, overlay applied, ready as ``get_storage`` keywords."""

    source: Path
    """The file the profile was read from, for diagnostics."""

    environment: str | None = None
    """The applied stage overlay, when one was selected."""


def _validate_profiles(path: Path, data: dict[str, Any]) -> None:
    """Check the shape of a ``[profiles]`` table before anything reads it.

    A profile names one provider and carries that provider's settings
    directly, so there is no provider-named sub-table to repeat and no way
    to leave settings for a second provider lying around unread.

    Raises:
        ConfigurationError: If ``profiles`` is not a table, a profile is not
            a table, a name is illegal, a profile names no provider or an
            unknown one, a setting is not one of that provider's, an overlay
            tries to switch the provider, or a default environment does not
            exist.
    """
    node = data.get('profiles')
    if node is None:
        return
    if not isinstance(node, dict):
        msg = f'{path}: [profiles] must be a table of named profiles'
        raise ConfigurationError(msg)

    for name, profile in cast('dict[str, Any]', node).items():
        if not _PROFILE_NAME.fullmatch(name):
            msg = (
                f'{path}: profile name {name!r} is not allowed; use letters, '
                'digits, dot, dash, or underscore, starting alphanumeric'
            )
            raise ConfigurationError(msg)
        if not isinstance(profile, dict):
            msg = f'{path}: profile {name!r} must be a table'
            raise ConfigurationError(msg)
        table = cast('dict[str, Any]', profile)
        provider = table.get('provider')
        if not isinstance(provider, str):
            msg = f'{path}: profile {name!r} must name a provider'
            raise ConfigurationError(msg)
        if provider not in _PROFILE_PROVIDERS:
            known = ', '.join(sorted(_PROFILE_PROVIDERS))
            msg = (
                f'{path}: profile {name!r} names unknown provider '
                f'{provider!r}; known: {known}'
            )
            raise ConfigurationError(msg)
        _validate_profile_keys(path, name, provider, table, _RESERVED_PROFILE_KEYS)
        _validate_environments(path, name, provider, table)
        _validate_default_environment(path, name, table)


def _validate_profile_keys(
    path: Path,
    name: str,
    provider: str,
    table: dict[str, Any],
    reserved: frozenset[str],
) -> None:
    """Reject a key that is neither reserved nor a setting of the provider.

    This is what stops a settings block for another provider, or a typo,
    from sitting in a profile unread: a profile belongs to one provider, so
    anything else in it is a mistake worth naming.

    Raises:
        ConfigurationError: On a key the selected provider does not have.
    """
    model = PROVIDER_MODELS.get(provider)
    fields: set[str] = set(model.model_fields) if model is not None else set()
    for key in table:
        if key in reserved or key in fields:
            continue
        known = ', '.join(sorted(fields)) if fields else 'none'
        msg = (
            f'{path}: profile {name!r} is a {provider!r} profile and has no '
            f'setting {key!r} (known: {known})'
        )
        raise ConfigurationError(msg)


def _validate_environments(
    path: Path, name: str, provider: str, profile: dict[str, Any]
) -> None:
    """Check one profile's overlays.

    Raises:
        ConfigurationError: If the overlays are not a table, an environment
            name is illegal, an overlay declares its own provider, or an
            overlay sets something the provider does not have.
    """
    node = profile.get(_ENVIRONMENTS)
    if node is None:
        return
    if not isinstance(node, dict):
        msg = f'{path}: profile {name!r}: [{_ENVIRONMENTS}] must be a table'
        raise ConfigurationError(msg)
    for env_name, overlay in cast('dict[str, Any]', node).items():
        if not _PROFILE_NAME.fullmatch(env_name):
            msg = (
                f'{path}: profile {name!r}: environment name {env_name!r} '
                'is not allowed'
            )
            raise ConfigurationError(msg)
        if not isinstance(overlay, dict):
            msg = f'{path}: profile {name!r}: environment {env_name!r} must be a table'
            raise ConfigurationError(msg)
        stage = cast('dict[str, Any]', overlay)
        if 'provider' in stage:
            msg = (
                f'{path}: profile {name!r}: environment {env_name!r} cannot change '
                'the provider; stages of one profile share a backend'
            )
            raise ConfigurationError(msg)
        _validate_profile_keys(path, f'{name}.{env_name}', provider, stage, frozenset())


def _validate_default_environment(
    path: Path, name: str, profile: dict[str, Any]
) -> None:
    """Check a profile's ``default_environment`` against its own stages.

    Raises:
        ConfigurationError: If the default is not a string or names a stage
            the profile does not define.
    """
    default = profile.get('default_environment')
    if default is None:
        return
    stages = profile.get(_ENVIRONMENTS)
    available: set[str] = (
        set(cast('dict[str, Any]', stages)) if isinstance(stages, dict) else set()
    )
    if not isinstance(default, str) or default not in available:
        known = ', '.join(sorted(available)) or 'none defined'
        msg = (
            f'{path}: profile {name!r}: default_environment {default!r} is not '
            f'one of its environments (available: {known})'
        )
        raise ConfigurationError(msg)


def available_profiles() -> dict[str, DiscoveredConfig]:
    """Every profile that can be selected, mapped to the file defining it.

    A project profile shadows a user profile of the same name whole: the
    effective profile is always readable from one file, with no cross-scope
    field merging to reason about (ADR 0031 D8).
    """
    found: dict[str, DiscoveredConfig] = {}
    for disc in (find_user_config(), find_project_config()):
        if disc is None:
            continue
        node = disc.data.get('profiles')
        if isinstance(node, dict):
            for name in cast('dict[str, Any]', node):
                found[name] = disc
    return found


def configured_profile() -> str | None:
    """The profile a config file pins with a top-level ``profile`` key."""
    for disc in (find_project_config(), find_user_config()):
        if disc is None:
            continue
        name = disc.data.get('profile')
        if isinstance(name, str):
            return name
    return None


def resolve_profile(name: str, environment: str | None = None) -> ResolvedProfile:
    """Resolve a profile (and optional overlay) into provider settings.

    A profile carries its provider's settings directly, and a stage overlay
    carries the same fields; the two are merged and then run through the
    extraction every config file gets, so unknown keys, the secret policy,
    and path anchoring behave identically inside a profile.

    Args:
        name: Profile to select.
        environment: Stage overlay to apply. ``None`` uses the profile's
            ``default_environment`` when it names one, else no overlay.

    Returns:
        The provider and its settings, ready as ``get_storage`` keywords.

    Raises:
        ConfigurationError: If the profile or environment does not exist, or
            the profile's settings fail the config-file policy.
    """
    profiles = available_profiles()
    disc = profiles.get(name)
    if disc is None:
        known = (
            ', '.join(f'{n} ({p.path})' for n, p in sorted(profiles.items()))
            or 'none defined'
        )
        msg = f'unknown profile {name!r}; available: {known}'
        raise ConfigurationError(msg)

    table = cast('dict[str, Any]', disc.data['profiles'])
    profile = cast('dict[str, Any]', table[name])
    provider = cast('str', profile['provider'])
    stage = environment or cast('str | None', profile.get('default_environment'))

    settings = {
        key: value
        for key, value in profile.items()
        if key not in _RESERVED_PROFILE_KEYS
    }
    if stage is not None:
        overlays = cast('dict[str, Any]', profile.get(_ENVIRONMENTS, {}))
        overlay = overlays.get(stage)
        if overlay is None:
            known = ', '.join(sorted(overlays)) or 'none defined'
            msg = (
                f'profile {name!r} has no environment {stage!r} '
                f'({disc.path}); available: {known}'
            )
            raise ConfigurationError(msg)
        settings |= cast('dict[str, Any]', overlay)

    model = PROVIDER_MODELS.get(provider)
    if model is None:
        # a provider with no settings model (memory) configures nothing, and
        # the validator has already refused any setting written under it
        return ResolvedProfile(
            name=name,
            provider=provider,
            values={},
            source=disc.path,
            environment=stage,
        )

    # reuse the file policy wholesale: unknown keys, env: secrets, anchoring
    section = str(getattr(model, 'TOML_SECTION', provider))
    view = DiscoveredConfig(disc.path, {section: settings}, disc.scope)
    return ResolvedProfile(
        name=name,
        provider=provider,
        values=_section_values(view, model),
        source=disc.path,
        environment=stage,
    )


# --- provenance (which source supplied each effective field) ---


def _dotenv_fields(settings_cls: type[BaseSettings]) -> frozenset[str]:
    """Fields the project ``.env`` provides for this model's prefix."""
    env_file = Path('.env')
    if not env_file.is_file():
        return frozenset()
    from dotenv import dotenv_values

    prefix = settings_cls.model_config.get('env_prefix', '')
    present = dotenv_values(env_file)
    return frozenset(
        f for f in settings_cls.model_fields if f'{prefix}{f.upper()}' in present
    )


def _env_fields(settings_cls: type[BaseSettings]) -> frozenset[str]:
    """Fields the process environment provides for this model's prefix."""
    prefix = settings_cls.model_config.get('env_prefix', '')
    return frozenset(
        f for f in settings_cls.model_fields if f'{prefix}{f.upper()}' in os.environ
    )


def config_provenance(
    provider: str,
    /,
    *,
    profile: str | None = None,
    environment: str | None = None,
    **overrides: Any,
) -> dict[str, ConfigSource]:
    """Report which source supplies each effective field of ``provider``.

    Replays the same precedence ``get_storage`` resolves (overrides beat a
    selected profile and its stage, which beat the environment, ``.env``,
    project TOML, the user file, and defaults), so diagnostics can explain
    a value's origin. An unknown provider yields an empty map.

    Args:
        provider: The provider whose configuration to trace.
        profile: A selected profile, whose values sit above the environment.
        environment: The stage overlay applied to that profile.
        overrides: The explicit keyword overrides passed to ``get_storage``.

    Raises:
        ConfigurationError: If a discovered file is malformed or invalid, or
            the named profile does not exist (the same failures
            ``get_storage`` would raise).
    """
    settings_cls = PROVIDER_MODELS.get(provider)
    if settings_cls is None:
        return {}
    project = find_project_config()
    user = find_user_config()
    empty: frozenset[str] = frozenset()
    profile_fields = (
        frozenset(resolve_profile(profile, environment).values)
        if profile is not None
        else empty
    )
    project_fields = (
        frozenset(_section_values(project, settings_cls)) if project else empty
    )
    user_fields = frozenset(_section_values(user, settings_cls)) if user else empty
    layers: list[tuple[ConfigSource, frozenset[str]]] = [
        ('override', frozenset(overrides)),
        ('profile', profile_fields),
        ('env', _env_fields(settings_cls)),
        ('dotenv', _dotenv_fields(settings_cls)),
        ('project', project_fields),
        ('user', user_fields),
    ]
    result: dict[str, ConfigSource] = {}
    for field in settings_cls.model_fields:
        source: ConfigSource = 'default'
        for src, present in layers:
            if field in present:
                source = src
                break
        result[field] = source
    return result


# --- installation remedy (context-aware, D7); shared by the CLI guards ---


# --- writing: scope resolution and atomic, validated edits (ADR 0031 D10) ---


type Scope = Literal['user', 'project']
"""Where a write lands: the XDG user file, or the project's own."""


def user_config_path() -> Path:
    """This platform's user config file, whether or not it exists yet.

    ``XDG_CONFIG_HOME`` wins everywhere when it is set, because a user who
    exports it means it. Otherwise Windows uses ``%APPDATA%``, where a
    Windows user expects per-user application data, and every other platform
    uses ``~/.config``. Anchoring a Windows install under ``~/.config``
    would work and look foreign, a poor trade for a tool that now installs
    itself with PowerShell too.
    """
    configured = os.environ.get('XDG_CONFIG_HOME')
    if configured:
        base = Path(configured)
    elif sys.platform == 'win32':
        appdata = os.environ.get('APPDATA')
        base = Path(appdata) if appdata else Path.home() / 'AppData' / 'Roaming'
    else:
        base = Path.home() / '.config'
    return base / 'storix' / 'config.toml'


def project_config_path() -> tuple[Path, bool]:
    """Where a project write lands, and whether that file exists yet.

    The nearest ``storix.toml`` walking upward, else a ``pyproject.toml``
    that already carries ``[tool.storix]``, else ``./storix.toml`` in the
    current directory - which is reported as not existing so the caller can
    say it is creating one.
    """
    discovered = find_project_config()
    if discovered is not None:
        return discovered.path, True
    return Path.cwd() / 'storix.toml', False


def scope_path(scope: Scope) -> tuple[Path, bool]:
    """The file a write to ``scope`` targets, and whether it exists."""
    if scope == 'user':
        path = user_config_path()
        return path, path.is_file()
    return project_config_path()


def split_key(key: str) -> tuple[str, ...]:
    """Split a dotted config key into its path.

    Raises:
        ConfigurationError: If the key is empty or has an empty segment.
    """
    parts = tuple(key.split('.'))
    if not key or any(not part for part in parts):
        msg = f'{key!r} is not a config key; write section.field, e.g. s3.bucket'
        raise ConfigurationError(msg)
    return parts


def _document_root(path: Path) -> tuple[Any, tuple[str, ...]]:
    """Parse ``path`` for editing, plus the prefix a key sits under.

    ``pyproject.toml`` keeps storix config under ``[tool.storix]``; a
    standalone file has no prefix.
    """
    import tomlkit

    text = path.read_text(encoding='utf-8') if path.is_file() else ''
    document = tomlkit.parse(text)
    prefix = ('tool', 'storix') if path.name == 'pyproject.toml' else ()
    return document, prefix


def _validate_written(path: Path, document: Any) -> None:
    """Reject an edit that would leave the file invalid, before writing it.

    Raises:
        ConfigurationError: If the resulting document fails the same checks
            a discovered file gets.
    """
    import tomllib

    data = tomllib.loads(document.as_string())
    if path.name == 'pyproject.toml':
        data = _table(data, 'tool', 'storix') or {}
    _validate_document(path, data)
    scope: Scope = 'user' if path == user_config_path() else 'project'
    disc = DiscoveredConfig(path, data, scope)
    for model in PROVIDER_MODELS.values():
        _section_values(disc, model)


def _write_atomically(path: Path, text: str, scope: Scope) -> None:
    """Replace ``path`` in one step, keeping its mode (user files are 600)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = path.stat().st_mode & 0o777 if path.is_file() else None
    with tempfile.NamedTemporaryFile(
        'w', encoding='utf-8', dir=path.parent, delete=False
    ) as handle:
        handle.write(text)
        temporary = Path(handle.name)
    temporary.chmod(mode if mode is not None else (0o600 if scope == 'user' else 0o644))
    temporary.replace(path)


def set_setting(key: str, value: str, scope: Scope = 'project') -> Path:
    """Set one config key, validated, atomically, comments preserved.

    Args:
        key: Dotted key, e.g. ``s3.bucket`` or ``cli.icons``.
        value: The value as typed; parsed type-aware by TOML rules.
        scope: Which file to write.

    Returns:
        The file that was written.

    Raises:
        ConfigurationError: If the key is malformed, names a secret in a
            project file, or would leave the file invalid.
    """
    import tomlkit

    parts = split_key(key)
    path, _ = scope_path(scope)
    _refuse_secret_write(path, parts, scope)
    document, prefix = _document_root(path)

    node: Any = document
    for part in (*prefix, *parts[:-1]):
        if part not in node:
            node[part] = tomlkit.table()
        node = node[part]
    node[parts[-1]] = _parse_value(value)

    _validate_written(path, document)
    _write_atomically(path, tomlkit.dumps(document), scope)
    return path


def unset_setting(key: str, scope: Scope = 'project') -> Path:
    """Remove one config key from ``scope``'s file.

    Returns:
        The file that was written.

    Raises:
        ConfigurationError: If the key is malformed or not present.
    """
    import tomlkit

    parts = split_key(key)
    path, exists = scope_path(scope)
    if not exists:
        msg = f'{path}: no config file to remove {key!r} from'
        raise ConfigurationError(msg)
    document, prefix = _document_root(path)

    node: Any = document
    for part in (*prefix, *parts[:-1]):
        if part not in node:
            msg = f'{path}: {key!r} is not set'
            raise ConfigurationError(msg)
        node = node[part]
    if parts[-1] not in node:
        msg = f'{path}: {key!r} is not set'
        raise ConfigurationError(msg)
    del node[parts[-1]]

    _validate_written(path, document)
    _write_atomically(path, tomlkit.dumps(document), scope)
    return path


def _parse_value(value: str) -> Any:
    """Parse a command-line value the way TOML would read it.

    A bare word stays a string, so ``sx config set s3.bucket media`` does
    not need quoting, while ``true``, ``8``, and ``"8MiB"`` mean what they
    say.
    """
    import tomllib

    try:
        return tomllib.loads(f'value = {value}')['value']
    except tomllib.TOMLDecodeError:
        return value


def _refuse_secret_write(path: Path, parts: tuple[str, ...], scope: Scope) -> None:
    """Apply the secret policy to a write.

    Raises:
        ConfigurationError: On a literal secret written to a project file.
    """
    section_and_field = 2
    if len(parts) < section_and_field:
        return
    model = PROVIDER_MODELS.get(parts[0])
    if model is None or not is_secret(model, parts[-1]):
        return
    if scope == 'project':
        msg = (
            f'{path}: {".".join(parts)} is a secret and project files are '
            f'committed; set STORIX_{parts[0].upper()}_{parts[-1].upper()}, or '
            f'write env:VAR here, or use --scope user'
        )
        raise ConfigurationError(msg)


def _is_uv_tool() -> bool:
    """Whether ``sx`` runs from a ``uv tool install`` environment.

    uv drops a ``uv-receipt.toml`` in the tool's environment directory
    (verified against a real ``uv tool`` layout).
    """
    prefix = Path(sys.prefix)
    return (prefix / 'uv-receipt.toml').is_file() or (
        prefix.parent / 'uv-receipt.toml'
    ).is_file()


def installation_kind() -> str:
    """How this storix was installed, as a word fit for a message.

    ``uv-tool`` is the only kind ``sx update`` will drive; the others are
    reported so the user gets the right manual command instead of a
    surprise write into someone else's environment.
    """
    if _is_uv_tool():
        return 'uv-tool'
    if (Path(sys.prefix) / 'pyvenv.cfg').is_file():
        return 'virtualenv'
    return 'system'


def upgrade_command() -> list[str] | None:
    """The exact command that upgrades this installation, if one is known.

    A uv tool install is upgraded through uv, whose receipt already holds
    the extras that were requested, so storix keeps no installation state
    of its own. Anything else gets the pip form, which the caller prints
    rather than runs.
    """
    if _is_uv_tool():
        return ['uv', 'tool', 'upgrade', 'storix']
    return [sys.executable, '-m', 'pip', 'install', '--upgrade', 'storix']


def install_hint(extra: str) -> str:
    """The install command to add a missing optional ``extra``.

    Context-aware (D7): a ``uv tool`` install gets the ``uv tool install``
    form (which keeps ``sx`` on PATH); everything else gets the ``pip`` /
    ``uv add`` project forms.
    """
    if _is_uv_tool():
        bundle = 'cli' if extra == 'cli' else f'cli,{extra}'
        return f'uv tool install "storix[{bundle}]"'
    return f'pip install "storix[{extra}]" (or uv add "storix[{extra}]")'
