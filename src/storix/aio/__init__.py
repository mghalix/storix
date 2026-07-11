"""Storix: storage for unix lovers - async flavor.

Identical names to the sync package; every operation is awaitable.
"""

from storix import errors
from storix._async import (
    DataUrlLayer,
    LayerBase,
    MetadataLayer,
    SandboxLayer,
    Storix,
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
    'Capabilities',
    'Capability',
    'DataUrlLayer',
    'Entry',
    'FileProperties',
    'LayerBase',
    'MetadataLayer',
    'SandboxLayer',
    'StorageProvider',
    'Storix',
    'StorixPath',
    'StrPathLike',
    'errors',
    'get_storage',
    'register_backend',
    'scratch',
    'temporary',
    'when_missing',
)
