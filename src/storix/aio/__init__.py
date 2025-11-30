"""Async version of storix - identical API but with async/await."""

import importlib

from typing import TYPE_CHECKING, Any

from storix._internal._lazy import lazy_import as _limp

from .providers._proto import Storage


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
StorixPath = _limp('storix.types', 'StorixPath')
StrPathLike = _limp('storix.types', 'StrPathLike')
AvailableProviders = _limp('storix.types', 'AvailableProviders')

# <-- interface & factory --> #
get_storage = _limp('.factory', 'get_storage')
# Storage = _limp('.providers._proto', 'Storage')


# <-- providers --> #
# AzureDataLake = _limp('.providers.azure', 'AzureDataLake')
# LocalFilesystem = _limp('.providers.local', 'LocalFilesystem')

_module_lookup = {
    'AzureDataLake': 'storix.aio.providers.azure',
    'LocalFilesystem': 'storix.aio.providers.local',
}


def __getattr__(name: str) -> Any:
    if name in _module_lookup:
        module = importlib.import_module(_module_lookup[name])
        attr = getattr(module, name)
        globals()[name] = attr
        return attr
    msg = f'module {__name__} has no attribute {name!r}'
    raise AttributeError(msg)


if TYPE_CHECKING:
    from ..types import AvailableProviders, StorixPath, StrPathLike
    from .factory import get_storage
    from .providers.azure import AzureDataLake
    from .providers.local import LocalFilesystem


def __dir__() -> list[str]:
    return list(__all__)
