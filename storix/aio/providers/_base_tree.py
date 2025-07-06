from abc import ABC, abstractmethod
from collections.abc import Sequence
from functools import cached_property
from pathlib import Path
from typing import TYPE_CHECKING, Generic, TypeVar

from pydantic import BaseModel

if TYPE_CHECKING:
    from ._base import BaseStorage

_N = TypeVar("_N", bound="TreeNode")
_S = TypeVar("_S", bound="BaseStorage")


class TreeNode(BaseModel):
    pass


class StorageTree(ABC, Generic[_S, _N]):
    _storage: _S

    def __init__(self, storage: _S) -> None:
        """Initialize storage tree."""
        self._storage = storage

    @property
    def root(self) -> Path:
        return self._storage.root

    @cached_property
    @abstractmethod
    def levels(self) -> int: ...

    @abstractmethod
    def next(self) -> _N: ...

    @abstractmethod
    def previous(self) -> _N: ...

    @abstractmethod
    def draw(self) -> str: ...

    @abstractmethod
    def search(self, pattern: str) -> Sequence[_N]: ...

    # TODO(mghali): should i implement those, also include them as algorithm selection in
    # search method? do they return dictionary of nodes? check anytree lib
    # def dfs(self) -> ??
    # def bfs(self) -> ??

    def __str__(self) -> str:
        return self.draw()

    def __len__(self) -> int:
        return self.levels
