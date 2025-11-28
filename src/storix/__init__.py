"""Sync version of storix."""

from typing import TYPE_CHECKING

from storix._internal._lazy import _limp


__all__ = (
    'AvailableProviders',
    'AzureDataLake',
    'LocalFilesystem',
    'PathNotFoundError',
    'Storage',
    'StorixError',
    'StorixPath',
    'StrPathLike',
    'errors',
    'get_storage',
)


# <-- errors --> #
errors = _limp('.', 'errors')
PathNotFoundError = _limp('.errors', 'PathNotFoundError')
StorixError = _limp('.errors', 'StorixError')

# <-- interface & factory --> #
get_storage = _limp('.factory', 'get_storage')
Storage = _limp('.providers._proto', 'Storage')

# <-- providers --> #
AzureDataLake = _limp('.providers.azure', 'AzureDataLake')
LocalFilesystem = _limp('.providers.local', 'LocalFilesystem')

# <-- types --> #
StorixPath = _limp('.types', 'StorixPath')
StrPathLike = _limp('.types', 'StrPathLike')
AvailableProviders = _limp('.types', 'AvailableProviders')


if TYPE_CHECKING:
    from . import errors
    from .errors import PathNotFoundError, StorixError
    from .factory import get_storage
    from .providers._proto import Storage
    from .providers.azure import AzureDataLake
    from .providers.local import LocalFilesystem
    from .types import AvailableProviders, StorixPath, StrPathLike


def __dir__() -> list[str]:
    return list(__all__)
