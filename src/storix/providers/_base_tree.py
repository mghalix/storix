from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ._base import BaseStorage

    """Base class for tree nodes in storage trees."""


@dataclass
class TreeNode:
    """Base class for tree nodes in storage trees."""


# TODO(@mghali): add total_dirs and total_files like unix cli tree at the end of output
class StorageTree[S: BaseStorage, N: TreeNode](ABC):
    """Abstract base class for storage tree structures."""

    _storage: S

    def __init__(self, storage: S) -> None:
        """Initialize storage tree."""
        self._storage = storage

    @property
    def root(self) -> Path:
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

    # TODO(@mghali): should i implement those, also include them as algorithm selection in
    # search method? do they return dictionary of nodes? check anytree lib
    # def dfs(self) -> ??
    # def bfs(self) -> ??

    def __str__(self) -> str:
        """Return a string representation of the storage tree."""
        return self.draw()

    def __len__(self) -> int:
        """Return the number of levels in the storage tree."""
        return self.levels
