# ruff: noqa: A004
from __future__ import annotations

import dataclasses

from pathlib import PurePosixPath
from typing import TYPE_CHECKING, override

from storix._async._stream import chunked, collect
from storix.enums import PathKind
from storix.errors import (
    AlreadyExistsError,
    DirectoryNotEmptyError,
    IsADirectoryError,
    NotADirectoryError,
    PathNotFoundError,
)
from storix.models import Capabilities, Entry, RawStat
from storix.utils.time import utcnow

from .base import BackendBase


if TYPE_CHECKING:
    import datetime as dt

    from collections.abc import AsyncIterator, Iterator, Mapping

    from storix.types import EchoMode


@dataclasses.dataclass(slots=True)
class _Node:
    """Internal per-path record; mutable on purpose (this IS the store)."""

    data: bytearray | None  # None => directory
    created: dt.datetime
    modified: dt.datetime
    metadata: dict[str, str] | None = None

    @property
    def is_dir(self) -> bool:
        return self.data is None

    @property
    def size(self) -> int:
        return 0 if self.data is None else len(self.data)


class MemoryBackend(BackendBase):
    """Dict-backed reference backend.

    Implements only the six primitives, so every generic fallback is
    exercised through it - it is the reference for port semantics and the
    conformance suite's fastest vehicle. Directories are real nodes
    (``data=None``), the root is pre-seeded, timestamps are UTC-aware.
    Supports custom metadata, making it the credential-free test vehicle
    for the capability.
    """

    capabilities: Capabilities = Capabilities(custom_metadata=True)

    _nodes: dict[PurePosixPath, _Node]

    def __init__(self) -> None:
        now = utcnow()
        self._nodes = {PurePosixPath('/'): _Node(data=None, created=now, modified=now)}

    def _children(self, path: PurePosixPath) -> Iterator[PurePosixPath]:
        """Yield direct children from a snapshot of the store.

        The snapshot (the eagerly-evaluated outer iterable) is what lets
        consumers delete entries while iterating, as ``delete_tree`` does.
        """
        return (p for p in list(self._nodes) if p.parent == path and p != path)

    @override
    async def read_stream(self, path: PurePosixPath) -> AsyncIterator[bytes]:
        """Stream a file's contents in chunks."""
        node = self._get(path)
        data = node.data
        if data is None:
            raise IsADirectoryError(path)

        for chunk in chunked(data):
            yield chunk

    @override
    async def write(
        self,
        path: PurePosixPath,
        data: AsyncIterator[bytes],
        *,
        mode: EchoMode,
        content_type: str | None,
        metadata: Mapping[str, str] | None = None,
    ) -> None:
        """Write a file from a chunk stream ('w' truncates, 'a' appends)."""
        payload = await collect(data)
        now = utcnow()
        node = self._nodes.get(path)

        if node is None or mode == 'w':
            if node is not None and node.data is None:
                raise IsADirectoryError(path)
            self._nodes[path] = _Node(
                data=bytearray(payload),
                created=now,
                modified=now,
                metadata=dict(metadata) if metadata else None,
            )
            return

        if node.data is None:
            raise IsADirectoryError(path)

        node.data.extend(payload)
        node.modified = now
        if metadata is not None:
            node.metadata = dict(metadata)

    @override
    async def delete(self, path: PurePosixPath) -> None:
        """Delete a leaf: a file or an empty directory."""
        props = await self.stat(path)
        if props.kind is PathKind.DIRECTORY and any(self._children(path)):
            raise DirectoryNotEmptyError(path)

        self._nodes.pop(path)

    @override
    async def list_dir(self, path: PurePosixPath) -> AsyncIterator[Entry]:
        """Yield the direct children of a directory, sizes included."""
        is_file = (await self.stat(path)).kind is PathKind.FILE
        if is_file:
            raise NotADirectoryError(path)

        for child in self._children(path):
            node = self._nodes[child]
            yield Entry(
                name=child.name,
                is_dir=node.is_dir,
                size=None if node.is_dir else node.size,
            )

    @override
    async def stat(self, path: PurePosixPath) -> RawStat:
        """Return raw facts about a path (directory sizes are 0)."""
        node = self._get(path)
        return RawStat(
            kind=PathKind.DIRECTORY if node.is_dir else PathKind.FILE,
            size=node.size,
            created=node.created,
            modified=node.modified,
            metadata=dict(node.metadata) if node.metadata else None,
        )

    @override
    async def make_dir(self, path: PurePosixPath, *, parents: bool) -> None:
        """Create a directory (``parents=True`` behaves like mkdir -p)."""
        existing = self._nodes.get(path)
        if existing is not None:
            if parents and existing.is_dir:
                return
            raise AlreadyExistsError(path)

        if parents:
            for parent in reversed(path.parents):
                node = self._nodes.get(parent)
                if node is None:
                    now = utcnow()
                    self._nodes[parent] = _Node(data=None, created=now, modified=now)
                elif not node.is_dir:
                    raise NotADirectoryError(parent)
        else:
            parent_path = path.parent
            parent_node = self._nodes.get(parent_path)
            if parent_node is None:
                raise PathNotFoundError(parent_path)
            if not parent_node.is_dir:
                raise NotADirectoryError(parent_path)

        now = utcnow()
        self._nodes[path] = _Node(data=None, created=now, modified=now)

    def _get(self, path: PurePosixPath) -> _Node:
        """Look up a node or raise ``PathNotFoundError``."""
        try:
            return self._nodes[path]
        except KeyError:
            raise PathNotFoundError(path) from None
