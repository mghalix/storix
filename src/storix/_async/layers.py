"""Port middleware: backends that wrap backends.

A layer implements the same ``StorageBackend`` protocol it consumes, so
layers compose with backends and with each other. Cross-cutting concerns
(sandboxing now; caching, metadata, observability later) live here
rather than inside the core or any backend.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from storix import pathops
from storix.errors import PathError, PermissionDeniedError
from storix.types import StorixPath


if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Mapping
    from pathlib import PurePosixPath

    from storix.models import Capabilities, Entry, RawStat
    from storix.types import EchoMode, StrPathLike

    from .backends import StorageBackend


_ROOT = StorixPath('/')


class SandboxLayer:
    """Confine any backend beneath a virtual root - chroot as middleware.

    Every incoming port path is re-anchored under ``root`` after lexical
    normalization, so traversal cannot escape even when a caller bypasses
    the core's resolution. Errors surfacing from the inner backend are
    re-scoped back into the virtual namespace, so the real prefix never
    leaks through error paths or tracebacks.
    """

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
        """Rebuild an inner error in the caller's virtual namespace."""
        return type(exc)(self.to_virtual(exc.path))

    # --- the port, delegated under translation ---

    async def read(self, path: PurePosixPath) -> bytes:
        """Return the full contents of a file."""
        try:
            return await self._inner.read(self.to_real(path))
        except PathError as exc:
            raise self._rescope(exc) from None

    async def read_stream(self, path: PurePosixPath) -> AsyncIterator[bytes]:
        """Stream a file's contents in chunks."""
        try:
            async for chunk in self._inner.read_stream(self.to_real(path)):
                yield chunk
        except PathError as exc:
            raise self._rescope(exc) from None

    async def write(
        self,
        path: PurePosixPath,
        data: AsyncIterator[bytes],
        *,
        mode: EchoMode,
        content_type: str | None,
        metadata: Mapping[str, str] | None = None,
    ) -> None:
        """Write a file from a chunk stream."""
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

    async def close(self) -> None:
        """Release the inner backend's resources."""
        await self._inner.close()


class PassthroughLayer:
    """Base class for custom layers: full delegation, override what matters.

    Unlike ``__getattr__``-based delegation, every port method is written
    out, so subclasses satisfy the ``StorageBackend`` protocol
    *statically* - type checkers accept them anywhere a backend goes.
    Override the operations your layer changes, and reassign
    ``capabilities`` (e.g. via ``dataclasses.replace``) when it adds one.
    """

    capabilities: Capabilities

    def __init__(self, backend: StorageBackend) -> None:
        self._inner = backend
        self.capabilities = backend.capabilities

    async def read(self, path: PurePosixPath) -> bytes:
        """Return the full contents of a file."""
        return await self._inner.read(path)

    async def read_stream(self, path: PurePosixPath) -> AsyncIterator[bytes]:
        """Stream a file's contents in chunks."""
        async for chunk in self._inner.read_stream(path):
            yield chunk

    async def write(
        self,
        path: PurePosixPath,
        data: AsyncIterator[bytes],
        *,
        mode: EchoMode,
        content_type: str | None,
        metadata: Mapping[str, str] | None = None,
    ) -> None:
        """Write a file from a chunk stream."""
        await self._inner.write(
            path, data, mode=mode, content_type=content_type, metadata=metadata
        )

    async def delete(self, path: PurePosixPath) -> None:
        """Delete a leaf: a file or an empty directory."""
        await self._inner.delete(path)

    async def list_dir(self, path: PurePosixPath) -> AsyncIterator[Entry]:
        """Yield the direct children of a directory."""
        async for entry in self._inner.list_dir(path):
            yield entry

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

    async def close(self) -> None:
        """Release the inner backend's resources."""
        await self._inner.close()
