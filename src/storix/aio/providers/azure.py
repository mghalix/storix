import asyncio
import contextlib
import datetime as dt
from collections.abc import AsyncIterator, Iterable, Sequence
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AnyStr, Literal, Self, TypeVar, overload, override

from storix.constants import DEFAULT_WRITE_CHUNKSIZE

try:
    from azure.storage.blob import ContentSettings
    from azure.storage.filedatalake.aio import (
        DataLakeDirectoryClient as AsyncDataLakeDirectoryClient,
    )
    from azure.storage.filedatalake.aio import (
        DataLakeFileClient as AsyncDataLakeFileClient,
    )
    from azure.storage.filedatalake.aio import (
        DataLakeServiceClient as AsyncDataLakeServiceClient,
    )
    from azure.storage.filedatalake.aio import FileSystemClient as AsyncFileSystemClient
except ImportError as err:
    raise ImportError(
        'azure backend not installed. Install it by running `"uv add storix[azure]"`.'
    ) from err
from loguru import logger

from storix.models import AzureFileProperties
from storix.sandbox import PathSandboxer, SandboxedPathHandler
from storix.security import SAS_EXPIRY_SECONDS, SAS_PERMISSIONS, Permissions
from storix.settings import get_settings
from storix.types import AsyncDataBuffer, EchoMode, StorixPath, StrPathLike

from ._base import BaseStorage

T = TypeVar("T")


