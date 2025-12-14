from __future__ import annotations

from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    from ..types import AvailableProviders, StrPathLike
    from .providers._proto import Storage


def get_storage(
    provider: AvailableProviders | str | None = None,
    initialpath: StrPathLike | None = None,
    sandboxed: bool | None = None,
) -> Storage:
    """Get a storage instance with optional runtime overrides.

    Args:
        provider: Override the provider from environment settings. If None, uses
            STORAGE_PROVIDER from environment or settings.
        initialpath: Override the initial path from environment settings. If None, uses
            provider-specific default paths from environment or settings.
        sandboxed: Override sandboxing from environment settings. If None, uses
            default sandboxing behavior.

    Returns:
        Storage: A configured storage instance. Provider-specific settings (like
            credentials) are automatically loaded from environment or .env files.

    Raises:
        ValueError: If STORAGE_PROVIDER is not supported.
    """
    import os

    from ..settings import get_settings

    settings = get_settings()

    provider = str(
        provider or settings.STORAGE_PROVIDER or os.environ.get('STORAGE_PROVIDER')
    ).lower()

    params: dict[str, Any] = {}
    if initialpath is not None:
        params['initialpath'] = initialpath
    if sandboxed is not None:
        params['sandboxed'] = sandboxed

    if provider == 'local':
        from .providers.local import LocalFilesystem

        return LocalFilesystem(**params)
    if provider == 'azure':
        from .providers.azure import AzureDataLake

        return AzureDataLake(**params)

    msg = f'Unsupported storage provider: {provider}'
    raise ValueError(msg)
