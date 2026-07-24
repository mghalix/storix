from __future__ import annotations

import abc

from typing import TYPE_CHECKING

from storix._async._stream import collect, resolve_chunk_size, span_of, validate_span
from storix.constants import DEFAULT_READ_CHUNK_SIZE, DEFAULT_WRITE_CHUNK_SIZE
from storix.enums import Capability
from storix.errors import UnsupportedOperationError
from storix.models import Capabilities

from . import generic


if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Mapping
    from pathlib import PurePosixPath

    from storix.models import Entry, RawStat
    from storix.types import EchoMode


class BackendBase(abc.ABC):
    """Convenience base pre-wiring the ``generic`` fallbacks.

    Subclasses implement four structural primitives plus at least one method
    from each I/O pair (``read``/``read_stream`` and
    ``write``/``write_stream``). The opposite form is derived generically.
    Streaming-native backends should implement the stream methods; simple
    whole-object backends may implement ``read`` and ``write`` instead, with
    the documented cost that their stream fallbacks materialize full files.
    Backends with native fast paths override the remaining concrete methods.
    Deliberately does *not* inherit the Protocol - structural typing checks
    conformance, and the core types against the Protocol only. See the
    Protocol docstrings for the semantics each method must honor.
    """

    capabilities: Capabilities = Capabilities()
    default_read_chunk_size: int = DEFAULT_READ_CHUNK_SIZE
    """Preferred read size when a caller passes ``chunk_size=None``."""
    default_write_chunk_size: int = DEFAULT_WRITE_CHUNK_SIZE
    """Preferred write batch when a caller passes ``chunk_size=None``."""

    def _overrides(self, name: str) -> bool:
        """Whether the concrete backend overrides ``name`` from this base."""
        return getattr(type(self), name) is not getattr(BackendBase, name)

    async def read(self, path: PurePosixPath) -> bytes:
        """Return full contents, collecting a native stream by default.

        Raises:
            NotImplementedError: If neither read method is implemented.
        """
        if not self._overrides('read_stream'):
            msg = f'{type(self).__name__} must implement read() or read_stream()'
            raise NotImplementedError(msg)
        return await generic.read(self, path)

    async def read_stream(
        self, path: PurePosixPath, *, chunk_size: int | None = None
    ) -> AsyncIterator[bytes]:
        """Split a whole-object read into consumer-sized chunks.

        This compatibility fallback materializes the full file. Override it
        whenever the provider supports bounded streaming.

        Raises:
            NotImplementedError: If neither read method is implemented.
            ValueError: If ``chunk_size`` is zero or negative.
        """
        if not self._overrides('read'):
            msg = f'{type(self).__name__} must implement read() or read_stream()'
            raise NotImplementedError(msg)
        size = resolve_chunk_size(chunk_size, self.default_read_chunk_size)
        data = await self.read(path)
        for offset in range(0, len(data), size):
            yield data[offset : offset + size]

    async def read_range(
        self,
        path: PurePosixPath,
        *,
        offset: int,
        length: int,
        chunk_size: int | None = None,
    ) -> AsyncIterator[bytes]:
        """Stream a byte range, skipping through ``read_stream`` by default.

        Correct for every backend, cheap for none: it transfers the bytes
        before ``offset`` and throws them away. Backends whose provider can
        fetch a range in one request override this and set
        ``capabilities.ranged_reads``, which is what the core gates its
        parallel reads on (ADR 0032).

        Raises:
            ValueError: If ``offset`` or ``length`` is negative, or if
                ``chunk_size`` is zero or negative.
        """
        validate_span(offset, length)
        size = resolve_chunk_size(chunk_size, self.default_read_chunk_size)
        async for chunk in span_of(
            self.read_stream(path, chunk_size=size), offset=offset, length=length
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
        """Write complete contents through a native stream by default.

        Raises:
            NotImplementedError: If neither write method is implemented.
        """
        if not self._overrides('write_stream'):
            msg = f'{type(self).__name__} must implement write() or write_stream()'
            raise NotImplementedError(msg)
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
        """Collect a chunk stream for a whole-object write implementation.

        This compatibility fallback materializes the full payload. Override it
        whenever the provider supports bounded streaming.

        Raises:
            NotImplementedError: If neither write method is implemented.
            ValueError: If ``chunk_size`` is zero or negative.
        """
        if not self._overrides('write'):
            msg = f'{type(self).__name__} must implement write() or write_stream()'
            raise NotImplementedError(msg)
        resolve_chunk_size(chunk_size, self.default_write_chunk_size)
        await self.write(
            path,
            await collect(data),
            mode=mode,
            content_type=content_type,
            metadata=metadata,
        )

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

    def list_tree(self, path: PurePosixPath) -> AsyncIterator[PurePosixPath]:
        """Yield the absolute path of every descendant of a directory.

        Capability-gated by ``bulk_listing`` (default: unsupported). Only
        backends that advertise the capability override this, and the core
        calls it exclusively on those, so this default never runs in
        practice; it is the honest signal for a stray call.

        Raises:
            UnsupportedOperationError: Always, on a backend that does not
                advertise ``bulk_listing``.
        """
        del path
        raise UnsupportedOperationError(Capability.BULK_LISTING)

    async def provision(self) -> bool:
        """Ensure the backend's storage root exists (control-plane).

        Capability-gated by ``provisioning`` (default: unsupported). Only
        backends whose engine can create their root override this, and the
        core calls it exclusively on those, so this default never runs in
        practice; it is the honest signal for a stray call.

        Raises:
            UnsupportedOperationError: Always, on a backend that does not
                advertise ``provisioning``.
        """
        raise UnsupportedOperationError(Capability.PROVISIONING)

    async def move(self, src: PurePosixPath, dst: PurePosixPath) -> None:
        """Move a file or directory tree (fallback: copy then delete)."""
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

    async def set_metadata(
        self, path: PurePosixPath, metadata: Mapping[str, str]
    ) -> None:
        """Replace a file's custom metadata (default: unsupported)."""
        del path, metadata
        raise UnsupportedOperationError(Capability.CUSTOM_METADATA)

    async def make_url(
        self, path: PurePosixPath, *, expires_in: int | None = None
    ) -> str:
        """Mint a presigned URL (default: unsupported)."""
        del path, expires_in
        raise UnsupportedOperationError(Capability.PRESIGNED_URLS)

    def locate(self, path: PurePosixPath) -> str:
        """Opaque locator; override to expose a physical URI scheme."""
        return f'storix://{path}'

    async def close(self) -> None:  # noqa: B027 - optional hook, deliberately concrete
        """Release backend resources; the default is a no-op."""
