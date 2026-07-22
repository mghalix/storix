# ruff: noqa: A004 - storix error classes intentionally shadow stdlib names
"""Azure Data Lake Gen2 backend (async flavor).

Hand-written twin pair (excluded from codegen): the sync sibling imports
the non-aio SDK. Keep ``storix._sync.backends.azure`` in lockstep by
hand; the conformance suite (integration-marked) is the drift guard.

Requires a storage account with **hierarchical namespaces enabled** -
the dfs endpoint this backend speaks only exists on HNS accounts. Flat
(portal-default) blob accounts are not supported here; use
``AzureBlobBackend`` for those.
"""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import TYPE_CHECKING

from storix._async._stream import batch_chunks, resolve_chunk_size, split_chunks
from storix.constants import (
    DEFAULT_AZURE_READ_CHUNK_SIZE,
    DEFAULT_AZURE_READ_PREFETCH_SIZE,
    DEFAULT_AZURE_WRITE_CHUNK_SIZE,
)
from storix.enums import PathKind
from storix.errors import (
    AlreadyExistsError,
    ConfigurationError,
    DirectoryNotEmptyError,
    IsADirectoryError,
    NotADirectoryError,
    PathNotFoundError,
    PermissionDeniedError,
    StorageError,
    StorageRootNotFoundError,
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
except ModuleNotFoundError as exc:  # pragma: no cover
    if (exc.name or '').partition('.')[0] != 'azure':
        raise
    _msg = (
        'azure extra not installed. Install it by running '
        "`uv add 'storix[azure]'` (or the lean, ADLS-only `storix[azadls]`)."
    )
    raise ImportError(_msg) from None


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
    if code in {'AuthenticationFailed', 'InvalidAuthenticationInfo'} or isinstance(
        exc, ClientAuthenticationError
    ):
        return ConfigurationError(
            'azure authentication failed; check account_name and credential'
        )
    if isinstance(exc, ResourceNotFoundError):
        return PathNotFoundError(path)
    if isinstance(exc, ResourceExistsError):
        return AlreadyExistsError(path)
    if isinstance(exc, HttpResponseError):
        return StorageError(f"'{path}': {exc.message}{_HNS_HINT}")
    return StorageError(f"'{path}': {exc}")


class AzureBackend(BackendBase):
    """ADLS Gen2 backend anchored at one container (filesystem).

    The container is namespace configuration: port path ``/x`` maps to
    the container-relative path ``x``. The container is neither created
    nor validated at construction; operations against a missing one fail
    with ``StorageRootNotFoundError`` naming it (ADR 0029).
    """

    capabilities: Capabilities = Capabilities(
        content_type=True, custom_metadata=True, presigned_urls=True
    )
    default_read_chunk_size: int = DEFAULT_AZURE_READ_CHUNK_SIZE
    default_write_chunk_size: int = DEFAULT_AZURE_WRITE_CHUNK_SIZE

    def __init__(
        self,
        container: str,
        *,
        account_name: str,
        credential: str,
        read_chunk_size: int = DEFAULT_AZURE_READ_CHUNK_SIZE,
        write_chunk_size: int = DEFAULT_AZURE_WRITE_CHUNK_SIZE,
        read_prefetch_size: int = DEFAULT_AZURE_READ_PREFETCH_SIZE,
    ) -> None:
        """Create an ADLS Gen2 backend.

        Args:
            container: Filesystem/container anchoring port path ``/``.
            account_name: HNS-enabled Azure Storage account name.
            credential: SAS token or account key.
            read_chunk_size: Default consumer and SDK range chunk size.
            write_chunk_size: Default ``append_data`` request batch size.
            read_prefetch_size: Size of the SDK's initial download request.

        Raises:
            ValueError: If any configured transfer size is not positive.
        """
        self.default_read_chunk_size = resolve_chunk_size(
            read_chunk_size, read_chunk_size
        )
        self.default_write_chunk_size = resolve_chunk_size(
            write_chunk_size, write_chunk_size
        )
        read_prefetch_size = resolve_chunk_size(read_prefetch_size, read_prefetch_size)
        self.container = container
        self._account_name = account_name
        self._credential = credential
        self._service = DataLakeServiceClient(
            account_url=f'https://{account_name}.dfs.core.windows.net',
            credential=credential,
            max_chunk_get_size=self.default_read_chunk_size,
            max_single_get_size=read_prefetch_size,
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

    def _error(self, exc: AzureError, path: PurePosixPath) -> StorageError:
        """Translate an SDK failure, detecting a missing filesystem root."""
        if str(getattr(exc, 'error_code', '') or '') == 'FilesystemNotFound':
            return StorageRootNotFoundError(self.container, kind='azure filesystem')
        return _translate(exc, path)

    async def read_stream(
        self, path: PurePosixPath, *, chunk_size: int | None = None
    ) -> AsyncIterator[bytes]:
        """Stream a file through the SDK with bounded consumer chunks.

        Raises:
            ValueError: If ``chunk_size`` is zero or negative.
        """
        size = resolve_chunk_size(chunk_size, self.default_read_chunk_size)
        raw = await self.stat(path)
        if raw.kind is PathKind.DIRECTORY:
            # dfs 'downloads' a directory marker as zero bytes; refuse instead
            raise IsADirectoryError(path)
        client = self._filesystem.get_file_client(self._key(path))
        try:
            download = await client.download_file()
            async for chunk in split_chunks(download.chunks(), size):
                yield chunk
        except AzureError as exc:
            raise self._error(exc, path) from exc

    async def write_stream(
        self,
        path: PurePosixPath,
        data: AsyncIterator[bytes],
        *,
        chunk_size: int | None = None,
        mode: EchoMode,
        content_type: str | None,
        metadata: Mapping[str, str] | None = None,
    ) -> None:
        """Write batched range appends, then flush the completed file.

        Raises:
            ValueError: If ``chunk_size`` is zero or negative.
        """
        size = resolve_chunk_size(chunk_size, self.default_write_chunk_size)
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
            async for chunk in batch_chunks(data, size):
                await client.append_data(chunk, offset=offset, length=len(chunk))
                offset += len(chunk)
            settings = (
                ContentSettings(content_type=content_type) if content_type else None
            )
            await client.flush_data(offset, content_settings=settings)
            if metadata is not None and not creating:
                await client.set_metadata(dict(metadata))
        except AzureError as exc:
            raise self._error(exc, path) from exc

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
            raise self._error(exc, path) from exc

    async def list_dir(self, path: PurePosixPath) -> AsyncIterator[Entry]:
        """Yield the direct children of a directory, sizes included.

        One request, no stat precheck: dfs list disambiguates every case
        itself. A missing path raises ``PathNotFound``, an empty
        directory lists nothing, and a *file* target lists exactly one
        entry named like the target, which becomes NotADirectoryError.
        """
        key = self._key(path)
        try:
            async for item in self._filesystem.get_paths(
                path=key or None, recursive=False
            ):
                if item.name == key:
                    raise NotADirectoryError(path)
                is_dir = bool(item.is_directory)
                yield Entry(
                    name=PurePosixPath(item.name).name,
                    is_dir=is_dir,
                    size=None if is_dir else item.content_length or 0,
                )
        except AzureError as exc:
            raise self._error(exc, path) from exc

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
            raise self._error(exc, path) from exc
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
            raise self._error(exc, path) from exc

    async def exists(self, path: PurePosixPath) -> bool:
        """Whether anything lives at ``path`` (native fast path)."""
        key = self._key(path)
        if not key:
            return True
        try:
            return await self._filesystem.get_file_client(key).exists()
        except AzureError as exc:
            raise self._error(exc, path) from exc

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
            raise self._error(exc, src) from exc

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
            raise self._error(exc, path) from exc

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
            raise self._error(exc, path) from exc

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

    async def provision(self) -> bool:
        """Create the ADLS filesystem (container) if missing. Idempotent.

        Attempts to create the filesystem on the native SDK client the
        backend already holds. A pre-existing filesystem, or a concurrent
        creator winning the race, surfaces as ``ResourceExistsError`` -
        the already-present signal, not a failure. Any other SDK failure
        is translated through the backend's error boundary.

        Returns:
            True if this call created the filesystem, False if it already
            existed.

        Raises:
            StorageError: If the SDK reports any failure other than the
                filesystem already existing (translated to the taxonomy).
        """
        try:
            await self._filesystem.create_file_system()
        except ResourceExistsError:
            return False
        except AzureError as exc:
            raise _translate(exc, PurePosixPath('/')) from exc
        return True

    async def close(self) -> None:
        """Close the underlying service client (idempotent)."""
        await self._service.close()
