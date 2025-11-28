from typing import TYPE_CHECKING, Literal

from storix.types import StorixPath


if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Sequence


class Finder:
    """Finder of paths."""

    __slots__ = ('dir_checker', 'file_checker', 'paths')

    def __init__(
        self,
        paths: Sequence[StorixPath],
        *,
        dir_checker: Callable[[StorixPath], bool],
        file_checker: Callable[[StorixPath], bool],
        type: Literal['f', 'd'] | None = None,
    ) -> None:
        """Initialize find object."""
        self.dir_checker = dir_checker
        self.file_checker = file_checker
        self.paths: set[StorixPath] = self._resolve(paths=paths, type=type)

    def _resolve(
        self, paths: Sequence[StorixPath], type: Literal['f', 'd'] | None = None
    ) -> set[StorixPath]:
        if not type:
            return set(paths)

        checker = self.dir_checker if type == 'd' else self.file_checker
        return set(filter(checker, paths))

    def __repr__(self) -> str:
        return '\n'.join(map(str, self.paths))

    def __iter__(self) -> Iterator[StorixPath]:
        return iter(self.paths)

    def __len__(self) -> int:
        return len(self.paths)
