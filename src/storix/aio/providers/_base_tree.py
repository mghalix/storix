from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from functools import cached_property
from typing import TYPE_CHECKING

from storix.types import StorixPath

if TYPE_CHECKING:
    from ._base import BaseStorage


@dataclass
class TreeNode:
    pass


class StorageTree[S: BaseStorage, N: TreeNode](ABC):
    _storage: S

    def __init__(self, storage: S) -> None:
        """Initialize storage tree."""
        self._storage = storage

    @property
    def root(self) -> StorixPath:
        return self._storage.root

    @cached_property
    @abstractmethod
    def levels(self) -> int: ...

    @abstractmethod
    def next(self) -> N: ...

    @abstractmethod
    def previous(self) -> N: ...

    @abstractmethod
    def draw(self) -> str: ...

    @abstractmethod
    def search(self, pattern: str) -> Sequence[N]: ...

    # TODO(mghali): should i implement those, also include them as algorithm selection in
    # search method? do they return dictionary of nodes? check anytree lib
    # def dfs(self) -> ??
    # def bfs(self) -> ??

    def __str__(self) -> str:
        return self.draw()

    def __len__(self) -> int:
        return self.levels
