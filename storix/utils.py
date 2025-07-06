from collections.abc import Callable, Sequence
from functools import reduce
from pathlib import Path
from typing import ParamSpec, TypeVar

from typing_extensions import Self

from storix.sandbox import PathSandboxable
from storix.typing import PathLike

P = ParamSpec("P")
R = TypeVar("R")


T = TypeVar("T")
U = TypeVar("U")
V = TypeVar("V")


def pipeline(*funcs: Callable[P, R]) -> Callable[P, R]:
    """Compose multiple functions into a single pipeline."""

    def compose_two(f: Callable[[U], V], g: Callable[[T], U]) -> Callable[[T], V]:
        """Compose two functions."""
        return lambda x: f(g(x))

    return reduce(compose_two, reversed(funcs), lambda x: x)  # type: ignore


class DictMixin:
    """A mixin providing dict-like behavior for classes."""

    def __setitem__(self, key: str, item: object) -> None:
        """Set an item in the dictionary."""
        self.__dict__[key] = item

    def __getitem__(self, key: str) -> object:
        """Get an item from the dictionary."""
        return self.__dict__[key]

    def __repr__(self) -> str:
        """Return the string representation of the object."""
        return str(self)

    def __len__(self) -> int:
        """Return the number of keys in the dictionary."""
        return len(self.keys())

    def __delitem__(self, key: str) -> None:
        """Delete an item from the dictionary."""
        self.__dict__[key] = None

    def __eq__(self, other: object) -> bool:
        """Check equality with another object."""
        if isinstance(other, self.__class__):
            return self.__dict__ == other.__dict__
        return False

    def __ne__(self, other: object) -> bool:
        """Check inequality with another object."""
        return not self.__eq__(other)

    def __str__(self) -> str:
        """Return a string of public attributes."""
        return str({k: v for k, v in self.__dict__.items() if not k.startswith("_")})

    def __contains__(self, key: str) -> bool:
        """Check if a key is in the dictionary."""
        return key in self.__dict__

    def has_key(self, k: str) -> bool:
        """Check if the dictionary has a key (legacy)."""
        return k in self.__dict__

    def update(self, *args: object, **kwargs: object) -> None:
        """Update the dictionary with new key-value pairs."""
        return self.__dict__.update(*args, **kwargs)

    def keys(self) -> list[str]:
        """Return a list of keys."""
        return [k for k in self.__dict__ if not k.startswith("_")]

    def values(self) -> list[object]:
        """Return a list of values."""
        return [v for k, v in self.__dict__.items() if not k.startswith("_")]

    def items(self) -> list[tuple[str, object]]:
        """Return a list of key-value pairs."""
        return [(k, v) for k, v in self.__dict__.items() if not k.startswith("_")]

    def get(self, key: str, default: object = None) -> object:
        """Get a value for a key, or return default if not found."""
        if key in self.__dict__:
            return self.__dict__[key]
        return default


L = TypeVar("L", bound=PathLike)


class PathLogicMixin:
    """Mixin for shared path logic between sync and async BaseStorage.

    Expects the inheriting class to provide:
        - self._min_depth: Path
        - self._current_path: Path
        - self._home: Path
        - self._sandbox: PathSandboxable | None
        - self.home: property returning Path
        - self.pwd(): method returning Path
    """

    _min_depth: Path
    _current_path: Path
    _home: Path
    _sandbox: PathSandboxable | None

    def _parse_dots(self, path: PathLike, *, graceful: bool = True) -> Path:
        path = Path(path)
        bk_cnt: int = str(path).count("..")
        if bk_cnt:
            bk_cnt += 1
        target_path = eval(f"path{'.parent' * bk_cnt}")
        # type: ignore[attr-defined] because 'home' is guaranteed by inheriting class
        if target_path >= Path(self.home):  # type: ignore[attr-defined]
            return target_path
        if not graceful:
            raise ValueError(f"Cannot go back deeper than current path: {path}")
        return Path(self.home)  # type: ignore[attr-defined]

    def _parse_home(self, path: PathLike) -> Path:
        # type: ignore[attr-defined] because 'home' is guaranteed by inheriting class
        return Path(str(path).replace("~", str(self.home)))  # type: ignore[attr-defined]

    def _makeabs(self, path: PathLike) -> Path:
        path = Path(path)
        if path.is_absolute():
            return path
        # type: ignore[attr-defined] because 'pwd' is guaranteed by inheriting class
        return self.pwd() / path  # type: ignore[attr-defined]

    def _topath(self, path: PathLike | None) -> Path:
        sb = getattr(self, "_sandbox", None)

        path_str = str(path).strip()
        if not path or path_str == ".":
            # type: ignore[attr-defined] because 'pwd' is guaranteed by inheriting class
            path = self.pwd()  # type: ignore[attr-defined]
        elif path_str == "~":
            # type: ignore[attr-defined] because 'home' is guaranteed by inheriting class
            path = Path(self.home)  # type: ignore[attr-defined]
        else:
            p = Path(path)
            if sb and not p.is_absolute():
                # type: ignore[attr-defined] because '_current_path' is guaranteed by inheriting class
                path = self._current_path / p  # type: ignore[attr-defined]

        if sb:
            path = Path(sb.to_real(path))
            path = path.resolve()
            try:
                path.relative_to(sb.get_prefix().resolve())
            except ValueError as err:
                raise ValueError(f"Path '{path}' escapes sandbox boundaries") from err
        else:
            path = pipeline(
                self._parse_dots,
                self._parse_home,
                self._makeabs,
            )(path)
            path = Path(path)
        return path

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

    def _filter_hidden(self, output: Sequence[L]) -> Sequence[L]:
        return list(filter(lambda q: not Path(q).name.startswith("."), output))
