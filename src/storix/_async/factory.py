"""Settings-driven construction of Storix sessions."""

from __future__ import annotations

from typing import (
    TYPE_CHECKING,
    Any,
    Final,
    Literal,
    TypedDict,
    Unpack,
    overload,
)

from storix.config import (
    AzureConfig,
    GcsConfig,
    LocalConfig,
    S3Config,
    StorixSettings,
    require_extra,
    resolve_profile,
)
from storix.errors import ConfigurationError

from .core import Storix


if TYPE_CHECKING:
    from collections.abc import Callable

    from .backends import StorageBackend


class _LocalOverrides(TypedDict, total=False):
    base: str
    read_chunk_size: int
    write_chunk_size: int


class _AzureOverrides(TypedDict, total=False):
    kind: Literal['auto', 'adls', 'blob']
    container: str
    account_name: str
    credential: str
    endpoint: str
    read_chunk_size: int
    write_chunk_size: int
    read_prefetch_size: int


class _S3Overrides(TypedDict, total=False):
    bucket: str
    region: str
    access_key_id: str
    secret_access_key: str
    endpoint: str
    root: str
    read_chunk_size: int
    write_chunk_size: int
    read_prefetch_size: int


class _GcsOverrides(TypedDict, total=False):
    bucket: str
    credential: str
    credential_path: str
    endpoint: str
    root: str
    read_chunk_size: int
    write_chunk_size: int
    read_prefetch_size: int


def _build_local(**overrides: Any) -> StorageBackend:
    from .backends.local import LocalBackend

    cfg = LocalConfig(**overrides)
    return LocalBackend(
        cfg.base,
        read_chunk_size=cfg.read_chunk_size,
        write_chunk_size=cfg.write_chunk_size,
    )


def _build_memory(**overrides: Any) -> StorageBackend:
    if overrides:
        fields = ', '.join(sorted(overrides))
        msg = f'memory backend accepts no configuration overrides: {fields}'
        raise ConfigurationError(msg)

    from .backends.memory import MemoryBackend

    return MemoryBackend()


_AZURE_KIND_CACHE: Final[
    dict[tuple[str | None, str | None], Literal['adls', 'blob']]
] = {}
"""Detected Azure account kinds by (account_name, endpoint).

Detection results only, never explicit ``kind`` assertions: an
account's HNS-ness cannot change within a process, so a measurement is
safe to reuse, while a user's (possibly wrong) claim is not one.
"""


def _detect_azure_kind(cfg: AzureConfig) -> Literal['adls', 'blob']:
    """Decide which Azure surface to build with one account-properties call.

    Deliberately uses the synchronous blob client in both flavors: the
    factory is a plain function, and this is a single request per
    account per process (the result is cached). Passing an explicit
    ``kind`` skips it entirely.

    Raises:
        ConfigurationError: If detection is impossible - the azure SDK
            extra is missing, the account is unreachable, or the
            credential may not read account properties (container-scoped
            SAS, anonymous access).
    """
    cache_key = (cfg.account_name, cfg.endpoint)
    cached = _AZURE_KIND_CACHE.get(cache_key)
    if cached is not None:
        return cached

    try:
        from azure.core.exceptions import AzureError
        from azure.storage.blob import BlobServiceClient
    except ModuleNotFoundError:
        msg = (
            'azure kind auto-detection needs the azure SDK - install '
            "storix[azure], or set kind='adls' / kind='blob' explicitly"
        )
        raise ConfigurationError(msg) from None

    account_url = cfg.endpoint or f'https://{cfg.account_name}.blob.core.windows.net'
    try:
        with BlobServiceClient(account_url, credential=cfg.credential) as client:
            info = client.get_account_information()
    except AzureError as exc:
        msg = (
            'azure kind auto-detection could not read the account properties '
            f'({type(exc).__name__}); if the credential is scoped below the '
            "account (container SAS) or anonymous, set kind='adls' or "
            "kind='blob' explicitly"
        )
        raise ConfigurationError(msg) from exc
    kind: Literal['adls', 'blob'] = 'adls' if info.get('is_hns_enabled') else 'blob'
    _AZURE_KIND_CACHE[cache_key] = kind
    return kind


