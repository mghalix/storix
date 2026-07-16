"""Settings-driven construction of Storix sessions."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal, TypedDict, Unpack, overload

from storix.config import (
    AzureConfig,
    GcsConfig,
    LocalConfig,
    S3Config,
    StorixSettings,
)
from storix.errors import ConfigurationError

from .core import Storix


if TYPE_CHECKING:
    from collections.abc import Callable

    from .backends import StorageBackend


class _LocalOverrides(TypedDict, total=False):
    base: str


class _AzureOverrides(TypedDict, total=False):
    container: str
    account_name: str
    credential: str
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


class _GcsOverrides(TypedDict, total=False):
    bucket: str
    credential: str
    credential_path: str
    endpoint: str
    root: str


def _build_local(**overrides: Any) -> StorageBackend:
    from .backends.local import LocalBackend

    cfg = LocalConfig(**overrides)
    return LocalBackend(cfg.base)


def _build_memory(**overrides: Any) -> StorageBackend:
    if overrides:
        fields = ', '.join(sorted(overrides))
        msg = f'memory backend accepts no configuration overrides: {fields}'
        raise ConfigurationError(msg)

    from .backends.memory import MemoryBackend

    return MemoryBackend()


def _build_azure(**overrides: Any) -> StorageBackend:
    # lazy: the azure SDK is an optional dependency
    from .backends.azure import AzureBackend

    cfg = AzureConfig(**overrides)
    missing = [
        field
        for field in ('container', 'account_name', 'credential')
        if getattr(cfg, field) is None
    ]
    if missing:
        msg = (
            f'azure backend is missing configuration: {", ".join(missing)} - '
            f'set STORIX_AZURE_{missing[0].upper()} (etc.) or pass them to '
            f'get_storage()'
        )
        raise ConfigurationError(msg)
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


@overload
def get_storage(
    provider: Literal['local'], /, **overrides: Unpack[_LocalOverrides]
) -> Storix: ...
@overload
def get_storage(provider: Literal['memory'], /) -> Storix: ...
@overload
def get_storage(
    provider: Literal['azure'], /, **overrides: Unpack[_AzureOverrides]
) -> Storix: ...
@overload
def get_storage(
    provider: Literal['s3'], /, **overrides: Unpack[_S3Overrides]
) -> Storix: ...
@overload
def get_storage(
    provider: Literal['gcs'], /, **overrides: Unpack[_GcsOverrides]
) -> Storix: ...
@overload
def get_storage(provider: str, /, **overrides: Any) -> Storix: ...  # plugins
@overload
def get_storage(provider: None = None, /) -> Storix: ...  # env-driven, no kwargs


def get_storage(provider: str | None = None, /, **overrides: Any) -> Storix:
    """Build a Storix session from settings.

    ``provider`` overrides ``STORIX_PROVIDER`` (default: local at
    ``~/.storix``); keyword overrides beat the corresponding
    ``STORIX_<PROVIDER>_*`` environment values. Passing a literal
    provider name gets fully typed keyword completion.

    The provider is positional-only: ``get_storage(provider='azure')``
    would otherwise be silently swallowed as a config override, so it is
    rejected both statically (no overload accepts it) and at runtime.
    """
    if 'provider' in overrides:
        msg = "pass the provider positionally: get_storage('azure', ...)"
        raise ConfigurationError(msg)
    name = provider or StorixSettings().provider
    builder = _BUILDERS.get(name)
    if builder is None:
        msg = f'unknown storage provider {name!r}; available: {sorted(_BUILDERS)}'
        raise ConfigurationError(msg)
    return Storix(builder(**overrides))
