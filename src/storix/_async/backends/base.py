from __future__ import annotations

import abc

from typing import TYPE_CHECKING

from storix.models import Capabilities

from . import generic


if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import PurePosixPath

    from storix.models import Entry, RawStat
    from storix.types import EchoMode


class BackendBase(abc.ABC):
    """Convenience base pre-wiring the ``generic`` fallbacks.

    Subclasses implement the six abstract primitives and get the rest of
    the :class:`~storix._async.backends.StorageBackend` contract for free;
    backends with native fast paths override the concrete methods.
    Deliberately does *not* inherit the Protocol - structural typing checks
    conformance, and the core types against the Protocol only. See the
    Protocol docstrings for the semantics each method must honor.
    """

    capabilities: Capabilities = Capabilities()

    @abc.abstractmethod
    def read_stream(self, path: PurePosixPath) -> AsyncIterator[bytes]:
        """Stream a file's contents in chunks."""

    @abc.abstractmethod
    async def write(
        self,
        path: PurePosixPath,
        data: AsyncIterator[bytes],
        *,
        mode: EchoMode,
        content_type: str | None,
    ) -> None:
        """Write a file from a chunk stream ('w' truncates, 'a' appends)."""

    @abc.abstractmethod
    async def delete(self, path: PurePosixPath) -> None:
        """Delete a leaf: a file or an empty directory."""

    @abc.abstractmethod
    def list_dir(self, path: PurePosixPath) -> AsyncIterator[Entry]:
        """Yield the direct children of a directory."""

    @abc.abstractmethod
    async def stat(self, path: PurePosixPath) -> RawStat:
        """Return raw facts about a path (kind, size, timestamps)."""

    @abc.abstractmethod
    async def make_dir(self, path: PurePosixPath, *, parents: bool) -> None:
        """Create a directory (``parents=True`` behaves like mkdir -p)."""

    async def read(self, path: PurePosixPath) -> bytes:
        """Return the full contents of a file."""
        return await generic.read(self, path)

    async def move(self, src: PurePosixPath, dst: PurePosixPath) -> None:
        """Move a single file (generic fallback: copy then delete)."""
        await generic.move(self, src, dst)

    async def copy(self, src: PurePosixPath, dst: PurePosixPath) -> None:
        """Copy a single file (generic fallback: stream read into write)."""
        await generic.copy(self, src, dst)

    async def delete_tree(self, path: PurePosixPath) -> None:
        """Delete ``path`` and everything below it (rmtree semantics)."""
        await generic.delete_tree(self, path)

    async def du(self, path: PurePosixPath) -> int:
        """Total size in bytes of the tree rooted at ``path``."""
        return await generic.du(self, path)

    async def exists(self, path: PurePosixPath) -> bool:
        """Whether anything lives at ``path``."""
        return await generic.exists(self, path)
