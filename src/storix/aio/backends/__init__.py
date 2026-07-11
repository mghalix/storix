"""Async storage backends (sync twins: ``storix.backends``).

``AzureBackend`` loads lazily - the azure SDK is an optional dependency
(``storix[azure]``).
"""

from typing import TYPE_CHECKING, Any

from storix._async.backends import BackendBase, StorageBackend
from storix._async.backends.local import LocalBackend
from storix._async.backends.memory import MemoryBackend


if TYPE_CHECKING:
    from storix._async.backends.azure import AzureBackend


__all__ = (
    'AzureBackend',
    'BackendBase',
    'LocalBackend',
    'MemoryBackend',
    'StorageBackend',
)


def __getattr__(name: str) -> Any:
    if name == 'AzureBackend':
        from storix._async.backends.azure import AzureBackend

        return AzureBackend
    msg = f'module {__name__!r} has no attribute {name!r}'
    raise AttributeError(msg)