class AzureDataLake(BaseStorage):
    """Async Azure Data Lake Storage Gen2 implementation - identical interface to sync version."""

    __slots__ = (
        "_current_path",
        "_filesystem",
        "_home",
        "_min_depth",
        "_sandbox",
        "_service_client",
        "account_name",
        "container_name",
        "initialpath",
    )

    _sandbox: PathSandboxer | None
    _service_client: AsyncDataLakeServiceClient
    _filesystem: AsyncFileSystemClient
    _home: StorixPath
    _current_path: StorixPath
    _min_depth: StorixPath

    def __init__(
        self,
        initialpath: StrPathLike | None = None,
        container_name: str | None = None,
        adlsg2_account_name: str | None = None,
        adlsg2_token: str | None = None,
        *,
        sandboxed: bool = True,
        sandbox_handler: type[PathSandboxer] = SandboxedPathHandler,
        allow_container_name_in_paths: bool | None = None,
    ) -> None:
        """Initialize Azure Data Lake Storage Gen2 client.

        Sets up connection to Azure Data Lake Storage Gen2 using the provided
        account and credentials. Creates or connects to the specified filesystem
        container and initializes path navigation.

        Args:
            initialpath: The starting directory path for storage operations.
                Default path is defined in application settings. Supports tilde (~)
                expansion for home directory references.
            container_name: Path to the initial container in ADLS Gen2.
                Defaults to value in settings.ADLSG2_INITIAL_CONTAINER.
            adlsg2_account_name: Azure Storage account name.
                Defaults to value in settings.ADLSG2_ACCOUNT_NAME.
            adlsg2_token: SAS/account-key token for authentication.
                Defaults to value in settings.ADLSG2_SAS.
            sandboxed: If True, restricts file system access to the initial path
                directory tree. When enabled, the initial path acts as a virtual
                root directory ("/").
            sandbox_handler: The implementation class for path sandboxing.
                Only used when sandboxed=True.
            allow_container_name_in_paths: Accept having the container name shown in
                any input path to any file operation, e.g., /raw/... or /processed/... .

        Raises:
            AssertionError: If account name or SAS token are not provided.

        """
        settings = get_settings()
        self.container_name = container_name or str(settings.ADLSG2_CONTAINER_NAME)
        self.account_name = adlsg2_account_name or settings.ADLSG2_ACCOUNT_NAME
        adlsg2_token = adlsg2_token or settings.ADLSG2_TOKEN
        self._allow_container_name_in_paths = (
            settings.ADLSG2_ALLOW_CONTAINER_NAME_IN_PATHS
            if allow_container_name_in_paths is None
            else allow_container_name_in_paths
        )

        if initialpath is None:
            initialpath = (
                get_settings().STORAGE_INITIAL_PATH_AZURE
                or settings.STORAGE_INITIAL_PATH
            )

        if initialpath == "~":
            initialpath = "/"

        assert self.account_name and adlsg2_token, (
            "ADLSg2 account name and authentication token are required"
        )

        self._service_client = self._get_service_client(self.account_name, adlsg2_token)
        self._filesystem = self._init_filesystem(
            self._service_client, str(self.container_name)
        )

        super().__init__(
            initialpath, sandboxed=sandboxed, sandbox_handler=sandbox_handler
        )

    def strip_container_name(self, path: StrPathLike) -> StorixPath:
        """Strip container name from a given path.

        By default an adlsg2 path is bound to a container, meaning if your container is
        raw, your root would be just `/` not `/raw`.

        This function help you accept paths with the container included in their parts.

        This could be useful if you need compatability logic for a function or so,
        between this and another filesystem that doesn't default to this behavior, such
        as `LocalFilesystem`.

        * If you want to have this behaviro fixed within your instance, see parameter
            `allow_container_name_in_paths`
             or export
            `ADLSG2_ALLOW_CONTAINER_NAME_IN_PATHS=true`

        Examples:
            * If your current filesystem container is `raw`, it would strip the `raw`
                 part so it does not mess up with later on operations:

            ```py
            source_dataset = "/raw/file/to/dataset"
            path = fs.strip_container_name(source_dataset)
            print(path)
            # /file/to/dataset
            ```

            * If your current filesystem is not `raw`, then this is a normal directory
                inside your current container:

            ```py
            source_dataset = "/raw/file/to/dataset"
            path = fs.strip_container_name(source_dataset)
            print(path)
            # /raw/file/to/dataset
            ```
        """
        p = super()._topath(path)

        container_idx = 1
        parts = p.parts

        with contextlib.suppress(IndexError):
            container_part = parts[container_idx]

            if container_part == self.container_name:
                stripped_parts = parts[:container_idx] + parts[container_idx + 1 :]
                return StorixPath(*stripped_parts)

        return p

    @override
    def _topath(self, path: StrPathLike | None) -> StorixPath:
        p = super()._topath(path)

        if not self._allow_container_name_in_paths:
            return p

        return self.strip_container_name(p)

    def _init_filesystem(
        self, client: AsyncDataLakeServiceClient, container_name: str
    ) -> AsyncFileSystemClient:
        return client.get_file_system_client(container_name)

    def _get_service_client(
        self, account_name: str, token: str
    ) -> AsyncDataLakeServiceClient:
        account_url = f"https://{account_name}.dfs.core.windows.net"
        return AsyncDataLakeServiceClient(account_url, credential=token)

    # TODO(mghali): convert the return type to dict[str, str] or Tree DS
    # so that its O(1) from the ui-side to access
    async def tree(
        self, path: StrPathLike | None = None, *, abs: bool = False
    ) -> list[StorixPath]:
        """Get a recursive listing of all files and directories.

        Args:
            path: The path to list. Defaults to current directory.
            abs: If True, return absolute paths.

        Returns:
            A list of Path objects for all files and directories.

        """
        path = self._topath(path)
        await self._ensure_exist(path)

        all = self._filesystem.get_paths(path=str(path), recursive=True)
        paths: list[StorixPath] = [self._topath(f.name) async for f in all]

        if self._sandbox:
            return [self._sandbox.to_virtual(p) for p in paths]

        return paths

    @overload
    async def ls(
        self,
        path: StrPathLike | None = None,
        *,
        abs: Literal[False] = False,
        all: bool = True,
    ) -> list[str]: ...
    @overload
    async def ls(
        self,
        path: StrPathLike | None = None,
        *,
        abs: Literal[True] = True,
        all: bool = True,
    ) -> list[StorixPath]: ...
    async def ls(
        self, path: StrPathLike | None = None, *, abs: bool = False, all: bool = True
    ) -> Sequence[StrPathLike]:
        """List all items at the given path as Path or str objects."""
        path = self._topath(path)
        await self._ensure_exist(path)

        items = self._filesystem.get_paths(path=str(path), recursive=False)
        paths: Iterable[StorixPath] = [self.home / f.name async for f in items]

        if not all:
            paths = self._filter_hidden(paths)

        if not abs:
            return [Path(p.name) for p in paths]

        return list(paths)

    async def mkdir(self, path: StrPathLike, *, parents: bool = False) -> None:
        """Create a directory at the given path."""
        path = self._topath(path)
        # TODO(mghalix): add parents logic
        await self._filesystem.create_directory(str(path))

    async def isdir(self, path: StrPathLike) -> bool:
        """Check if the given path is a directory."""
        stats = await self.stat(path)
        return stats.hdi_isfolder

    async def stat(self, path: StrPathLike) -> AzureFileProperties:
        """Return stat information for the given path."""
        path = self._topath(path)
        await self._ensure_exist(path)

        async with self._get_file_client(path) as fc:
            # determining whether an item is a file or a dir is currently not in the
            # azure sdk, but we follow this workaround
            # https://github.com/Azure/azure-sdk-for-python/issues/24814#issuecomment-1159280840
            props = await fc.get_file_properties()
            metadata = props.get("metadata") or {}

            return AzureFileProperties.model_validate(dict(**props, **metadata))

    async def isfile(self, path: StrPathLike) -> bool:
        """Return True if the path is a file."""
        stats = await self.stat(path)
        return not stats.hdi_isfolder

    # TODO(mghali): add a confirm override option
    async def mv(self, source: StrPathLike, destination: StrPathLike) -> None:
        """Move a file or directory to a new location."""
        source = self._topath(source)
        destination = self._topath(destination)

        await self._ensure_exist(source)

        if await self.isdir(source):
            raise NotImplementedError("mv is not yet supported for directories")

        data = await self.cat(source)
        dest: StorixPath = destination
        if await self.exists(dest) and await self.isdir(dest):
            dest /= source.name

        # TODO(mghali): add fallback or error on touch fail (ensuring no data loss by rm)
        await asyncio.gather(self.touch(dest, data), self.rm(source))

    async def cd(self, path: StrPathLike | None = None) -> Self:
        """Change to the given directory."""
        if path is None:
            path = self.home
        else:
            await self._ensure_exist(path)

        path = self._topath(path)

        if await self.isfile(path):
            raise ValueError(f"cd: not a directory: {path}")

        if self._sandbox:
            self._current_path = self._sandbox.to_virtual(path)
            return self

        self._current_path = path
        return self

    async def rm(self, path: StrPathLike) -> bool:
        """Delete an item at the given path. Returns True if successful."""
        path = self._topath(path)
        await self._ensure_exist(path)

        try:
            async with self._get_file_client(path) as f:
                await f.delete_file()
        except Exception as err:
            logger.error(f"rm: failed to remove '{path}': {err}")
            return False

        return True

    async def rmdir(self, path: StrPathLike, recursive: bool = False) -> bool:
        """Remove a directory at the given path."""
        path = self._topath(path)

        if await self.isfile(path):
            raise ValueError(f"rmdir: failed to remove '{path}': Not a directory")

        async with self._get_dir_client(path) as d:
            if not recursive and await self.ls(path):
                logger.error(
                    f"Error: {path} is a non-empty directory. Use recursive=True to "
                    "force remove non-empty directories."
                )
                return False

            await d.delete_directory()

        return True

    async def touch(self, path: StrPathLike, data: Any | None = None) -> bool:
        """Create a file at the given path, optionally writing data."""
        path = self._topath(path)

        async with self._get_file_client(path) as f:
            await f.create_file()

            if not data:
                return True

            from storix.utils import get_mimetype

            await f.upload_data(
                data,
                overwrite=True,
                content_settings=ContentSettings(content_type=get_mimetype(buf=data)),
            )

        return True

    async def echo(
        self,
        data: AsyncDataBuffer[AnyStr],
        path: StrPathLike,
        *,
        mode: EchoMode = "w",
        chunksize: int = DEFAULT_WRITE_CHUNKSIZE,
    ) -> bool:
        """Write (overwrite/append) data into a file."""
        path = self._topath(path)

        async with self._get_file_client(path) as f:
            from storix.constants import DEFAULT_MIMETYPE_DETECTION_PEEKSIZE
            from storix.utils import get_mimetype
            from storix.utils.streaming import normalize_data

            stream = normalize_data(data)

            offset = 0

            if mode == "w" or not await self.exists(path):
                await f.create_file()
                head = stream.read(DEFAULT_MIMETYPE_DETECTION_PEEKSIZE)
                if asyncio.iscoroutine(head):
                    head = await head
                content_type = get_mimetype(buf=head)
                length = len(head)
                await f.append_data(head, offset=offset, length=length)
                offset += length
            else:
                props = await f.get_file_properties()
                content_type = props.content_settings.content_type
                offset = props.size

            while True:
                chunk = stream.read(chunksize)
                if asyncio.iscoroutine(chunk):
                    chunk = await chunk

                if not chunk:
                    break

                length = len(chunk)
                await f.append_data(chunk, offset=offset, length=length)
                offset += length

            await f.flush_data(
                offset=offset,
                content_settings=ContentSettings(content_type=content_type),
            )

        return True

    async def cat(self, path: StrPathLike) -> bytes:
        """Read the contents of a file as bytes."""
        path = self._topath(path)
        await self._ensure_exist(path)

        if await self.isdir(path):
            raise ValueError(f"cat: {path}: Is a directory")

        blob: bytes
        async with self._get_file_client(path) as f:
            download = await f.download_file()
            blob = await download.readall()

        return blob

    async def exists(self, path: StrPathLike) -> bool:
        """Return True if the path exists."""
        path = self._topath(path)

        if str(path) == "/":
            return True

        try:
            async with self._get_file_client(path) as f:
                return await f.exists()
        except Exception:
            try:
                async with self._get_dir_client(path) as d:
                    return await d.exists()
            except Exception:
                return False

    async def cp(self, source: StrPathLike, destination: StrPathLike) -> None:
        """Copy a file or directory to a new location."""
        source = self._topath(source)
        destination = self._topath(destination)

        if await self.isfile(source):
            data = await self.cat(source)
            await self.touch(destination, data)
            return

        # TODO(mghali): copy tree
        raise NotImplementedError

    # TODO(mghalix): review / remove - mirror in sync provider
    async def du(
        self, path: StrPathLike | None = None, *, human_readable: bool = True
    ) -> Any:
        """Get disk usage for Azure storage - placeholder implementation."""
        # Azure Data Lake doesn't provide direct disk usage stats
        # This is a placeholder implementation
        path = self._topath(path)
        await self._ensure_exist(path)

        if await self.isfile(path):
            props = await self.stat(path)
            # Return file size if available
            return getattr(props, "size", 0)

        # For directories, we'd need to traverse all files
        # This is a simplified implementation
        total_size = 0
        files = await self.tree(path)
        for file_path in files:
            if await self.isfile(file_path):
                props = await self.stat(file_path)
                total_size += getattr(props, "size", 0)

        return total_size

    async def close(self) -> None:
        """Close the Azure Data Lake client and filesystem."""
        await self._filesystem.close()
        await self._service_client.close()

    @asynccontextmanager
    async def _get_file_client(
        self, filepath: StrPathLike
    ) -> AsyncIterator[AsyncDataLakeFileClient]:
        filepath = self._topath(filepath)
        async with self._filesystem.get_file_client(str(filepath)) as client:
            yield client

    @asynccontextmanager
    async def _get_dir_client(
        self, dirpath: StrPathLike
    ) -> AsyncIterator[AsyncDataLakeDirectoryClient]:
        dirpath = self._topath(dirpath)
        async with self._filesystem.get_directory_client(str(dirpath)) as client:
            yield client

    async def make_url(
        self, path: StrPathLike, *, astype: Literal["data_url", "sas"] = "sas"
    ) -> str:
        """Generate a url for a path."""
        if astype == "sas":
            return await self._generate_sas_url(
                path, expires_in=SAS_EXPIRY_SECONDS, permissions=SAS_PERMISSIONS
            )
        return await super().make_url(path, astype=astype)

    async def _generate_sas_url(
        self,
        path: StrPathLike,
        *,
        expires_in: int = 3600,
        permissions: frozenset[Permissions] = frozenset({Permissions.READ}),
    ) -> str:
        from azure.storage.filedatalake import FileSasPermissions, generate_file_sas

        from storix.utils import craft_adlsg2_url_sas

        path = self._topath(path)
        await self._ensure_exist(path)

        if await self.isdir(path):
            raise ValueError("cannot generate a sas token for a directory")

        fs = self._filesystem
        account_name: str = str(fs.account_name)
        container: str = str(fs.file_system_name)
        credential: str = str(fs.credential.account_key)

        expiry = dt.datetime.now(dt.UTC) + dt.timedelta(seconds=expires_in)
        file_permissions = FileSasPermissions(
            **dict.fromkeys(map(str, permissions), True)
        )

        directory: str = str(path.parent).lstrip("/")
        filename: str = path.parts[-1]

        # pure local crypto op no i/o
        token = generate_file_sas(
            account_name=account_name,
            file_system_name=container,
            credential=credential,
            directory_name=directory,
            file_name=filename,
            permission=file_permissions,
            expiry=expiry,
        )

        return craft_adlsg2_url_sas(
            account_name=account_name,
            container=container,
            directory=directory,
            filename=filename,
            sas_token=token,
        )
