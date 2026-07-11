# ruff: noqa: A004 - storix error classes intentionally shadow stdlib names
"""Azure Data Lake Gen2 backend (async flavor).

Hand-written twin pair (excluded from codegen): the sync sibling imports
the non-aio SDK. Keep ``storix._sync.backends.azure`` in lockstep by
hand; the conformance suite (integration-marked) is the drift guard.

Requires a storage account with **hierarchical namespaces enabled** -
the dfs endpoint this backend speaks only exists on HNS accounts. Flat
(portal-default) blob accounts are not supported; enable HNS on the
account or wait for the flat-namespace adapter.
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
    from azure.storage.filedatalake.aio import DataLakeServiceClient
except ImportError as err:  # pragma: no cover
    _msg = "azure backend not installed - install with: uv add 'storix[azure]'"
    raise ImportError(_msg) from err


if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Mapping

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

    capabilities: Capabilities = Capabilities(
        content_type=True, custom_metadata=True, presigned_urls=True
    )

    def __init__(self, container: str, *, account_name: str, credential: str) -> None:
        self.container = container
        self._account_name = account_name
        self._credential = credential
        self._service = DataLakeServiceClient(
            account_url=f'https://{account_name}.dfs.core.windows.net',
            credential=credential,
        )
        self._filesystem = self._service.get_file_system_client(container)

    @staticmethod
    def _key(path: PurePosixPath) -> str:
        """Container-relative key for a port path ('' for the root)."""
        return str(path).lstrip('/')

    def locate(self, path: PurePosixPath) -> str:
        """``abfss://`` URI (the standard ADLS Gen2 locator)."""
        host = f'{self._account_name}.dfs.core.windows.net'
        return f'abfss://{self.container}@{host}/{self._key(path)}'

    async def read_stream(self, path: PurePosixPath) -> AsyncIterator[bytes]:
        """Stream a file's contents in chunks."""
        raw = await self.stat(path)
        if raw.kind is PathKind.DIRECTORY:
            # dfs 'downloads' a directory marker as zero bytes; refuse instead
            raise IsADirectoryError(path)
        client = self._filesystem.get_file_client(self._key(path))
        try:
            download = await client.download_file()
        except AzureError as exc:
            raise _translate(exc, path) from exc
        async for chunk in download.chunks():
            yield chunk

    async def write(
        self,
        path: PurePosixPath,
        data: AsyncIterator[bytes],
        *,
        mode: EchoMode,
        content_type: str | None,
        metadata: Mapping[str, str] | None = None,
    ) -> None:
        """Write a file from a chunk stream ('w' truncates, 'a' appends)."""
        offset = 0
        try:
            raw = await self.stat(path)
        except PathNotFoundError:
            raw = None
        if raw is not None:
            if raw.kind is PathKind.DIRECTORY:
                raise IsADirectoryError(path)
            if mode == 'a':
                offset = raw.size

        client = self._filesystem.get_file_client(self._key(path))
        creating = raw is None or mode == 'w'
        try:
            if creating:
                # metadata rides along with creation - one request, not two
                await client.create_file(metadata=dict(metadata) if metadata else None)
            async for chunk in data:
                if not chunk:
                    continue
                await client.append_data(chunk, offset=offset, length=len(chunk))
                offset += len(chunk)
            settings = (
                ContentSettings(content_type=content_type) if content_type else None
            )
            await client.flush_data(offset, content_settings=settings)
            if metadata is not None and not creating:
                await client.set_metadata(dict(metadata))
        except AzureError as exc:
            raise _translate(exc, path) from exc

    async def delete(self, path: PurePosixPath) -> None:
        """Delete a leaf: a file or an *empty* directory.

        The emptiness check is explicit because the SDK's directory
        delete is recursive; relying on it would silently violate the
        leaf-delete contract.
        """
        raw = await self.stat(path)
        key = self._key(path)
        try:
            if raw.kind is PathKind.DIRECTORY:
                async for _ in self._filesystem.get_paths(path=key, recursive=False):
                    raise DirectoryNotEmptyError(path)
                await self._filesystem.get_directory_client(key).delete_directory()
            else:
                await self._filesystem.get_file_client(key).delete_file()
        except AzureError as exc:
            raise _translate(exc, path) from exc

    async def list_dir(self, path: PurePosixPath) -> AsyncIterator[Entry]:
        """Yield the direct children of a directory, sizes included."""
        raw = await self.stat(path)
        if raw.kind is PathKind.FILE:
            raise NotADirectoryError(path)
        key = self._key(path)
        try:
            async for item in self._filesystem.get_paths(
                path=key or None, recursive=False
            ):
                is_dir = bool(item.is_directory)
                yield Entry(
                    name=PurePosixPath(item.name).name,
                    is_dir=is_dir,
                    size=None if is_dir else item.content_length or 0,
                )
        except AzureError as exc:
            raise _translate(exc, path) from exc

    async def stat(self, path: PurePosixPath) -> RawStat:
        """Return raw facts about a path (directory sizes are 0)."""
        key = self._key(path)
        try:
            if not key:  # the container root is always a directory
                props = await self._filesystem.get_file_system_properties()
                return RawStat(
                    kind=PathKind.DIRECTORY,
                    size=0,
                    created=props.last_modified,
                    modified=props.last_modified,
                    accessed=None,
                )
            file_props = await self._filesystem.get_file_client(
                key
            ).get_file_properties()
        except AzureError as exc:
            raise _translate(exc, path) from exc
        raw_metadata = dict(file_props.metadata or {})
        is_dir = bool(raw_metadata.pop('hdi_isfolder', None))
        return RawStat(
            kind=PathKind.DIRECTORY if is_dir else PathKind.FILE,
            size=0 if is_dir else file_props.size,
            created=file_props.creation_time,
            modified=file_props.last_modified,
            accessed=None,
            metadata=raw_metadata or None,
        )

    async def make_dir(self, path: PurePosixPath, *, parents: bool) -> None:
        """Create a directory (``parents=True`` behaves like mkdir -p).

        dfs creates intermediate directories implicitly, so the port's
        plain-mkdir contract (existing target / missing parent /
        non-directory parent) is enforced explicitly here.
        """
        try:
            existing = await self.stat(path)
        except PathNotFoundError:
            existing = None
        if existing is not None:
            if parents and existing.kind is PathKind.DIRECTORY:
                return
            raise AlreadyExistsError(path)

        if not parents and self._key(path.parent):
            parent_raw = await self.stat(path.parent)  # raises PathNotFound(parent)
            if parent_raw.kind is not PathKind.DIRECTORY:
                raise NotADirectoryError(path.parent)

        try:
            await self._filesystem.create_directory(self._key(path))
        except AzureError as exc:
            raise _translate(exc, path) from exc

    async def exists(self, path: PurePosixPath) -> bool:
        """Whether anything lives at ``path`` (native fast path)."""
        key = self._key(path)
        if not key:
            return True
        try:
            return await self._filesystem.get_file_client(key).exists()
        except AzureError as exc:
            raise _translate(exc, path) from exc

    async def move(self, src: PurePosixPath, dst: PurePosixPath) -> None:
        """Move a file or directory tree via native (atomic) dfs rename."""
        raw = await self.stat(src)
        new_name = f'{self.container}/{self._key(dst)}'
        try:
            if raw.kind is PathKind.DIRECTORY:
                client = self._filesystem.get_directory_client(self._key(src))
                await client.rename_directory(new_name)
            else:
                file_client = self._filesystem.get_file_client(self._key(src))
                await file_client.rename_file(new_name)
        except AzureError as exc:
            raise _translate(exc, src) from exc

    async def delete_tree(self, path: PurePosixPath) -> None:
        """Delete ``path`` and everything below it via native recursion."""
        key = self._key(path)
        if not key:
            operation = 'delete_tree on the container root'
            raise UnsupportedOperationError(operation)
        raw = await self.stat(path)
        if raw.kind is PathKind.FILE:
            raise NotADirectoryError(path)
        try:
            await self._filesystem.get_directory_client(key).delete_directory()
        except AzureError as exc:
            raise _translate(exc, path) from exc

    async def set_metadata(
        self, path: PurePosixPath, metadata: Mapping[str, str]
    ) -> None:
        """Replace a file's custom metadata without touching its content."""
        raw = await self.stat(path)
        if raw.kind is PathKind.DIRECTORY:
            raise IsADirectoryError(path)
        try:
            client = self._filesystem.get_file_client(self._key(path))
            await client.set_metadata(dict(metadata))
        except AzureError as exc:
            raise _translate(exc, path) from exc

    async def make_url(
        self, path: PurePosixPath, *, expires_in: int | None = None
    ) -> str:
        """Mint a read-only SAS URL for a file.

        ``None`` applies the storix default lifetime. SAS generation is
        local HMAC crypto (no request) and requires the backend
        credential to be an account key.
        """
        if expires_in is None:
            from storix.constants import DEFAULT_URL_EXPIRY_SECONDS

            expires_in = DEFAULT_URL_EXPIRY_SECONDS
        raw = await self.stat(path)
        if raw.kind is PathKind.DIRECTORY:
            raise IsADirectoryError(path)

        import datetime as dt

        from azure.storage.filedatalake import FileSasPermissions, generate_file_sas

        from storix.utils import craft_adlsg2_url_sas
        from storix.utils.time import utcnow

        directory = str(path.parent).lstrip('/')
        token = generate_file_sas(
            account_name=self._account_name,
            file_system_name=self.container,
            credential=self._credential,
            directory_name=directory,
            file_name=path.name,
            permission=FileSasPermissions(read=True),
            expiry=utcnow() + dt.timedelta(seconds=expires_in),
        )
        return craft_adlsg2_url_sas(
            account_name=self._account_name,
            container=self.container,
            directory=directory,
            filename=path.name,
            sas_token=token,
        )

    async def close(self) -> None:
        """Close the underlying service client (idempotent)."""
        await self._service.close()
