from __future__ import annotations

from abc import ABC
from typing import TYPE_CHECKING, Literal, Self

from storix.types import StorixPath
from storix.utils import PathLogicMixin

from ._proto import Storage

if TYPE_CHECKING:
    from storix.sandbox import PathSandboxer
    from storix.types import StrPathLike


class BaseStorage(PathLogicMixin, Storage, ABC):
    """Async base provider - REUSES all path logic from sync version."""

    __slots__ = (
        "_current_path",
        "_home",
        "_min_depth",
        "_sandbox",
    )

    _min_depth: StorixPath
    _current_path: StorixPath
    _home: StorixPath
    _sandbox: PathSandboxer | None

    def __init__(
        self,
        initialpath: StrPathLike | None = None,
        *,
        sandboxed: bool = False,
        sandbox_handler: type[PathSandboxer] | None = None,
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
            self._init_storage(initialpath=StorixPath("/"))
        else:
            self._sandbox = None
            self._init_storage(initialpath=root)

    async def _ensure_exist(self, path: StrPathLike) -> None:
        if await self.exists(path):
            return
        from storix.errors import PathNotFoundError
        raise PathNotFoundError(f"path '{path}' does not exist")

    async def open(self) -> Self:
        return self

    async def close(self) -> None:
        await self.cd()

    @property
    def home(self) -> StorixPath:
        """Return the home path of the storage."""
        return self._home

    @property
    def root(self) -> StorixPath:
        return StorixPath("/")

    def chroot(self, new_root: StrPathLike) -> Self:
        """Change storage root to a descendant path reconstructing the storage."""
        initialpath = self._topath(new_root)
        return self._init_storage(initialpath=initialpath)

    def pwd(self) -> StorixPath:
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
        from storix.utils import to_data_url

        data = await self.cat(path)
        return to_data_url(buf=data)

    async def empty(self, path: StrPathLike) -> bool:
        return not bool(await self.ls(path))

    def _init_storage(self, initialpath: StrPathLike) -> Self:
        initialpath = self._prepend_root(initialpath)
        self._min_depth = self._home = self._current_path = initialpath
        return self

    def _prepend_root(self, path: StrPathLike | None = None) -> StorixPath:
        if path is None:
            return StorixPath("/")
        return StorixPath("/") / str(path).lstrip("/")
