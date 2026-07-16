"""Storix: storage for unix lovers - sync flavor.

The async twin lives at ``storix.aio`` with identical names; backends
are under ``storix.backends`` / ``storix.aio.backends``.
"""

from storix import errors
from storix._sync import (
    BoundLayer,
    CacheLayer,
    CacheOp,
    CacheStore,
    DataUrlLayer,
    InMemoryCacheStore,
    LayerBase,
    LayerFactory,
    MetadataLayer,
    ObservabilityLayer,
    SandboxLayer,
    Storix,
    TransferEvent,
    available_providers,
    cache,
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
    'BoundLayer',
    'CacheLayer',
    'CacheOp',
    'CacheStore',
    'Capabilities',
    'Capability',
    'DataUrlLayer',
    'Entry',
    'FileProperties',
    'InMemoryCacheStore',
    'LayerBase',
    'LayerFactory',
    'MetadataLayer',
    'ObservabilityLayer',
    'PathKind',
    'RawStat',
    'SandboxLayer',
    'StorageProvider',
    'Storix',
    'StorixPath',
    'StrPathLike',
    'TransferEvent',
    'available_providers',
    'cache',
    'errors',
    'get_storage',
    'register_backend',
    'scratch',
    'temporary',
    'when_missing',
)
