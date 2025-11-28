from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING

from storix.types import StorixPath

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Sequence


class Tree:
    __slots__ = (
        "_built",
        "dir_checker",
        "dir_iter",
        "file_checker",
        "root",
    )

    def __init__(
        self,
        root: StorixPath,
        *,
        dir_iterator: Callable[[StorixPath], Iterator[StorixPath]],
        dir_checker: Callable[[StorixPath], bool],
        file_checker: Callable[[StorixPath], bool],
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

    # TODO(mghalix): make prettier as tree, when integrating nodes and pointers to Tree
    def __repr__(self) -> str:
        extension = "├──"
        extension_end = "└──"

        def _decor(p: StorixPath, prefix: str) -> str:
            return f"{prefix} {p}"

        dir = partial(_decor, prefix="📁")
        file = partial(_decor, prefix="📄")

        res = []

        res.append(dir(self.root))

        for p in self.build():
            view = dir if self.dir_checker(p) else file
            res.append(view(p))

        return "\n".join(res)
        # return "\n".join(map(str, self.build()))
