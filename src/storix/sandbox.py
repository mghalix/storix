import asyncio
from collections.abc import Awaitable, Callable
from functools import wraps
from pathlib import Path
from typing import Any, Protocol, TypeVar

from storix.typing import StrPathLike

T = TypeVar("T")


class PathSandboxable(Protocol):
    """Protocol defining sandboxed filesystem path operations.

    This protocol defines the interface for classes that provide path sandboxing
    functionality, restricting file system access to a specific directory tree.
    Path sandboxing creates a virtual root directory that maps to a real filesystem
    location, preventing access to any paths outside this sandbox.

    Implementations must provide methods to convert between real and virtual paths,
    and a decorator that can sandbox functions that operate on paths.
    """

    def __init__(self, prefix_path: StrPathLike) -> None:
        """Initialize the path sandbox with a root directory.

        Args:
            prefix_path: The filesystem path to use as the sandbox root.

        """

    def to_virtual(self, real_path: StrPathLike) -> Path:
        """Convert a real filesystem path to a virtual sandboxed path.

        Args:
            real_path: A path in the real filesystem.

        Returns:
            Path: The equivalent virtual path inside the sandbox.

        Raises:
            ValueError: If the real path is outside the sandboxed directory.

        """
        ...

    def to_real(self, virtual_path: StrPathLike) -> Path:
        """Convert a virtual sandboxed path to a real filesystem path.

        Args:
            virtual_path: A virtual path within the sandbox.

        Returns:
            Path: The corresponding real filesystem path.

        """
        ...

    def get_prefix(self) -> Path:
        """Get the real filesystem path that serves as the sandbox root.

        Returns:
            Path: The sandbox root directory path.

        """
        ...

    def __call__(
        self, func: Callable[..., T | Awaitable[T]]
    ) -> Callable[..., T | Awaitable[T]]:
        """Sandbox filesystem operations in a function.

        Wraps a function to automatically convert between real and virtual paths
        in both arguments and return values.

        Args:
            func: The function to sandbox. Can be either sync or async.

        Returns:
            A wrapped function that operates with sandboxed paths.

        """
        ...


class SandboxedPathHandler:
    """Handler for mapping between real and virtual (sandboxed) paths."""

    def __init__(self, prefix_path: StrPathLike) -> None:
        """Initialize with a prefix path for the sandbox."""
        self._prefix = Path(prefix_path).resolve()

    def to_virtual(self, real_path: StrPathLike) -> Path:
        """Convert a real path to its virtual (sandboxed) equivalent."""
        path = Path(real_path).resolve()
        try:
            return Path("/") / path.relative_to(self._prefix)
        except ValueError as err:
            raise ValueError(
                f"Path '{real_path}' is outside the sandbox root '{self._prefix}'"
            ) from err

    def to_real(self, virtual_path: StrPathLike | None = None) -> Path:
        """Convert a virtual (sandboxed) path to its real path."""
        if virtual_path is None:
            return self._prefix

        path = Path(virtual_path)

        # Handle special cases first
        if str(path) in (".", "/"):
            return self._prefix

        # For absolute paths, we need to treat them as virtual paths
        # and map them relative to our sandbox root
        if path.is_absolute():
            # Check if this is already a real path within our sandbox
            try:
                path.relative_to(self._prefix)
                # If we reach here, it's already a real path within sandbox
                return path.resolve()
            except ValueError:
                # It's an absolute path that should be treated as virtual
                # Remove the leading slash and treat as relative to sandbox
                path = Path(*path.parts[1:])

        # Construct the full path and resolve it to handle .. and . properly
        full_path = (self._prefix / path).resolve()

        # Verify the resolved path is still within sandbox boundaries
        try:
            full_path.relative_to(self._prefix.resolve())
        except ValueError as err:
            raise ValueError(
                f"Path '{virtual_path}' would escape sandbox boundaries"
            ) from err

        return full_path

    def get_prefix(self) -> Path:
        """Get the real filesystem path that serves as the sandbox root."""
        return self._prefix

    def __call__(
        self, func: Callable[..., T | Awaitable[T]]
    ) -> Callable[..., T | Awaitable[T]]:
        """Decorator to sandbox a function's path arguments/results."""

        def get_new_args_kwargs(*args: Any, **kwargs: Any) -> tuple[list, dict]:
            # convert args that are paths
            new_args = []

            def is_sandboxable(arg: Any) -> bool:
                return isinstance(arg, str | Path)

            for arg in args:
                if is_sandboxable(arg):
                    new_args.append(self.to_real(arg))
                else:
                    new_args.append(arg)  # unchanged

            new_kwargs = {}
            for k, v in kwargs.items():
                if is_sandboxable(v):
                    new_kwargs[k] = self.to_real(v)
                else:
                    new_kwargs[k] = v

            return new_args, new_kwargs

        def convert_result(result: Any) -> Any:
            if isinstance(result, str | Path):
                return self.to_virtual(result)
            if isinstance(result, list | tuple):
                return [
                    self.to_virtual(item) if isinstance(item, str | Path) else item
                    for item in result
                ]
            return result

        @wraps(func)
        async def async_wrapper(*args, **kwargs):  # noqa
            new_args, new_kwargs = get_new_args_kwargs(*args, **kwargs)
            assert asyncio.iscoroutinefunction(func)
            result = await func(*new_args, **new_kwargs)
            return convert_result(result)

        @wraps(func)
        def sync_wrapper(*args, **kwargs):  # noqa
            new_args, new_kwargs = get_new_args_kwargs(*args, **kwargs)
            result = func(*new_args, **new_kwargs)
            return convert_result(result)

        if asyncio.iscoroutinefunction(func):
            return async_wrapper

        return sync_wrapper
