from abc import ABC
from collections.abc import Sequence
from pathlib import Path
from types import TracebackType
from typing import Any, Literal, Protocol, overload

from typing_extensions import Self

from storix.sandbox import PathSandboxable
from storix.typing import PathLike
from storix.utils import PathLogicMixin


class Storage(Protocol):
    """Protocol for storage provider interface."""

    @property
    def root(self) -> Path: ...
    @property
    def home(self) -> Path: ...

    def chroot(self, new_root: PathLike) -> Self: ...
    def touch(self, path: PathLike | None, data: Any | None = None) -> bool: ...
    def cat(self, path: PathLike) -> bytes: ...
    def cd(self, path: PathLike | None = None) -> Self: ...
    def pwd(self) -> Path: ...
    def mkdir(self, path: PathLike, *, parents: bool = False) -> None: ...
    def mv(self, source: PathLike, destination: PathLike) -> None: ...
    def cp(self, source: PathLike, destination: PathLike) -> None: ...
    def rm(self, path: PathLike) -> bool: ...
    def rmdir(self, path: PathLike, recursive: bool = False) -> bool: ...
    @overload
    def ls(
        self,
        path: PathLike | None = None,
        *,
        abs: Literal[False] = False,
        all: bool = True,
    ) -> list[str]: ...
    @overload
    def ls(
        self, path: PathLike | None = None, *, abs: Literal[True], all: bool = True
    ) -> list[Path]: ...
    def ls(
        self, path: PathLike | None = None, *, abs: bool = False, all: bool = True
    ) -> Sequence[Path | str]: ...
    def tree(
        self, path: PathLike | None = None, *, abs: bool = False
    ) -> list[Path]: ...
    # TODO(@mghali): bind stat and du return type to Node or Tree for du
    # the bound generic to TreeNode or Tree would cause circular import error...?
    def stat(self, path: PathLike) -> Any: ...
    def du(
        self, path: PathLike | None = None, *, human_readable: bool = True
    ) -> Any: ...

    # non unix commands but useful utils
    def exists(self, path: PathLike) -> bool: ...
    def isdir(self, path: PathLike) -> bool: ...
    def isfile(self, path: PathLike) -> bool: ...

    def __enter__(self) -> Self: ...
    def __exit__(
        self,
        exc_type: type[BaseException],
        exc_value: BaseException,
        traceback: TracebackType,
    ) -> None: ...


class BaseStorage(Storage, PathLogicMixin, ABC):
    """Abstract base class defining storage operations across different backends."""

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
        initialpath: PathLike | None = None,
        *,
        sandboxed: bool = False,
        sandbox_handler: type[PathSandboxable] | None = None,
    ) -> None:
        """Initialize the storage.

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

    def _ensure_exist(self, path: PathLike) -> None:
        if self.exists(path):
            return

        raise ValueError(f"path '{path}' does not exist.")

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
        self.cd()

    @property
    def home(self) -> Path:
        """Return the home path of the storage."""
        return self._home

    @property
    def root(self) -> Path:
        return Path("/")

    def chroot(self, new_root: PathLike) -> Self:
        """Change storage root to a descendant path reconstructing the storage."""
        initialpath = self._topath(new_root)
        return self._init_storage(initialpath=initialpath)

    def pwd(self) -> Path:
        """Return the current working directory."""
        return self._current_path

    def _init_storage(self, initialpath: PathLike) -> Self:
        initialpath = self._prepend_root(initialpath)
        self._min_depth = self._home = self._current_path = initialpath
        return self

    def _prepend_root(self, path: PathLike | None = None) -> Path:
        if path is None:
            return Path("/")
        return Path("/") / str(path).lstrip("/")
