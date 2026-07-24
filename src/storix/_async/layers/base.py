"""LayerBase: the delegating base for custom layers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from storix._async._stream import validate_chunk_size, validate_span


if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Mapping
    from pathlib import PurePosixPath
    from typing import ClassVar

    from storix.enums import Capability
    from storix.models import Capabilities, Entry, RawStat
    from storix.types import EchoMode

    from ..backends import StorageBackend


class LayerBase:
    """Base class for custom layers: full delegation, override what matters.

    Unlike ``__getattr__``-based delegation, every port method is written
    out, so subclasses satisfy the ``StorageBackend`` protocol
    *statically* - type checkers accept them anywhere a backend goes.
    Override the operations your layer changes, and reassign
    ``capabilities`` (e.g. via ``dataclasses.replace``) when it adds one.

    Used unsubclassed it is a harmless pure passthrough - occasionally
    useful for measuring layer overhead, never required.

    Set ``provides`` on a layer that backfills a capability; then
    ``fs.with_layer_missing(TheLayer)`` needs no capability argument - it
    is inferred (see ``DataUrlLayer``/``MetadataLayer``).
    """

    provides: ClassVar[Capability | None] = None
    """The capability this layer backfills, if any (used by native-preference)."""

    removable: ClassVar[bool] = True
    """Whether ``Storix.without_layer`` may strip this layer. A layer that is
    a guarantee (e.g. a sandbox) sets this ``False`` so it can never be
    bypassed."""

    capabilities: Capabilities

    def __init__(self, backend: StorageBackend) -> None:
        self._inner = backend
        self.capabilities = backend.capabilities

    async def read(self, path: PurePosixPath) -> bytes:
        """Return the full contents of a file."""
        return await self._inner.read(path)

    async def read_stream(
        self, path: PurePosixPath, *, chunk_size: int | None = None
    ) -> AsyncIterator[bytes]:
        """Stream a file's contents in bounded chunks.

        Raises:
            ValueError: If ``chunk_size`` is zero or negative.
        """
        validate_chunk_size(chunk_size)
        async for chunk in self._inner.read_stream(path, chunk_size=chunk_size):
            yield chunk

    async def read_range(
        self,
        path: PurePosixPath,
        *,
        offset: int,
        length: int,
        chunk_size: int | None = None,
    ) -> AsyncIterator[bytes]:
        """Stream one byte range of a file, in bounded chunks.

        Raises:
            ValueError: If ``offset`` or ``length`` is negative, or if
                ``chunk_size`` is zero or negative.
        """
        validate_chunk_size(chunk_size)
        validate_span(offset, length)
        async for chunk in self._inner.read_range(
            path, offset=offset, length=length, chunk_size=chunk_size
        ):
            yield chunk

    async def write(
        self,
        path: PurePosixPath,
        data: bytes,
        *,
        mode: EchoMode,
        content_type: str | None,
        metadata: Mapping[str, str] | None = None,
    ) -> None:
        """Write complete contents through this layer's stream path."""
        from ..backends import generic

        await generic.write(
            self,
            path,
            data,
            mode=mode,
            content_type=content_type,
            metadata=metadata,
        )

    async def write_stream(
        self,
        path: PurePosixPath,
        data: AsyncIterator[bytes],
        *,
        chunk_size: int | None = None,
        mode: EchoMode,
        content_type: str | None,
        metadata: Mapping[str, str] | None = None,
    ) -> None:
        """Write a file from a bounded chunk stream.

        Raises:
            ValueError: If ``chunk_size`` is zero or negative.
        """
        validate_chunk_size(chunk_size)
        await self._inner.write_stream(
            path,
            data,
            chunk_size=chunk_size,
            mode=mode,
            content_type=content_type,
            metadata=metadata,
        )

    async def delete(self, path: PurePosixPath) -> None:
        """Delete a leaf: a file or an empty directory."""
        await self._inner.delete(path)

    async def list_dir(self, path: PurePosixPath) -> AsyncIterator[Entry]:
        """Yield the direct children of a directory."""
        async for entry in self._inner.list_dir(path):
            yield entry

    async def list_tree(self, path: PurePosixPath) -> AsyncIterator[PurePosixPath]:
        """Yield every descendant path under a directory (bulk_listing)."""
        async for descendant in self._inner.list_tree(path):
            yield descendant

    async def stat(self, path: PurePosixPath) -> RawStat:
        """Return raw facts about a path."""
        return await self._inner.stat(path)

    async def make_dir(self, path: PurePosixPath, *, parents: bool) -> None:
        """Create a directory."""
        await self._inner.make_dir(path, parents=parents)

    async def exists(self, path: PurePosixPath) -> bool:
        """Whether anything lives at ``path``."""
        return await self._inner.exists(path)

    async def move(self, src: PurePosixPath, dst: PurePosixPath) -> None:
        """Move a file or directory tree."""
        await self._inner.move(src, dst)

    async def copy(self, src: PurePosixPath, dst: PurePosixPath) -> None:
        """Copy a single file."""
        await self._inner.copy(src, dst)

    async def delete_tree(self, path: PurePosixPath) -> None:
        """Delete ``path`` and everything below it."""
        await self._inner.delete_tree(path)

    async def du(self, path: PurePosixPath) -> int:
        """Total content size in bytes of the tree rooted at ``path``."""
        return await self._inner.du(path)

    async def set_metadata(
        self, path: PurePosixPath, metadata: Mapping[str, str]
    ) -> None:
        """Replace a file's custom metadata."""
        await self._inner.set_metadata(path, metadata)

    async def make_url(
        self, path: PurePosixPath, *, expires_in: int | None = None
    ) -> str:
        """Mint a shareable URL for a file."""
        return await self._inner.make_url(path, expires_in=expires_in)

    def locate(self, path: PurePosixPath) -> str:
        """Fully-qualified physical locator for a port path."""
        return self._inner.locate(path)

    async def close(self) -> None:
        """Release the inner backend's resources."""
        await self._inner.close()

    async def provision(self) -> bool:
        """Ensure the inner backend's storage root exists (control-plane)."""
        return await self._inner.provision()
