"""Sync version of storix."""

from importlib import import_module
from typing import TYPE_CHECKING, Any

from storix._internal._lazy import _limp

from .providers._proto import Storage


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
# Storage = _limp('.providers._proto', 'Storage')

# <-- providers --> #
# AzureDataLake = _limp('.providers.azure', 'AzureDataLake')
# LocalFilesystem = _limp('.providers.local', 'LocalFilesystem')

# <-- types --> #
StorixPath = _limp('.types', 'StorixPath')
StrPathLike = _limp('.types', 'StrPathLike')
AvailableProviders = _limp('.types', 'AvailableProviders')

_dynamic_imports = {
    'AzureDataLake': (__spec__.parent, '.providers.azure'),
    'LocalFilesystem': (__spec__.parent, '.providers.local'),
}


def __getattr__(name: str) -> Any:
    _dynamic_attribute = _dynamic_imports.get(name)
    if _dynamic_attribute is None:
        msg = f'module {__name__} has no attribute {name!r}'
        raise AttributeError(msg)

    package, module_name = _dynamic_attribute

    if module_name == '__module__':
        result = import_module(f'.{name}', package=package)
        globals()[name] = result
        return result

    module = import_module(module_name, package=package)
    result = getattr(module, name)
    g = globals()
    for k, (_, v_mod_name) in _dynamic_imports.items():
        if v_mod_name == module_name:
            g[k] = getattr(module, k)
    return result


if TYPE_CHECKING:
    from . import errors
    from .errors import PathNotFoundError, StorixError
    from .factory import get_storage
    from .providers.azure import AzureDataLake
    from .providers.local import LocalFilesystem
    from .types import AvailableProviders, StorixPath, StrPathLike


def __dir__() -> list[str]:
    return list(__all__)
