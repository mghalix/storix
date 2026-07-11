"""Storix: storage for unix lovers - async flavor.

Identical names to the sync package; every operation is awaitable.
"""

from storix import errors
from storix._async import SandboxLayer, Storix, get_storage, scratch, temporary
from storix.enums import Capability, PathKind
from storix.models import Capabilities, Entry, FileProperties, RawStat
from storix.types import AvailableProviders, StorixPath, StrPathLike


__all__ = (
    'AvailableProviders',
    'Capabilities',
    'Capability',
    'Entry',
    'FileProperties',
    'PathKind',
    'RawStat',
    'SandboxLayer',
    'Storix',
    'StorixPath',
    'StrPathLike',
    'errors',
    'get_storage',
    'scratch',
    'temporary',
)
