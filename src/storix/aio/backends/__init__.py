"""Async storage backends (sync twins: ``storix.backends``).

``AzureBackend``, ``AzureBlobBackend``, ``S3Backend``, and ``GcsBackend``
load lazily - their engines are optional dependencies (``storix[azure]``,
``storix[azblob]``, ``storix[s3]``, ``storix[gcs]``).
"""

from typing import TYPE_CHECKING, Any

from storix._async.backends import BackendBase, StorageBackend
from storix._async.backends.local import LocalBackend
from storix._async.backends.memory import MemoryBackend


if TYPE_CHECKING:
    from storix._async.backends.azblob import AzureBlobBackend
    from storix._async.backends.azure import AzureBackend
    from storix._async.backends.gcs import GcsBackend
    from storix._async.backends.s3 import S3Backend


__all__ = (
    'AzureBackend',
    'AzureBlobBackend',
    'BackendBase',
    'GcsBackend',
    'LocalBackend',
    'MemoryBackend',
    'S3Backend',
    'StorageBackend',
)


def __getattr__(name: str) -> Any:
    if name == 'AzureBackend':
        from storix._async.backends.azure import AzureBackend

        return AzureBackend
    if name == 'AzureBlobBackend':
        from storix._async.backends.azblob import AzureBlobBackend

        return AzureBlobBackend
    if name == 'S3Backend':
        from storix._async.backends.s3 import S3Backend

        return S3Backend
    if name == 'GcsBackend':
        from storix._async.backends.gcs import GcsBackend

        return GcsBackend
    msg = f'module {__name__!r} has no attribute {name!r}'
    raise AttributeError(msg)
