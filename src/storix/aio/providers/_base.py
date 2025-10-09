from abc import ABC
from collections.abc import Sequence
from pathlib import Path
from types import TracebackType
from typing import Any, Literal, Protocol, Self, overload

from storix.sandbox import PathSandboxable
from storix.typing import StrPathLike
from storix.utils import PathLogicMixin, to_data_url


class Storage(Protocol):
    """Async version of Storage protocol - identical interface but async methods."""

    @property
    def root(self) -> Path: ...
    @property
    def home(self) -> Path: ...

    def chroot(self, new_root: StrPathLike) -> Self: ...
    async def touch(
        self, path: StrPathLike | None, data: Any | None = None
    ) -> bool: ...
    async def cat(self, path: StrPathLike) -> bytes: ...
    async def cd(self, path: StrPathLike | None = None) -> Self: ...
    def pwd(self) -> Path: ...
    async def mkdir(self, path: StrPathLike, *, parents: bool = True) -> None: ...
    async def mv(self, source: StrPathLike, destination: StrPathLike) -> None: ...
    async def cp(self, source: StrPathLike, destination: StrPathLike) -> None: ...
    async def rm(self, path: StrPathLike) -> bool: ...
    async def rmdir(self, path: StrPathLike, recursive: bool = False) -> bool: ...
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
    ) -> list[Path]: ...
    async def ls(
        self, path: StrPathLike | None = None, *, abs: bool = False, all: bool = True
    ) -> Sequence[Path | str]: ...
    async def tree(
        self, path: StrPathLike | None = None, *, abs: bool = False
    ) -> list[Path]: ...
    async def stat(self, path: StrPathLike) -> Any: ...
    async def du(
        self, path: StrPathLike | None = None, *, human_readable: bool = True
    ) -> Any: ...

    # non unix commands but useful utils
    async def exists(self, path: StrPathLike) -> bool: ...
    async def isdir(self, path: StrPathLike) -> bool: ...
    async def isfile(self, path: StrPathLike) -> bool: ...
    async def make_url(
        self,
        path: StrPathLike,
        *,
        astype: Literal["data_url"] = "data_url",
    ) -> str: ...
    async def make_data_url(self, path: StrPathLike) -> str: ...
    def parent(self, path: StrPathLike) -> Path: ...
    def parents(self, path: StrPathLike) -> Sequence[Path]: ...
    async def empty(self, path: StrPathLike) -> bool: ...
    def is_root(self, path: StrPathLike) -> bool: ...

    async def open(self) -> Self: ...
    async def close(self) -> None: ...

    async def __aenter__(self) -> Self:
        return await self.open()

    async def __aexit__(
        self,
        exc_type: type[BaseException],
        exc_value: BaseException,
        traceback: TracebackType,
    ) -> None:
        await self.close()


class BaseStorage(Storage, PathLogicMixin, ABC):
    """Async base provider - REUSES all path logic from sync version."""

    __slots__ = (
        "_current_path",
        "_home",
        "_min_depth",
        "_sandbox",
    )

    _min_depth: Path
    _current_path: Path
    _home: Path
    _sandbox: PathSandboxable | None

    def __init__(
        self,
        initialpath: StrPathLike | None = None,
        *,
        sandboxed: bool = False,
        sandbox_handler: type[PathSandboxable] | None = None,
    ) -> None:
        """Initialize the async storage (identical to sync version).

        Sets up common operations for any filesystem storage implementation
        with optional path sandboxing. It expands and normalizes the provided path,
        creates the directory if necessary, and configures path translation for
        sandboxed mode.

        Args:
            initialpath: The starting directory path for storage operations.
                Default path is defined in application settings. Supports tilde (~)
                expansion for home directory references.
            sandboxed: If True, restricts file system access to the initial path
                directory tree. When enabled, the initial path acts as a virtual
                root directory ("/").
            sandbox_handler: The implementation class for path sandboxing.
                Only used when sandboxed=True.

        """
        root = self._prepend_root(initialpath)
        if sandboxed:
            assert sandbox_handler, (
                "'sandbox_handler' cannot be None when 'sandboxed' is set to True"
            )
            self._sandbox = sandbox_handler(root)
            self._init_storage(initialpath=Path("/"))
        else:
            self._sandbox = None
            self._init_storage(initialpath=root)

    async def _ensure_exist(self, path: StrPathLike) -> None:
        if await self.exists(path):
            return

        raise ValueError(f"path '{path}' does not exist.")

    async def open(self) -> Self:
        return self

    async def close(self) -> None:
        return None

    @property
    def home(self) -> Path:
        """Return the home path of the storage."""
        return self._home

    @property
    def root(self) -> Path:
        return Path("/")

    def chroot(self, new_root: StrPathLike) -> Self:
        """Change storage root to a descendant path reconstructing the storage."""
        initialpath = self._topath(new_root)
        return self._init_storage(initialpath=initialpath)

    def pwd(self) -> Path:
        """Return the current working directory."""
        return self._current_path

    async def make_url(
        self,
        path: StrPathLike,
        *,
        astype: Literal["data_url"] = "data_url",
    ) -> str:
        if astype == "data_url":
            return await self.make_data_url(path)

        raise NotImplementedError(f"cannot make url of type: {astype}")

    async def make_data_url(self, path: StrPathLike) -> str:
        data = await self.cat(path)
        return to_data_url(buf=data)

    async def empty(self, path: StrPathLike) -> bool:
        return not bool(await self.ls(path))

    def _init_storage(self, initialpath: StrPathLike) -> Self:
        initialpath = self._prepend_root(initialpath)
        self._min_depth = self._home = self._current_path = initialpath
        return self

    def _prepend_root(self, path: StrPathLike | None = None) -> Path:
        if path is None:
            return Path("/")
        return Path("/") / str(path).lstrip("/")
