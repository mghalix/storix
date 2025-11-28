from __future__ import annotations

from collections.abc import Sized
from typing import TYPE_CHECKING, Self

from storix.types import StorixPath, StrPathLike


if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Iterator, Sequence


class Tree(Sized):
    __slots__ = (
        '_built',
        'dir_checker',
        'dir_iter',
        'file_checker',
        'root',
    )

    def __init__(
        self,
        root: StorixPath,
        *,
        dir_iterator: Callable[[StorixPath], Iterator[StorixPath]],
        dir_checker: Callable[[StrPathLike], bool],
        file_checker: Callable[[StrPathLike], bool],
    ) -> None:
        self.root = root
        self.dir_iter = dir_iterator
        self.dir_checker = dir_checker
        self.file_checker = file_checker
        self._built: Sequence[StorixPath] | None = None

    def build(self) -> Sequence[StorixPath]:
        if not self._built:
            self._built = list(iter(self))

        return self._built

    @classmethod
    def from_iterable(cls, it: Iterable[StorixPath]) -> Self:
        # needed currently for backward compat with azure tree

        # no need anymore as size wouldn't exhaust since build is cached
        # paths = tuple(it)  # ensure never exhausted
        from collections.abc import Iterator

        from storix.utils.paths import is_dir_approx, is_file_approx

        return cls(
            root=StorixPath('/'),
            dir_iterator=lambda _: it if isinstance(it, Iterator) else iter(it),
            dir_checker=is_dir_approx,
            file_checker=is_file_approx,
        )

    def __iter__(self) -> Iterator[StorixPath]:
        for p in self.dir_iter(self.root):
            if self.file_checker(p):
                yield p
                continue

            if self.dir_checker(p):
                yield p
                yield from Tree(
                    root=p,
                    dir_iterator=self.dir_iter,
                    dir_checker=self.dir_checker,
                    file_checker=self.file_checker,
                )

    def __len__(self) -> int:
        return self.size

    @property
    def size(self) -> int:
        """Number of files in current tree."""
        return len(self.build())  # build already cached

    # TODO: make prettier as tree, when integrating nodes and pointers to Tree
    def __repr__(self) -> str:
        from functools import partial

        def _decor(p: StorixPath, prefix: str) -> str:
            return f'{prefix} {p}'

        dir = partial(_decor, prefix='📁')
        file = partial(_decor, prefix='📄')

        res: list[str] = []

        res.append(dir(self.root))

        for p in self.build():
            view = dir if self.dir_checker(p) else file
            res.append(view(p))

        return '\n'.join(res)
