"""Settings-driven construction of Storix sessions."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from storix.config import AzureConfig, LocalConfig, StorixSettings
from storix.errors import ConfigurationError

from .core import Storix


if TYPE_CHECKING:
    from storix.types import AvailableProviders

    from .backends import StorageBackend


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


_BUILDERS = {
    'local': _build_local,
    'azure': _build_azure,
}


def get_storage(
    provider: AvailableProviders | None = None, /, **overrides: Any
) -> Storix:
    """Build a Storix session from settings.

    ``provider`` overrides ``STORIX_PROVIDER`` (default: local at
    ``~/.storix``); keyword overrides beat the corresponding
    ``STORIX_<PROVIDER>_*`` environment values.
    """
    name = provider or StorixSettings().provider
    builder = _BUILDERS.get(name)
    if builder is None:
        msg = f'unknown storage provider {name!r}; available: {sorted(_BUILDERS)}'
        raise ConfigurationError(msg)
    return Storix(builder(**overrides))
