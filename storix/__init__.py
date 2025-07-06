"""Sync version of storix."""

from storix.typing import AvailableProviders, PathLike

from .providers import AzureDataLake, LocalFilesystem, Storage
from .settings import settings

__all__ = [
    "AzureDataLake",
    "LocalFilesystem",
    "Storage",
    "get_storage",
]


def get_storage(
    provider: AvailableProviders | str | None = None,
    initialpath: PathLike | None = None,
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

    provider = str(
        provider or settings.STORAGE_PROVIDER or os.environ.get("STORAGE_PROVIDER")
    ).lower()

    params = {}
    if initialpath is not None:
        params["initialpath"] = initialpath
    if sandboxed is not None:
        params["sandboxed"] = sandboxed

    if provider == "local":
        return LocalFilesystem(**params)
    if provider == "azure":
        return AzureDataLake(**params)
    raise ValueError(f"Unsupported storage provider: {provider}")


__version__ = "0.0.1"