def _build_azure(**overrides: Any) -> StorageBackend:
    cfg = AzureConfig(**overrides)
    required: tuple[str, ...] = ('container', 'account_name', 'credential')
    if cfg.kind == 'blob':  # blob allows anonymous access to public containers
        required = ('container', 'account_name')
    missing = [field for field in required if getattr(cfg, field) is None]
    if missing:
        msg = (
            f'azure backend is missing configuration: {", ".join(missing)} - '
            f'set STORIX_AZURE_{missing[0].upper()} (etc.) or pass them to '
            f'get_storage()'
        )
        raise ConfigurationError(msg)

    kind = cfg.kind
    if kind == 'auto':
        kind = _detect_azure_kind(cfg)

    if kind == 'blob':
        # lazy: the blob engine is an optional dependency (storix[azblob])
        from .backends.azblob import AzureBlobBackend

        assert cfg.container and cfg.account_name  # narrowed above
        return AzureBlobBackend(
            cfg.container,
            account_name=cfg.account_name,
            credential=cfg.credential,
            endpoint=cfg.endpoint,
        )

    if cfg.endpoint is not None:
        msg = 'the endpoint override applies to the blob kind only'
        raise ConfigurationError(msg)

    # lazy: the azure SDK is an optional dependency (storix[azure])
    from .backends.azure import AzureBackend

    assert cfg.container and cfg.account_name and cfg.credential  # narrowed above
    return AzureBackend(
        cfg.container,
        account_name=cfg.account_name,
        credential=cfg.credential,
        read_chunk_size=cfg.read_chunk_size,
        write_chunk_size=cfg.write_chunk_size,
        read_prefetch_size=cfg.read_prefetch_size,
    )


def _build_s3(**overrides: Any) -> StorageBackend:
    # lazy: the backend's engine is an optional dependency (storix[s3])
    from .backends.s3 import S3Backend

    cfg = S3Config(**overrides)
    if cfg.bucket is None:
        msg = (
            's3 backend is missing configuration: bucket - set '
            'STORIX_S3_BUCKET or pass it to get_storage()'
        )
        raise ConfigurationError(msg)
    return S3Backend(
        cfg.bucket,
        read_chunk_size=cfg.read_chunk_size,
        write_chunk_size=cfg.write_chunk_size,
        read_prefetch_size=cfg.read_prefetch_size,
        region=cfg.region,
        access_key_id=cfg.access_key_id,
        secret_access_key=cfg.secret_access_key,
        endpoint=cfg.endpoint,
        root=cfg.root,
    )


def _build_gcs(**overrides: Any) -> StorageBackend:
    # lazy: the backend's engine is an optional dependency (storix[gcs])
    from .backends.gcs import GcsBackend

    cfg = GcsConfig(**overrides)
    if cfg.bucket is None:
        msg = (
            'gcs backend is missing configuration: bucket - set '
            'STORIX_GCS_BUCKET or pass it to get_storage()'
        )
        raise ConfigurationError(msg)
    return GcsBackend(
        cfg.bucket,
        read_chunk_size=cfg.read_chunk_size,
        write_chunk_size=cfg.write_chunk_size,
        read_prefetch_size=cfg.read_prefetch_size,
        credential=cfg.credential,
        credential_path=cfg.credential_path,
        endpoint=cfg.endpoint,
        root=cfg.root,
    )


# keyed by str, not the built-in Literal: third-party providers register
# arbitrary names (the whole point of register_backend)
_BUILDERS: dict[str, Callable[..., StorageBackend]] = {
    'local': _build_local,
    'memory': _build_memory,
    'azure': _build_azure,
    's3': _build_s3,
    'gcs': _build_gcs,
}


def register_backend(name: str, builder: Callable[..., StorageBackend]) -> None:
    """Register a backend builder under a provider name.

    The extension point for third-party backends: the builder receives
    ``get_storage``'s keyword overrides and returns a constructed
    ``StorageBackend``. The built-in providers are registered the same
    way.
    """
    _BUILDERS[name] = builder


def available_providers() -> tuple[str, ...]:
    """Provider names ``get_storage`` accepts - built-ins plus plugins.

    Runtime companion to the ``StorageProvider`` literal (which types the
    built-ins for IDE completion): use this to enumerate everything
    registered, including third-party backends.
    """
    return tuple(_BUILDERS)


