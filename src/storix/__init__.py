"""Storix: storage for unix lovers - sync flavor.

The async twin lives at ``storix.aio`` with identical names; backends
are under ``storix.backends`` / ``storix.aio.backends``.
"""

from storix import errors
from storix._sync import (
    PassthroughLayer,
    SandboxLayer,
    Storix,
    get_storage,
    scratch,
    temporary,
)
from storix.enums import Capability, PathKind
from storix.models import Capabilities, Entry, FileProperties, RawStat
from storix.types import AvailableProviders, StorixPath, StrPathLike


__all__ = (
    'AvailableProviders',
    'Capabilities',
    'Capability',
    'Entry',
    'FileProperties',
    'PassthroughLayer',
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
