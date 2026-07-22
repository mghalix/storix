"""SandboxLayer: chroot as port middleware."""

from __future__ import annotations

from typing import TYPE_CHECKING

from storix import pathops
from storix._async._stream import validate_chunk_size
from storix.errors import PathError, PathNotFoundError, PermissionDeniedError
from storix.types import StorixPath


if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Mapping
    from pathlib import PurePosixPath
    from typing import ClassVar

    from storix.models import Capabilities, Entry, RawStat
    from storix.types import EchoMode, StrPathLike

    from ..backends import StorageBackend


_ROOT = StorixPath('/')


class SandboxLayer:
    """Confine any backend beneath a virtual root - chroot as middleware.

    Every incoming port path is re-anchored under ``root`` after lexical
    normalization, so traversal cannot escape even when a caller bypasses
    the core's resolution. Errors surfacing from the inner backend are
    re-scoped back into the virtual namespace, so the real prefix never
    leaks through error paths or tracebacks.
    """

    removable: ClassVar[bool] = False
    """A jail is a guarantee: ``without_layer`` can never strip it."""

    capabilities: Capabilities

    def __init__(self, backend: StorageBackend, *, root: StrPathLike) -> None:
        self._inner = backend
        self._root = pathops.resolve(root, cwd=_ROOT, home=_ROOT)
        self.capabilities = backend.capabilities

    # --- scoping machinery ---

    def to_real(self, path: StrPathLike) -> StorixPath:
        """Translate a virtual (sandboxed) path to its real inner path.

        The privileged escape hatch for code that *owns* the layer -
        e.g. writing real paths to an audit store while the sandboxed
        session only ever sees virtual ones.
        """
        virtual = pathops.normalize(path)  # clamps '..' inside virtual space
        real = StorixPath(self._root, *virtual.parts[1:])
        if not real.is_relative_to(self._root):  # defense in depth
            raise PermissionDeniedError(path)
        return real

    def to_virtual(self, real: StrPathLike) -> StorixPath:
        """Translate a real inner path back into the virtual namespace.

        Paths outside the sandbox root pass through unchanged.
        """
        p = StorixPath(real)
        if p.is_relative_to(self._root):
            return StorixPath('/', *p.relative_to(self._root).parts)
        return p

    def _rescope(self, exc: PathError) -> PathError:
        """Rebuild an inner error in the caller's virtual namespace.

        When the inner path that failed *is* the root, plain rescoping
        would report ``'/'`` - true inside the jail, and unreadable
        outside it, since no filesystem is missing its own root. Say what
        is actually wrong instead, without naming the real root the jail
        exists to hide.
        """
        virtual = self.to_virtual(exc.path)
        if virtual == _ROOT and isinstance(exc, PathNotFoundError):
            return PathNotFoundError(virtual, 'sandbox root does not exist')
        return type(exc)(virtual)

    # --- the port, delegated under translation ---

    async def read(self, path: PurePosixPath) -> bytes:
        """Return the full contents of a file."""
        try:
            return await self._inner.read(self.to_real(path))
        except PathError as exc:
            raise self._rescope(exc) from None

    async def read_stream(
        self, path: PurePosixPath, *, chunk_size: int | None = None
    ) -> AsyncIterator[bytes]:
        """Stream a file's contents in bounded chunks.

        Raises:
            ValueError: If ``chunk_size`` is zero or negative.
        """
        validate_chunk_size(chunk_size)
        try:
            async for chunk in self._inner.read_stream(
                self.to_real(path), chunk_size=chunk_size
            ):
                yield chunk
        except PathError as exc:
            raise self._rescope(exc) from None

    async def write(
        self,
        path: PurePosixPath,
        data: bytes,
        *,
        mode: EchoMode,
        content_type: str | None,
        metadata: Mapping[str, str] | None = None,
    ) -> None:
        """Write complete contents under sandbox translation."""
        try:
            await self._inner.write(
                self.to_real(path),
                data,
                mode=mode,
                content_type=content_type,
                metadata=metadata,
            )
        except PathError as exc:
            raise self._rescope(exc) from None

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
        try:
            await self._inner.write_stream(
                self.to_real(path),
                data,
                chunk_size=chunk_size,
                mode=mode,
                content_type=content_type,
                metadata=metadata,
            )
        except PathError as exc:
            raise self._rescope(exc) from None

    async def delete(self, path: PurePosixPath) -> None:
        """Delete a leaf: a file or an empty directory."""
        try:
            await self._inner.delete(self.to_real(path))
        except PathError as exc:
            raise self._rescope(exc) from None

    async def list_dir(self, path: PurePosixPath) -> AsyncIterator[Entry]:
        """Yield the direct children of a directory (names need no scoping)."""
        try:
            async for entry in self._inner.list_dir(self.to_real(path)):
                yield entry
        except PathError as exc:
            raise self._rescope(exc) from None

    async def list_tree(self, path: PurePosixPath) -> AsyncIterator[PurePosixPath]:
        """Yield descendant paths, re-scoped back into the virtual namespace.

        Unlike ``list_dir`` (bare names, no scoping), this yields full
        paths in the real namespace, so each is translated back through
        ``to_virtual`` before it leaves the jail.
        """
        try:
            async for descendant in self._inner.list_tree(self.to_real(path)):
                yield self.to_virtual(descendant)
        except PathError as exc:
            raise self._rescope(exc) from None

    async def stat(self, path: PurePosixPath) -> RawStat:
        """Return raw facts about a path."""
        try:
            return await self._inner.stat(self.to_real(path))
        except PathError as exc:
            raise self._rescope(exc) from None

    async def make_dir(self, path: PurePosixPath, *, parents: bool) -> None:
        """Create a directory."""
        try:
            await self._inner.make_dir(self.to_real(path), parents=parents)
        except PathError as exc:
            raise self._rescope(exc) from None

    async def exists(self, path: PurePosixPath) -> bool:
        """Whether anything lives at ``path``."""
        try:
            return await self._inner.exists(self.to_real(path))
        except PathError as exc:
            raise self._rescope(exc) from None

    async def move(self, src: PurePosixPath, dst: PurePosixPath) -> None:
        """Move a file or directory tree."""
        try:
            await self._inner.move(self.to_real(src), self.to_real(dst))
        except PathError as exc:
            raise self._rescope(exc) from None

    async def copy(self, src: PurePosixPath, dst: PurePosixPath) -> None:
        """Copy a single file."""
        try:
            await self._inner.copy(self.to_real(src), self.to_real(dst))
        except PathError as exc:
            raise self._rescope(exc) from None

    async def delete_tree(self, path: PurePosixPath) -> None:
        """Delete ``path`` and everything below it."""
        try:
            await self._inner.delete_tree(self.to_real(path))
        except PathError as exc:
            raise self._rescope(exc) from None

    async def du(self, path: PurePosixPath) -> int:
        """Total size in bytes of the tree rooted at ``path``."""
        try:
            return await self._inner.du(self.to_real(path))
        except PathError as exc:
            raise self._rescope(exc) from None

    async def set_metadata(
        self, path: PurePosixPath, metadata: Mapping[str, str]
    ) -> None:
        """Replace a file's custom metadata."""
        try:
            await self._inner.set_metadata(self.to_real(path), metadata)
        except PathError as exc:
            raise self._rescope(exc) from None

    async def make_url(
        self, path: PurePosixPath, *, expires_in: int | None = None
    ) -> str:
        """Mint a shareable URL for a file."""
        try:
            return await self._inner.make_url(self.to_real(path), expires_in=expires_in)
        except PathError as exc:
            raise self._rescope(exc) from None

    def locate(self, path: PurePosixPath) -> str:
        """Locator of the *real* underlying path - the audit primitive.

        A sandboxed session's ``fs.locate('/x')`` returns the physical
        location (``file:///srv/data/tenant-42/x``), no privileged
        ``to_real`` dance required.
        """
        return self._inner.locate(self.to_real(path))

    async def close(self) -> None:
        """Release the inner backend's resources."""
        await self._inner.close()
