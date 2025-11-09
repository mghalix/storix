import asyncio
import os
import shutil
from collections.abc import Sequence
from typing import Any, AnyStr, Literal, Self, overload

import aiofiles as aiof
import aiofiles.os as aioos
from loguru import logger

from storix.constants import DEFAULT_WRITE_CHUNKSIZE
from storix.sandbox import PathSandboxer, SandboxedPathHandler
from storix.types import AsyncDataBuffer, EchoMode, StorixPath, StrPathLike

from ._base import BaseStorage


class LocalFilesystem(BaseStorage):
    """Async LocalFilesystem - (identical interface to sync version)."""

    def __init__(
        self,
        initialpath: StrPathLike | None = None,
        *,
        sandboxed: bool = True,
        sandbox_handler: type[PathSandboxer] = SandboxedPathHandler,
    ) -> None:
        """Initialize the async local storage adapter.

        Sets up a local filesystem storage implementation with optional
        path sandboxing. It expands and normalizes the provided path, creates the
        directory if necessary, and configures path translation for sandboxed mode.

        Args:
            initialpath: The starting directory path for storage operations.
                Default path is defined in application settings. Supports tilde (~)
                expansion for home directory references.
            sandboxed: If True, restricts file system access to the initial path
                directory tree. When enabled, the initial path acts as a virtual
                root directory ("/").
            sandbox_handler: The implementation class for path sandboxing.
                Only used when sandboxed=True.

        Raises:
            OSError: If directory creation fails due to permissions or other
                filesystem errors.

        """
        if initialpath is None:
            from storix.settings import get_settings

            settings = get_settings()

            initialpath = (
                settings.STORAGE_INITIAL_PATH_LOCAL or settings.STORAGE_INITIAL_PATH
            )

        from pathlib import Path

        initialpath = StorixPath(
            str(initialpath).replace("~", str(Path.home()))
        ).resolve()
        from pathlib import Path

        if not initialpath.is_absolute():
            initialpath = Path.home() / initialpath

        if not Path(initialpath).exists():
            logger.info(f"Creating initial path: '{initialpath}'...")
            os.makedirs(initialpath)

        super().__init__(
            initialpath, sandboxed=sandboxed, sandbox_handler=sandbox_handler
        )

    async def exists(self, path: StrPathLike) -> bool:
        """Check if the given path exists."""
        path = self._topath(path)
        return await aioos.path.exists(path)

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
        """List all items at the given path.

        When abs=True return concrete pathlib.Path objects for test compatibility.
        """
        from pathlib import Path

        path = self._topath(path)
        entries = await aioos.listdir(path)

        if not all:
            entries = list(self._filter_hidden(entries))

        if abs:
            return [Path(path) / entry for entry in entries]

        return entries

    async def isdir(self, path: StrPathLike) -> bool:
        """Return True if the path is a directory."""
        path = self._topath(path)
        return await aioos.path.isdir(path)

    async def isfile(self, path: StrPathLike) -> bool:
        """Return True if the path is a file."""
        path = self._topath(path)
        return await aioos.path.isfile(path)

    async def mkdir(self, path: StrPathLike, *, parents: bool = False) -> None:
        """Create a directory at the given path."""
        path = self._topath(path)
        coro = aioos.makedirs(path, exist_ok=True) if parents else aioos.mkdir(path)
        await coro

    async def touch(self, path: StrPathLike, data: Any | None = None) -> bool:
        """Create a file at the given path with optional data."""
        path = self._topath(path)

        if not await self.exists(path.parent):
            logger.error(f"touch: cannot touch '{path!s}': No such file or directory")
            return False

        data_bytes: bytes | None = data.encode() if isinstance(data, str) else data

        try:
            async with aiof.open(path, "wb") as f:
                await f.write(data_bytes or b"")
            return True
        except Exception as err:
            logger.error(f"touch: failed to write file '{path!s}': {err}")
            return False

    async def rmdir(self, path: StrPathLike, recursive: bool = False) -> bool:
        """Delete a directory at the given path. Returns True if successful."""
        path = self._topath(path)

        if not await self.exists(path):
            logger.error(
                f"rmdir: failed to remove '{path!s}': No such file or directory"
            )
            return False

        if not await self.isdir(path):
            logger.error(f"rmdir: failed to remove '{path!s}': Not a directory")
            return False

        try:
            # aiofiles doesn't have removedirs, so fall back to sync method
            if recursive:
                await asyncio.to_thread(shutil.rmtree, path)
            else:
                await aioos.rmdir(path)

            return True
        except Exception as err:
            logger.error(f"rmdir: failed to remove '{path!s}': {err}")
            return False

    async def cat(self, path: StrPathLike) -> bytes:
        """Read the contents of a file."""
        path = self._topath(path)
        await self._ensure_exist(path)

        async with aiof.open(path, "rb") as f:
            return await f.read()

    async def rm(self, path: StrPathLike) -> bool:
        """Delete an item at the given path. Returns True if successful."""
        path = self._topath(path)

        if not await self.exists(path):
            logger.error(f"rm: cannot remove '{path}': No such file or directory")
            return False

        if not await self.isfile(path):
            logger.error(f"rm: cannot remove '{path!s}': Is a directory")
            return False
        try:
            await aioos.remove(path)
            return True
        except FileNotFoundError:
            logger.error(f"File not found: {path}")
            return False
        except PermissionError:
            logger.error(f"Permission denied: {path}")
            return False
        except Exception as err:
            logger.error(f"Failed to remove {path}: {err}")
            return False

    async def mv(self, source: StrPathLike, destination: StrPathLike) -> None:
        """Move an item from source to destination."""
        source = self._topath(source)
        await self._ensure_exist(source)

        destination = self._topath(destination)

        # TODO(mghalix): test below or switch to above
        await aioos.rename(source, destination)

    async def cp(self, source: StrPathLike, destination: StrPathLike) -> None:
        """Copy an item from source to destination."""
        source = self._topath(source)
        destination = self._topath(destination)

        # if source.is_dir():
        #     await asyncio.to_thread(shutil.copytree, *(source, destination))
        # else:
        #     await asyncio.to_thread(shutil.copy2, *(source, destination))

        # TODO(mghalix): test below or switch to above
        if await self.isdir(source):
            await asyncio.to_thread(shutil.copytree, str(source), str(destination))
        else:
            async with (
                aiof.open(source, "rb") as src,
                aiof.open(destination, "wb") as dst,
            ):
                await dst.write(await src.read())

    # TODO(mghalix): revise from here to bottom
    async def tree(
        self, path: StrPathLike | None = None, *, abs: bool = False
    ) -> list[StorixPath]:
        """List all items recursively at the given path."""
        path = self._topath(path)
        entries = []
        for root, _, files in await asyncio.to_thread(os.walk, path):
            for file in files:
                entries.append(StorixPath(root) / file)
        if abs:
            return entries
        return [entry.relative_to(path) for entry in entries]

    async def stat(self, path: StrPathLike) -> Any:
        """Get file/directory statistics using aiofiles."""
        # path = self._topath(path)
        # await self._ensure_exist(path)
        #
        # return await aioos.stat(path)
        raise NotImplementedError

    async def du(
        self, path: StrPathLike | None = None, *, human_readable: bool = True
    ) -> Any:
        """Get disk usage for the given path."""
        path = self._topath(path)
        await self._ensure_exist(path)

        import os

        size: float
        if await self.isfile(path):
            stat_result = await asyncio.to_thread(os.stat, path)
            size = stat_result.st_size
        else:
            # For directories, sum up all file sizes
            size = 0
            for root, _dirs, files in await asyncio.to_thread(os.walk, path):
                for file in files:
                    file_path = os.path.join(root, file)
                    try:
                        stat_result = await asyncio.to_thread(os.stat, file_path)
                        size += stat_result.st_size
                    except OSError:
                        # Skip files we can't stat
                        continue

        if human_readable:
            # Simple human readable format
            for unit in ["B", "KB", "MB", "GB", "TB"]:
                if size < 1024.0:
                    return f"{size:.1f}{unit}"
                size /= 1024.0
            return f"{size:.1f}PB"

        return size

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

        if not await self.exists(path.parent):
            logger.error(
                f"echo: cannot echo into '{path!s}': No such file or directory"
            )
            return False

        from storix.utils.streaming import normalize_data

        stream = normalize_data(data)
        try:
            async with aiof.open(path, mode + "b") as f:
                while True:
                    chunk = stream.read(chunksize)

                    if asyncio.iscoroutine(chunk):
                        chunk = await chunk

                    if not chunk:
                        break

                    await f.write(chunk)

        except Exception as err:
            logger.error(f"echo: failed to write into file '{path!s}': {err}")
            return False

        return True
