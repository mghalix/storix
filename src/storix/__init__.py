"""Storix: storage for unix lovers - sync flavor.

The async twin lives at ``storix.aio`` with identical names; backends
are under ``storix.backends`` / ``storix.aio.backends``.
"""

from storix import errors
from storix._sync import (
    CacheLayer,
    DataUrlLayer,
    LayerBase,
    MetadataLayer,
    SandboxLayer,
    Storix,
    available_providers,
    get_storage,
    register_backend,
    scratch,
    temporary,
    when_missing,
)
from storix.enums import Capability, PathKind
from storix.models import Capabilities, Entry, FileProperties, RawStat
from storix.types import StorageProvider, StorixPath, StrPathLike


__all__ = (
    'CacheLayer',
    'Capabilities',
    'Capability',
    'DataUrlLayer',
    'Entry',
    'FileProperties',
    'LayerBase',
    'MetadataLayer',
    'PathKind',
    'RawStat',
    'SandboxLayer',
    'StorageProvider',
    'Storix',
    'StorixPath',
    'StrPathLike',
    'available_providers',
    'errors',
    'get_storage',
    'register_backend',
    'scratch',
    'temporary',
    'when_missing',
)