# every overload carries the profile selection: it is not a provider setting,
# so it stays a named keyword rather than a key in the override TypedDicts,
# and it is spelled out here so editors offer it (ADR 0031 D8)
@overload
def get_storage(
    provider: Literal['local'],
    /,
    *,
    profile: str | None = None,
    environment: str | None = None,
    **overrides: Unpack[_LocalOverrides],
) -> Storix: ...
@overload
def get_storage(
    provider: Literal['memory'],
    /,
    *,
    profile: str | None = None,
    environment: str | None = None,
) -> Storix: ...
@overload
def get_storage(
    provider: Literal['azure'],
    /,
    *,
    profile: str | None = None,
    environment: str | None = None,
    **overrides: Unpack[_AzureOverrides],
) -> Storix: ...
@overload
def get_storage(
    provider: Literal['s3'],
    /,
    *,
    profile: str | None = None,
    environment: str | None = None,
    **overrides: Unpack[_S3Overrides],
) -> Storix: ...
@overload
def get_storage(
    provider: Literal['gcs'],
    /,
    *,
    profile: str | None = None,
    environment: str | None = None,
    **overrides: Unpack[_GcsOverrides],
) -> Storix: ...
@overload
def get_storage(  # plugins
    provider: str,
    /,
    *,
    profile: str | None = None,
    environment: str | None = None,
    **overrides: Any,
) -> Storix: ...
@overload
def get_storage(  # env-driven or profile-driven: the provider is resolved
    provider: None = None,
    /,
    *,
    profile: str | None = None,
    environment: str | None = None,
    **overrides: Any,
) -> Storix: ...


def get_storage(
    provider: str | None = None,
    /,
    *,
    profile: str | None = None,
    environment: str | None = None,
    **overrides: Any,
) -> Storix:
    """Build a Storix session from settings.

    ``provider`` overrides ``STORIX_PROVIDER`` (default: local at
    ``~/.storix``); keyword overrides beat the corresponding
    ``STORIX_<PROVIDER>_*`` environment values. Passing a literal
    provider name gets fully typed keyword completion.

    ``profile=`` selects a named profile from a config file, and
    ``environment=`` a stage overlay within it (ADR 0031). A profile
    already names its provider, so the usual call is
    ``get_storage(profile='media')`` with no provider at all; naming a
    different one is a contradiction and raises. Naming the *same* one is
    allowed and buys typed completion for that provider's override keys,
    which is the only reason to write it. Explicit keywords still win over
    the profile's values.

    A profile applies here only when this call asks for one. Neither
    ``STORIX_PROFILE`` nor a ``profile`` key pinned in a config file
    reaches the library: both are a person's convenience at a prompt, and
    letting either steer ``get_storage`` means a personal file can point
    an application's session at another account, and that
    ``get_storage('s3')`` beside ``get_storage('azure')`` - the shape
    every migration and every composite filesystem takes - stops working
    on whichever machine has a pin. ``sx`` honors both, because there the
    convenience is the point.

    The provider is positional-only: ``get_storage(provider='azure')``
    would otherwise be silently swallowed as a config override, so it is
    rejected both statically (no overload accepts it) and at runtime.
    """
    if 'provider' in overrides:
        msg = "pass the provider positionally: get_storage('azure', ...)"
        raise ConfigurationError(msg)
    if environment is not None and profile is None:
        msg = 'environment= selects a stage of a profile; name one with profile='
        raise ConfigurationError(msg)

    if profile is not None:
        resolved = resolve_profile(profile, environment)
        if provider is not None and provider != resolved.provider:
            msg = (
                f'profile {resolved.name!r} connects to {resolved.provider!r}, '
                f'not {provider!r} ({resolved.source}); a profile names its own '
                'provider'
            )
            raise ConfigurationError(msg)
        # explicit keywords still win: the profile is a source, not a lock
        overrides = {**resolved.values, **overrides}
        provider = resolved.provider

    name = provider or StorixSettings().provider
    builder = _BUILDERS.get(name)
    if builder is None:
        msg = f'unknown storage provider {name!r}; available: {sorted(_BUILDERS)}'
        raise ConfigurationError(msg)
    # the one place every builder routes through, so a missing extra outranks
    # a missing credential without depending on the order of statements inside
    # each builder (D7); third-party providers are not in the table and pass
    require_extra(name)
    return Storix(builder(**overrides))
