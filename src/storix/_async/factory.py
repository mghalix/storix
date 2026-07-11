"""Settings-driven construction of Storix sessions."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal, TypedDict, Unpack, overload

from storix.config import AzureConfig, LocalConfig, StorixSettings
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


def _build_local(**overrides: Any) -> StorageBackend:
    from .backends.local import LocalBackend

    cfg = LocalConfig(**overrides)
    return LocalBackend(cfg.base)


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
    )


# keyed by str, not the built-in Literal: third-party providers register
# arbitrary names (the whole point of register_backend)
_BUILDERS: dict[str, Callable[..., StorageBackend]] = {
    'local': _build_local,
    'azure': _build_azure,
}


def register_backend(name: str, builder: Callable[..., StorageBackend]) -> None:
    """Register a backend builder under a provider name.

    The extension point for third-party backends: the builder receives
    ``get_storage``'s keyword overrides and returns a constructed
    ``StorageBackend``. The built-in providers are registered the same
    way.
    """
    _BUILDERS[name] = builder


@overload
def get_storage(
    provider: Literal['local'], /, **overrides: Unpack[_LocalOverrides]
) -> Storix: ...
@overload
def get_storage(
    provider: Literal['azure'], /, **overrides: Unpack[_AzureOverrides]
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
