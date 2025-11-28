"""Async version of storix - identical API but with async/await."""

from typing import TYPE_CHECKING

from storix._internal._lazy import lazy_import as _limp


__all__ = (
    'AvailableProviders',
    'AzureDataLake',
    'LocalFilesystem',
    'Storage',
    'StorixPath',
    'StrPathLike',
    'get_storage',
)


# <-- types --> #
StorixPath = _limp('.types', 'StorixPath')
StrPathLike = _limp('.types', 'StrPathLike')
AvailableProviders = _limp('.types', 'AvailableProviders')

# <-- interface & factory --> #
get_storage = _limp('.factory', 'get_storage')
Storage = _limp('.providers._proto', 'Storage')

# <-- providers --> #
AzureDataLake = _limp('.providers.azure', 'AzureDataLake')
LocalFilesystem = _limp('.providers.local', 'LocalFilesystem')


if TYPE_CHECKING:
    from ..types import AvailableProviders, StorixPath, StrPathLike
    from .factory import get_storage
    from .providers._proto import Storage
    from .providers.azure import AzureDataLake
    from .providers.local import LocalFilesystem


def __dir__() -> list[str]:
    return list(__all__)
