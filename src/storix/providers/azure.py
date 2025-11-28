import contextlib
import datetime as dt

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from types import TracebackType
from typing import Any, AnyStr, Literal, Self, overload, override

from storix.constants import DEFAULT_WRITE_CHUNKSIZE
from storix.core.tree import Tree
from storix.types import StorixPath


try:
    from azure.storage.blob import ContentSettings
    from azure.storage.filedatalake import (
        DataLakeDirectoryClient,
        DataLakeFileClient,
        DataLakeServiceClient,
        FileSystemClient,
    )
except ImportError as err:
    msg = 'azure backend not installed. Install it by running `uv add storix[azure]`.'
    raise ImportError(msg) from err

from loguru import logger

from storix.models import AzureFileProperties
from storix.sandbox import PathSandboxer, SandboxedPathHandler
from storix.security import SAS_EXPIRY_SECONDS, SAS_PERMISSIONS, Permissions
from storix.settings import get_settings
from storix.types import DataBuffer, EchoMode, StrPathLike

from ._base import BaseStorage


# Expose a module-level settings object for tests that patch
settings = get_settings()


class AzureDataLake(BaseStorage):
    """Azure Data Lake Storage Gen2 implementation."""

    __slots__ = (
        '_current_path',
        '_filesystem',
        '_home',
        '_min_depth',
        '_sandbox',
        '_service_client',
        'account_name',
        'container_name',
        'initialpath',
    )

    _sandbox: PathSandboxer | None
    _service_client: DataLakeServiceClient
    _filesystem: FileSystemClient
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
        allow_container_name_in_paths: bool = False,
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
        cfg = settings
        self.container_name = container_name or str(cfg.ADLSG2_CONTAINER_NAME)
        self.account_name = adlsg2_account_name or cfg.ADLSG2_ACCOUNT_NAME
        adlsg2_token = adlsg2_token or cfg.ADLSG2_TOKEN
        self._allow_container_name_in_paths = (
            allow_container_name_in_paths or cfg.ADLSG2_ALLOW_CONTAINER_NAME_IN_PATHS
        )

        if initialpath is None:
            initialpath = cfg.STORAGE_INITIAL_PATH_AZURE or cfg.STORAGE_INITIAL_PATH

        if initialpath == '~':
            initialpath = '/'

        self.initialpath = initialpath
        assert self.account_name and adlsg2_token, (
            'ADLSg2 account name and authentication token are required'
        )

        self._service_client = self._get_service_client(self.account_name, adlsg2_token)
        self._filesystem = self._init_filesystem(
            self._service_client, str(self.container_name)
        )

        super().__init__(
            initialpath, sandboxed=sandboxed, sandbox_handler=sandbox_handler
        )

    def _init_filesystem(
        self, client: DataLakeServiceClient, container_name: str
    ) -> FileSystemClient:
        return client.get_file_system_client(container_name)

    def _get_service_client(
        self, account_name: str, token: str
    ) -> DataLakeServiceClient:
        account_url = f'https://{account_name}.dfs.core.windows.net'
        return DataLakeServiceClient(account_url, credential=token)

    # TODO: convert the return type to dict[str, str] or Tree DS
    # so that its O(1) from the ui-side to access
    def tree(self, path: StrPathLike | None = None, *, abs: bool = False) -> Tree:
        """Return a tree view of files and directories starting at path."""
        path = self._topath(path)
        self._ensure_exist(path)

        all = self._filesystem.get_paths(path=str(path), recursive=True)
        paths: list[StorixPath] = [self._topath(f.name) for f in all]

        it = (
            paths if not self._sandbox else (self._sandbox.to_virtual(p) for p in paths)
        )
        return Tree.from_iterable(it)
        # return Tree(
        #     root=path,
        #     dir_iterator=self.iterdir,
        #     dir_checker=self.isdir,
        #     file_checker=self.isfile,
        # )

    def iterdir(self, dir: StrPathLike | None = None) -> Iterator[StorixPath]:
        dir = self._topath(dir) or self.pwd()
        items = self.ls(dir, abs=True)

        # if self._sandbox:
        #     return (self._sandbox.to_virtual(p) for p in items)

        return iter(items)

    @override
    def _topath(self, path: StrPathLike | None) -> StorixPath:
        p = super()._topath(path)

        if not self._allow_container_name_in_paths:
            return p

        container_idx = 1
        parts = p.parts

        with contextlib.suppress(IndexError):
            container_part = parts[container_idx]

            if container_part == self.container_name:
                stripped_parts = parts[:container_idx] + parts[container_idx + 1 :]
                return StorixPath(*stripped_parts)

        return p

    @overload
    def ls(
        self,
        path: StrPathLike | None = None,
        *,
        abs: Literal[False] = False,
        all: bool = True,
    ) -> list[str]: ...
    @overload
    def ls(
        self, path: StrPathLike | None = None, *, abs: Literal[True], all: bool = True
    ) -> list[StorixPath]: ...
    def ls(
        self, path: StrPathLike | None = None, *, abs: bool = False, all: bool = True
    ) -> Sequence[StrPathLike]:
        """List all items at the given path as Path or str objects."""
        path = self._topath(path)
        self._ensure_exist(path)

        items = self._filesystem.get_paths(path=str(path), recursive=False)
        paths = [self.home / f.name for f in items]

        if not all:
            paths = list(self._filter_hidden(paths))

        if not abs:
            return [p.name for p in paths]

        return paths

    def mkdir(self, path: StrPathLike, *, parents: bool = False) -> None:
        """Create a directory at the given path."""
        path = self._topath(path)
        # TODO: add parents logic
        self._filesystem.create_directory(str(path))

    def isdir(self, path: StrPathLike) -> bool:
        """Check if the given path is a directory."""
        stats = self.stat(path)
        return stats.hdi_isfolder

    def stat(self, path: StrPathLike) -> AzureFileProperties:
        """Return stat information for the given path."""
        path = self._topath(path)
        self._ensure_exist(path)

        with self._get_file_client(path) as fc:
            # determining whether an item is a file or a dir is currently not in the
            # azure sdk, but we follow this workaround
            # https://github.com/Azure/azure-sdk-for-python/issues/24814#issuecomment-1159280840
            props = fc.get_file_properties()
            metadata = props.get('metadata') or {}

            return AzureFileProperties.model_validate(dict(**props, **metadata))

    def isfile(self, path: StrPathLike) -> bool:
        """Check if the given path is a file."""
        stats = self.stat(path)
        return not stats.hdi_isfolder

    # TODO: add a confirm override option
    def mv(self, source: StrPathLike, destination: StrPathLike) -> None:
        """Move a file or directory to a new location."""
        source = self._topath(source)
        destination = self._topath(destination)

        self._ensure_exist(source)

        if self.isdir(source):
            msg = 'mv is not yet supported for directories'
            raise NotImplementedError(msg)

        data = self.cat(source)
        dest: StorixPath = destination
        if self.exists(dest) and self.isdir(dest):
            dest /= source.name

        # TODO: add fallback or error on touch fail
        # (ensuring no data loss by rm)
        self.touch(dest, data)
        self.rm(source)

    def cd(self, path: StrPathLike | None = None) -> Self:
        """Change the current working directory."""
        if path is None:
            path = self.home
        else:
            self._ensure_exist(path)

        path = self._topath(path)

        if self.isfile(path):
            msg = f'cd: not a directory: {path}'
            raise ValueError(msg)

        if self._sandbox:
            self._current_path = self._sandbox.to_virtual(path)
            return self

        self._current_path = path
        return self

    def rm(self, path: StrPathLike) -> bool:
        """Remove a file at the given path."""
        path = self._topath(path)

        if not self.exists(path):
            logger.error(f"rm: cannot remove '{path}': No such file or directory")
            return False

        if not self.isfile(path):
            logger.error(f"rm: cannot remove '{path!s}': Is a directory")
            return False

        try:
            with self._get_file_client(path) as f:
                f.delete_file()
        except Exception as err:
            logger.error(f"rm: failed to remove '{path}': {err}")
            return False

        return True

    def rmdir(self, path: StrPathLike, recursive: bool = False) -> bool:
        """Remove a directory at the given path."""
        path = self._topath(path)

        if self.isfile(path):
            msg = f"rmdir: failed to remove '{path}': Not a directory"
            raise ValueError(msg)

        with self._get_dir_client(path) as d:
            if not recursive and self.ls(path):
                logger.error(
                    f'Error: {path} is a non-empty directory. Use recursive=True to '
                    'force remove non-empty directories.'
                )
                return False

            d.delete_directory()

        return True

    def touch(
        self,
        path: StrPathLike,
        data: Any | None = None,
        *,
        content_type: str | None = None,
    ) -> bool:
        """Create a file at the given path, optionally writing data.

        Args:
            path: Target file path.
            data: Optional data blob to write entirely in one go.
            content_type: Explicit content type override. If omitted we try:
                1) Guess from path extension
                2) Sniff from the data buffer (libmagic)
                3) Fallback to application/octet-stream
        """
        path = self._topath(path)

        with self._get_file_client(path) as f:
            f.create_file()

            if not data:
                return True
            from storix.utils import detect_mimetype

            inferred = content_type or detect_mimetype(buf=data, path=path)
            f.upload_data(
                data,
                overwrite=True,
                content_settings=ContentSettings(content_type=inferred),
            )

        return True

    def echo(
        self,
        data: DataBuffer[AnyStr],
        path: StrPathLike,
        *,
        mode: EchoMode = 'w',
        chunksize: int = DEFAULT_WRITE_CHUNKSIZE,
        content_type: str | None = None,
    ) -> bool:
        """Write (overwrite/append) data into a file.

        Args:
            data: Buffer / iterable of bytes-like chunks.
            path: Destination file path.
            mode: "w" to create/overwrite, "a" to append.
            chunksize: Size of stream chunks for append logic.
            content_type: Explicit content type override. If None and mode == "w" we
                will:
                1) Guess based on path extension
                2) Peek first bytes and sniff
                3) Fallback to application/octet-stream
                For append mode we preserve existing content_type unless explicit
                override is provided.
        """
        path = self._topath(path)

        with self._get_file_client(path) as f:
            from storix.constants import DEFAULT_MIMETYPE_DETECTION_PEEKSIZE
            from storix.utils import detect_mimetype
            from storix.utils.streaming import normalize_data

            stream = normalize_data(data)

            offset = 0

            ct: str | None

            if mode == 'w' or not self.exists(path):
                f.create_file()
                head = stream.read(DEFAULT_MIMETYPE_DETECTION_PEEKSIZE)
                # Determine new content type unless explicitly overridden
                ct = content_type or detect_mimetype(buf=head, path=path)
                length = len(head)
                f.append_data(head, offset=offset, length=length)
                offset += length
            else:
                props = f.get_file_properties()
                existing_ct = props.content_settings.content_type
                ct = content_type or existing_ct
                offset = props.size

            while chunk := stream.read(chunksize):
                length = len(chunk)
                f.append_data(chunk, offset=offset, length=length)
                offset += length

            f.flush_data(
                offset=offset,
                content_settings=ContentSettings(content_type=ct),
            )

        return True

    def cat(self, path: StrPathLike) -> bytes:
        """Read the contents of a file as bytes."""
        path = self._topath(path)
        self._ensure_exist(path)

        if self.isdir(path):
            msg = f'cat: {path}: Is a directory'
            raise ValueError(msg)

        blob: bytes
        with self._get_file_client(path) as f:
            download = f.download_file()
            blob = download.readall()

        return blob

    def exists(self, path: StrPathLike) -> bool:
        """Check if the given path exists."""
        path = self._topath(path)

        if str(path) == '/':
            return True

        try:
            with self._get_file_client(path) as f:
                return f.exists()
        except Exception:
            try:
                with self._get_dir_client(path) as d:
                    return d.exists()
            except Exception:
                return False

    def cp(self, source: StrPathLike, destination: StrPathLike) -> None:
        """Copy a file or directory to a new location."""
        source = self._topath(source)
        destination = self._topath(destination)

        if self.isfile(source):
            data = self.cat(source)
            self.touch(destination, data)
            return

        # TODO: copy tree
        raise NotImplementedError

    def du(
        self, path: StrPathLike | None = None, *, human_readable: bool = True
    ) -> Any:
        """Return disk usage statistics for the given path."""
        raise NotImplementedError

    def close(self) -> None:
        """Close the Azure Data Lake storage client."""
        self._filesystem.close()
        self._service_client.close()

    @contextmanager
    def _get_file_client(self, filepath: StrPathLike) -> Iterator[DataLakeFileClient]:
        filepath = self._topath(filepath)
        with self._filesystem.get_file_client(str(filepath)) as client:
            yield client

    @contextmanager
    def _get_dir_client(
        self, dirpath: StrPathLike
    ) -> Iterator[DataLakeDirectoryClient]:
        dirpath = self._topath(dirpath)
        with self._filesystem.get_directory_client(str(dirpath)) as client:
            yield client

    def make_url(
        self, path: StrPathLike, *, astype: Literal['data_url', 'sas'] = 'sas'
    ) -> str:
        """Generate a url for a path."""
        if astype == 'sas':
            return self._generate_sas_url(
                path, expires_in=SAS_EXPIRY_SECONDS, permissions=SAS_PERMISSIONS
            )
        return super().make_url(path, astype=astype)

    def _generate_sas_url(
        self,
        path: StrPathLike,
        *,
        expires_in: int = 3600,
        permissions: frozenset[Permissions] = frozenset({Permissions.READ}),
    ) -> str:
        from azure.storage.filedatalake import FileSasPermissions, generate_file_sas

        from storix.utils import craft_adlsg2_url_sas

        path = self._topath(path)
        self._ensure_exist(path)

        if self.isdir(path):
            msg = 'cannot generate a sas token for a directory'
            raise ValueError(msg)

        fs = self._filesystem
        account_name: str = str(fs.account_name)
        container: str = str(fs.file_system_name)
        credential: str = str(fs.credential.account_key)

        expiry = dt.datetime.now(dt.UTC) + dt.timedelta(seconds=expires_in)
        file_permissions = FileSasPermissions(
            **dict.fromkeys(map(str, permissions), True)
        )

        directory: str = str(path.parent).lstrip('/')
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

    def __enter__(self) -> Self:
        """Enter the runtime context related to this object."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException],
        exc_value: BaseException,
        traceback: TracebackType,
    ) -> None:
        """Exit the runtime context and close resources."""
        self.close()
