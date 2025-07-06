import asyncio
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from datetime import datetime as dt
from pathlib import Path
from types import TracebackType
from typing import Any, Literal, TypeVar, overload

import magic
from azure.storage.blob import ContentSettings
from azure.storage.filedatalake.aio import (
    DataLakeDirectoryClient as AsyncDataLakeDirectoryClient,
)
from azure.storage.filedatalake.aio import DataLakeFileClient as AsyncDataLakeFileClient
from azure.storage.filedatalake.aio import (
    DataLakeServiceClient as AsyncDataLakeServiceClient,
)
from azure.storage.filedatalake.aio import FileSystemClient as AsyncFileSystemClient
from loguru import logger
from pydantic import BaseModel
from typing_extensions import Self

from storix.sandbox import PathSandboxable, SandboxedPathHandler
from storix.settings import settings
from storix.typing import PathLike

from ._base import BaseStorage

T = TypeVar("T")


class FileProperties(BaseModel):
    """Properties for Azure Data Lake files and directories."""

    name: str
    hdi_isfolder: bool = False
    last_modified: dt
    creation_time: dt

    model_config = {"from_attributes": True}


class AzureDataLake(BaseStorage):
    """Async Azure Data Lake Storage Gen2 implementation - identical interface to sync version."""

    __slots__ = (
        "__filesystem",
        "__service_client",
        "_current_path",
        "_home",
        "_min_depth",
        "_sandbox",
    )

    _sandbox: PathSandboxable | None
    __service_client: AsyncDataLakeServiceClient
    __filesystem: AsyncFileSystemClient
    _home: Path
    _current_path: Path
    _min_depth: Path

    def __init__(
        self,
        initialpath: PathLike | None = None,
        container_name: str = str(settings.ADLSG2_CONTAINER_NAME),
        adlsg2_account_name: str | None = settings.ADLSG2_ACCOUNT_NAME,
        adlsg2_token: str | None = settings.ADLSG2_TOKEN,
        *,
        sandboxed: bool = True,
        sandbox_handler: type[PathSandboxable] = SandboxedPathHandler,
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

        Raises:
            AssertionError: If account name or SAS token are not provided.

        """
        if initialpath is None:
            initialpath = (
                settings.STORAGE_INITIAL_PATH_AZURE or settings.STORAGE_INITIAL_PATH
            )

        if initialpath == "~":
            initialpath = "/"

        assert adlsg2_account_name and adlsg2_token, (
            "ADLSg2 account name and authentication token are required"
        )

        self.__service_client = self._get_service_client(
            adlsg2_account_name, adlsg2_token
        )
        self.__filesystem = self._init_filesystem(
            self.__service_client, str(container_name)
        )

        super().__init__(
            initialpath, sandboxed=sandboxed, sandbox_handler=sandbox_handler
        )

    def _init_filesystem(
        self, client: AsyncDataLakeServiceClient, container_name: str
    ) -> AsyncFileSystemClient:
        return client.get_file_system_client(
            container_name
        ) or client.create_file_system(container_name)

    def _get_service_client(
        self, account_name: str, token: str
    ) -> AsyncDataLakeServiceClient:
        account_url = f"https://{account_name}.dfs.core.windows.net"
        return AsyncDataLakeServiceClient(account_url, credential=token)

    # TODO(mghali): convert the return type to dict[str, str] or Tree DS
    # so that its O(1) from the ui-side to access
    async def tree(
        self, path: PathLike | None = None, *, abs: bool = False
    ) -> list[Path]:
        """Get a recursive listing of all files and directories.

        Args:
            path: The path to list. Defaults to current directory.
            abs: If True, return absolute paths.

        Returns:
            A list of Path objects for all files and directories.

        """
        path = self._topath(path)
        await self._ensure_exist(path)

        all = self.__filesystem.get_paths(path=str(path), recursive=True)
        paths: list[Path] = [self._topath(f.name) async for f in all]

        if self._sandbox:
            return [self._sandbox.to_virtual(p) for p in paths]

        return paths

    @overload
    async def ls(
        self,
        path: PathLike | None = None,
        *,
        abs: Literal[False] = False,
        all: bool = True,
    ) -> list[str]: ...
    @overload
    async def ls(
        self,
        path: PathLike | None = None,
        *,
        abs: Literal[True] = True,
        all: bool = True,
    ) -> list[Path]: ...
    async def ls(
        self, path: PathLike | None = None, *, abs: bool = False, all: bool = True
    ) -> Sequence[Path | str]:
        """List all items at the given path as Path or str objects."""
        path = self._topath(path)
        await self._ensure_exist(path)

        items = self.__filesystem.get_paths(path=str(path), recursive=False)
        paths: Sequence[Path] = [self.home / f.name async for f in items]

        if not all:
            paths = self._filter_hidden(paths)

        if not abs:
            return [Path(p.name) for p in paths]

        return paths

    async def mkdir(self, path: PathLike, *, parents: bool = False) -> None:
        """Create a directory at the given path."""
        path = self._topath(path)
        # TODO(mghalix): add parents logic
        await self.__filesystem.create_directory(str(path))

    async def isdir(self, path: PathLike) -> bool:
        """Check if the given path is a directory."""
        stats = await self.stat(path)
        return stats.hdi_isfolder

    async def stat(self, path: PathLike) -> FileProperties:
        """Return stat information for the given path."""
        path = self._topath(path)
        await self._ensure_exist(path)

        async with self._get_file_client(path) as fc:
            # determining whether an item is a file or a dir is currently not in the
            # azure sdk, but we follow this workaround
            # https://github.com/Azure/azure-sdk-for-python/issues/24814#issuecomment-1159280840
            props = await fc.get_file_properties()
            metadata = props.get("metadata") or {}

            return FileProperties.model_validate(dict(**props, **metadata))

    async def isfile(self, path: PathLike) -> bool:
        """Return True if the path is a file."""
        stats = await self.stat(path)
        return not stats.hdi_isfolder

    # TODO(mghali): add a confirm override option
    async def mv(self, source: PathLike, destination: PathLike) -> None:
        """Move a file or directory to a new location."""
        source = self._topath(source)
        destination = self._topath(destination)

        await self._ensure_exist(source)

        if await self.isdir(source):
            raise NotImplementedError("mv is not yet supported for directories")

        data = await self.cat(source)
        dest: Path = destination
        if await self.exists(dest) and await self.isdir(dest):
            dest /= source.name

        # TODO(mghali): add fallback or error on touch fail (ensuring no data loss by rm)
        await asyncio.gather(self.touch(dest, data), self.rm(source))

    async def cd(self, path: PathLike | None = None) -> Self:
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

    async def rm(self, path: PathLike) -> bool:
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

    async def rmdir(self, path: PathLike, recursive: bool = False) -> bool:
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

    async def touch(self, path: PathLike | None, data: Any | None = None) -> bool:
        """Create a file at the given path, optionally writing data."""
        path = self._topath(path)

        async with self._get_file_client(path) as f:
            await f.create_file()

            if not data:
                return True

            content_type = magic.from_buffer(data, mime=True)
            await f.upload_data(
                data,
                overwrite=True,
                content_settings=ContentSettings(content_type=content_type),
            )

        return True

    async def cat(self, path: PathLike) -> bytes:
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

    async def exists(self, path: PathLike) -> bool:
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

    async def cp(self, source: PathLike, destination: PathLike) -> None:
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
        self, path: PathLike | None = None, *, human_readable: bool = True
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
        await self.__filesystem.close()
        await self.__service_client.close()

    @asynccontextmanager
    async def _get_file_client(
        self, filepath: PathLike
    ) -> AsyncIterator[AsyncDataLakeFileClient]:
        filepath = self._topath(filepath)
        async with self.__filesystem.get_file_client(str(filepath)) as client:
            yield client

    @asynccontextmanager
    async def _get_dir_client(
        self, dirpath: PathLike
    ) -> AsyncIterator[AsyncDataLakeDirectoryClient]:
        dirpath = self._topath(dirpath)
        async with self.__filesystem.get_directory_client(str(dirpath)) as client:
            yield client

    async def __aenter__(self) -> Self:
        """Enter the async context manager."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException],
        exc_value: BaseException,
        traceback: TracebackType,
    ) -> None:
        """Exit the async context manager."""
        await self.close()
