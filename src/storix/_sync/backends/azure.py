# ruff: noqa: A004 - storix error classes intentionally shadow stdlib names
"""Azure Data Lake Gen2 backend (sync flavor).

Hand-written twin of ``storix._async.backends.azure`` - NOT generated.
Same semantics over the non-aio SDK; keep in lockstep by hand. The
conformance suite (integration-marked) is the drift guard.

Requires a storage account with **hierarchical namespaces enabled** -
the dfs endpoint this backend speaks only exists on HNS accounts.
"""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import TYPE_CHECKING

from storix.enums import PathKind
from storix.errors import (
    AlreadyExistsError,
    DirectoryNotEmptyError,
    IsADirectoryError,
    NotADirectoryError,
    PathNotFoundError,
    PermissionDeniedError,
    StorageError,
    UnsupportedOperationError,
)
from storix.models import Capabilities, Entry, RawStat

from .base import BackendBase


try:
    from azure.core.exceptions import (
        AzureError,
        ClientAuthenticationError,
        HttpResponseError,
        ResourceExistsError,
        ResourceNotFoundError,
    )
    from azure.storage.blob import ContentSettings
    from azure.storage.filedatalake import DataLakeServiceClient
except ImportError as err:  # pragma: no cover
    _msg = "azure backend not installed - install with: uv add 'storix[azure]'"
    raise ImportError(_msg) from err


if TYPE_CHECKING:
    from collections.abc import Iterator

    from storix.types import EchoMode


_HNS_HINT = (
    ' (is hierarchical namespace enabled on this storage account?'
    ' the Data Lake Gen2 endpoint requires HNS)'
)

# dfs error codes -> storix taxonomy; refined as integration runs surface
# more codes
_ERROR_CODE_MAP: dict[str, type[StorageError]] = {
    'PathNotFound': PathNotFoundError,
    'BlobNotFound': PathNotFoundError,
    'FilesystemNotFound': PathNotFoundError,
    'DirectoryNotEmpty': DirectoryNotEmptyError,
    'PathAlreadyExists': AlreadyExistsError,
    'BlobAlreadyExists': AlreadyExistsError,
    'AuthorizationFailure': PermissionDeniedError,
    'AuthorizationPermissionMismatch': PermissionDeniedError,
}


def _translate(exc: AzureError, path: PurePosixPath) -> StorageError:
    """Translate SDK failures into the storix taxonomy (best effort)."""
    code = str(getattr(exc, 'error_code', '') or '')
    mapped = _ERROR_CODE_MAP.get(code)
    if mapped is not None:
        return mapped(path)
    if isinstance(exc, ResourceNotFoundError):
        return PathNotFoundError(path)
    if isinstance(exc, ResourceExistsError):
        return AlreadyExistsError(path)
    if isinstance(exc, ClientAuthenticationError):
        return PermissionDeniedError(path)
    if isinstance(exc, HttpResponseError):
        return StorageError(f"'{path}': {exc.message}{_HNS_HINT}")
    return StorageError(f"'{path}': {exc}")


