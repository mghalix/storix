from __future__ import annotations

import os
import shutil

from collections.abc import Iterable, Iterator, Sequence
from pathlib import Path
from typing import (
    Any,
    AnyStr,
    Literal,
    Self,
    overload,
)

from loguru import logger

from storix.constants import DEFAULT_WRITE_CHUNKSIZE
from storix.core import Finder
from storix.core.tree import Tree
from storix.sandbox import PathSandboxer, SandboxedPathHandler
from storix.settings import get_settings
from storix.types import DataBuffer, EchoMode, StorixPath, StrPathLike

from ._base import BaseStorage


class LocalFilesystem(BaseStorage):
    """Local filesystem storage provider implementation."""

    def __init__(
        self,
        initialpath: StrPathLike | None = None,
        *,
        sandboxed: bool = True,
        sandbox_handler: type[PathSandboxer] = SandboxedPathHandler,
    ) -> None:
        """Initialize the local storage adapter.

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
            settings = get_settings()

            initialpath = (
                settings.STORAGE_INITIAL_PATH_LOCAL or settings.STORAGE_INITIAL_PATH
            )

        initialpath = Path(str(initialpath).replace('~', str(Path.home()))).resolve()

        if not initialpath.is_absolute():
            initialpath = Path.home() / initialpath

        if not Path.exists(initialpath):
            logger.info(f"Creating initial path: '{initialpath}'...")
            os.makedirs(initialpath)

        super().__init__(
            initialpath, sandboxed=sandboxed, sandbox_handler=sandbox_handler
        )

    def exists(self, path: StrPathLike) -> bool:
        """Check if the given path exists."""
        path = self._topath(path)
        return Path(path).exists()

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
        self,
        path: StrPathLike | None = None,
        *,
        abs: bool = False,
        all: bool = True,
    ) -> Sequence[StrPathLike] | Iterator[StrPathLike]:
        """List files and directories at the given path."""
        path = self._topath(path)
        self._ensure_exist(path)

        lst: Iterable[Path] = Path(path).iterdir()

        if not all:
            lst = self._filter_hidden(lst)

        if abs:
            return list(lst)

        return [file.name for file in lst]

    def isdir(self, path: StrPathLike) -> bool:
        """Check if the given path is a directory."""
        return Path(self._topath(path)).is_dir()

    def isfile(self, path: StrPathLike) -> bool:
        """Check if the given path is a file."""
        return Path(self._topath(path)).is_file()

    def mkdir(self, path: StrPathLike, *, parents: bool = False) -> None:
        """Create a directory at the given path."""
        path = self._topath(path)
        Path(path).mkdir(exist_ok=True, parents=parents)

    def touch(self, path: StrPathLike, data: Any | None = None) -> bool:
        """Create a file at the given path, optionally writing data."""
        path = self._topath(path)

        if not self.exists(path.parent):
            logger.error(f"touch: cannot touch '{path!s}': No such file or directory")
            return False

        data_bytes: bytes | None = data.encode() if isinstance(data, str) else data

        try:
            with Path(path).open('wb') as f:
                f.write(data_bytes or b'')
            return True
        except Exception as err:
            logger.error(f"touch: failed to write file '{path!s}': {err}")
            return False

    def rmdir(self, path: StrPathLike, recursive: bool = False) -> bool:
        """Remove a directory at the given path."""
        path = Path(self._topath(path))

        if not self.exists(path):
            logger.error(
                f"rmdir: failed to remove '{path!s}': No such file or directory"
            )
            return False

        if not path.is_dir():
            logger.error(f"rmdir: failed to remove '{path!s}': Not a directory")
            return False

        try:
            if recursive:
                shutil.rmtree(path)
            else:
                path.rmdir()

            return True
        except Exception as err:
            logger.error(f"rmdir: failed to remove '{path!s}': {err}")
            return False

    def cat(self, path: StrPathLike) -> bytes:
        """Read the contents of a file as bytes."""
        path = self._topath(path)
        self._ensure_exist(path)

        data: bytes
        with Path(path).open('rb') as f:
            data = f.read()

        return data

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
            os.remove(path)
            return True
        except FileNotFoundError:
            logger.error(f'File not found: {path}')
            return False
        except PermissionError:
            logger.error(f'Permission denied: {path}')
            return False
        except Exception as err:
            logger.error(f'Failed to remove {path}: {err}')
            return False

    def mv(self, source: StrPathLike, destination: StrPathLike) -> None:
        """Move a file or directory to a new location."""
        source = self._topath(source)
        self._ensure_exist(source)

        destination = self._topath(destination)

        shutil.move(source, destination)

    def cp(self, source: StrPathLike, destination: StrPathLike) -> None:
        """Copy a file or directory to a new location."""
        source = self._topath(source)
        destination = self._topath(destination)

        if Path(source).is_dir():
            shutil.copytree(source, destination)
        else:
            shutil.copy2(source, destination)

    # TODO: revise from here to bottom
    # TODO: add support for relative, currently are all abs implicitly
    def tree(self, path: StrPathLike | None = None, *, abs: bool = False) -> Tree:
        """Return a tree view of files and directories starting at path."""
        path = self._topath(path)
        return Tree(
            root=path,
            dir_iterator=self.iterdir,
            dir_checker=self.isdir,
            file_checker=self.isfile,
        )

    def iterdir(self, path: StrPathLike | None = None) -> Iterator[StorixPath]:
        path = self._topath(path)
        return (StorixPath(p) for p in Path(path).iterdir())

    def stat(self, path: StrPathLike) -> Any:
        """Return stat information for the given path."""
        # path = self._topath(path)
        # self._ensure_exist(path)
        #
        # return path.stat()
        raise NotImplementedError

    def du(
        self, path: StrPathLike | None = None, *, human_readable: bool = True
    ) -> Any:
        """Return disk usage statistics for the given path."""
        path = self._topath(path)
        self._ensure_exist(path)
        raise NotImplementedError

    def echo(
        self,
        data: DataBuffer[AnyStr],
        path: StrPathLike,
        *,
        mode: EchoMode = 'w',
        chunksize: int = DEFAULT_WRITE_CHUNKSIZE,
    ) -> bool:
        """Write (overwrite/append) data into a file."""
        path = self._topath(path)

        if not self.exists(path.parent):
            logger.error(
                f"echo: cannot echo into '{path!s}': No such file or directory"
            )
            return False

        from storix.utils.streaming import normalize_data

        stream = normalize_data(data)
        try:
            with Path(path).open(mode + 'b') as f:
                while chunk := stream.read(chunksize):
                    f.write(chunk)

        except Exception as e:
            logger.error(f"echo: failed writing to '{path}': {e}")
            return False

        return True

    def find(self, path: StrPathLike, type: Literal['f', 'd'] | None = None) -> Finder:
        return Finder(
            self.tree(path=path).build(),
            dir_checker=self.isdir,
            file_checker=self.isfile,
            type=type,
        )