class AzureBackend(BackendBase):
    """ADLS Gen2 backend anchored at one container (filesystem).

    The container is namespace configuration: port path ``/x`` maps to
    the container-relative path ``x``. The container is neither created
    nor validated at construction; operations against a missing one fail
    with ``PathNotFoundError``.
    """

    capabilities: Capabilities = Capabilities(content_type=True)

    def __init__(self, container: str, *, account_name: str, credential: str) -> None:
        self.container = container
        self._service = DataLakeServiceClient(
            account_url=f'https://{account_name}.dfs.core.windows.net',
            credential=credential,
        )
        self._filesystem = self._service.get_file_system_client(container)

    @staticmethod
    def _key(path: PurePosixPath) -> str:
        """Container-relative key for a port path ('' for the root)."""
        return str(path).lstrip('/')

    def read_stream(self, path: PurePosixPath) -> Iterator[bytes]:
        """Stream a file's contents in chunks."""
        raw = self.stat(path)
        if raw.kind is PathKind.DIRECTORY:
            # dfs 'downloads' a directory marker as zero bytes; refuse instead
            raise IsADirectoryError(path)
        client = self._filesystem.get_file_client(self._key(path))
        try:
            download = client.download_file()
        except AzureError as exc:
            raise _translate(exc, path) from exc
        yield from download.chunks()

    def write(
        self,
        path: PurePosixPath,
        data: Iterator[bytes],
        *,
        mode: EchoMode,
        content_type: str | None,
    ) -> None:
        """Write a file from a chunk stream ('w' truncates, 'a' appends)."""
        offset = 0
        try:
            raw = self.stat(path)
        except PathNotFoundError:
            raw = None
        if raw is not None:
            if raw.kind is PathKind.DIRECTORY:
                raise IsADirectoryError(path)
            if mode == 'a':
                offset = raw.size

        client = self._filesystem.get_file_client(self._key(path))
        try:
            if raw is None or mode == 'w':
                client.create_file()
            for chunk in data:
                if not chunk:
                    continue
                client.append_data(chunk, offset=offset, length=len(chunk))
                offset += len(chunk)
            settings = (
                ContentSettings(content_type=content_type) if content_type else None
            )
            client.flush_data(offset, content_settings=settings)
        except AzureError as exc:
            raise _translate(exc, path) from exc

    def delete(self, path: PurePosixPath) -> None:
        """Delete a leaf: a file or an *empty* directory.

        The emptiness check is explicit because the SDK's directory
        delete is recursive; relying on it would silently violate the
        leaf-delete contract.
        """
        raw = self.stat(path)
        key = self._key(path)
        try:
            if raw.kind is PathKind.DIRECTORY:
                for _ in self._filesystem.get_paths(path=key, recursive=False):
                    raise DirectoryNotEmptyError(path)
                self._filesystem.get_directory_client(key).delete_directory()
            else:
                self._filesystem.get_file_client(key).delete_file()
        except AzureError as exc:
            raise _translate(exc, path) from exc

    def list_dir(self, path: PurePosixPath) -> Iterator[Entry]:
        """Yield the direct children of a directory, sizes included."""
        raw = self.stat(path)
        if raw.kind is PathKind.FILE:
            raise NotADirectoryError(path)
        key = self._key(path)
        try:
            for item in self._filesystem.get_paths(path=key or None, recursive=False):
                is_dir = bool(item.is_directory)
                yield Entry(
                    name=PurePosixPath(item.name).name,
                    is_dir=is_dir,
                    size=None if is_dir else item.content_length or 0,
                )
        except AzureError as exc:
            raise _translate(exc, path) from exc

    def stat(self, path: PurePosixPath) -> RawStat:
        """Return raw facts about a path (directory sizes are 0)."""
        key = self._key(path)
        try:
            if not key:  # the container root is always a directory
                props = self._filesystem.get_file_system_properties()
                return RawStat(
                    kind=PathKind.DIRECTORY,
                    size=0,
                    created=props.last_modified,
                    modified=props.last_modified,
                    accessed=None,
                )
            file_props = self._filesystem.get_file_client(key).get_file_properties()
        except AzureError as exc:
            raise _translate(exc, path) from exc
        is_dir = bool((file_props.metadata or {}).get('hdi_isfolder'))
        return RawStat(
            kind=PathKind.DIRECTORY if is_dir else PathKind.FILE,
            size=0 if is_dir else file_props.size,
            created=file_props.creation_time,
            modified=file_props.last_modified,
            accessed=None,
        )

    def make_dir(self, path: PurePosixPath, *, parents: bool) -> None:
        """Create a directory (``parents=True`` behaves like mkdir -p).

        dfs creates intermediate directories implicitly, so the port's
        plain-mkdir contract (existing target / missing parent /
        non-directory parent) is enforced explicitly here.
        """
        try:
            existing = self.stat(path)
        except PathNotFoundError:
            existing = None
        if existing is not None:
            if parents and existing.kind is PathKind.DIRECTORY:
                return
            raise AlreadyExistsError(path)

        if not parents and self._key(path.parent):
            parent_raw = self.stat(path.parent)  # raises PathNotFound(parent)
            if parent_raw.kind is not PathKind.DIRECTORY:
                raise NotADirectoryError(path.parent)

        try:
            self._filesystem.create_directory(self._key(path))
        except AzureError as exc:
            raise _translate(exc, path) from exc

    def exists(self, path: PurePosixPath) -> bool:
        """Whether anything lives at ``path`` (native fast path)."""
        key = self._key(path)
        if not key:
            return True
        try:
            return self._filesystem.get_file_client(key).exists()
        except AzureError as exc:
            raise _translate(exc, path) from exc

    def move(self, src: PurePosixPath, dst: PurePosixPath) -> None:
        """Move a file or directory tree via native (atomic) dfs rename."""
        raw = self.stat(src)
        new_name = f'{self.container}/{self._key(dst)}'
        try:
            if raw.kind is PathKind.DIRECTORY:
                client = self._filesystem.get_directory_client(self._key(src))
                client.rename_directory(new_name)
            else:
                file_client = self._filesystem.get_file_client(self._key(src))
                file_client.rename_file(new_name)
        except AzureError as exc:
            raise _translate(exc, src) from exc

    def delete_tree(self, path: PurePosixPath) -> None:
        """Delete ``path`` and everything below it via native recursion."""
        key = self._key(path)
        if not key:
            operation = 'delete_tree on the container root'
            raise UnsupportedOperationError(operation)
        raw = self.stat(path)
        if raw.kind is PathKind.FILE:
            raise NotADirectoryError(path)
        try:
            self._filesystem.get_directory_client(key).delete_directory()
        except AzureError as exc:
            raise _translate(exc, path) from exc

    def close(self) -> None:
        """Close the underlying service client (idempotent)."""
        self._service.close()
