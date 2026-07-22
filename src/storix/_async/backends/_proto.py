from __future__ import annotations

from typing import TYPE_CHECKING, Protocol


if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Mapping
    from pathlib import PurePosixPath

    from storix.models import Capabilities, Entry, RawStat
    from storix.types import EchoMode


class StorageBackend(Protocol):
    """The storage port: the full contract between the core and a backend.

    Path contract: every path a backend receives is already resolved -
    absolute, POSIX-style, with ``~``/``..``/cwd and sandbox translation
    applied by the layers above. Backends do zero path logic beyond mapping
    to their native representation.

    Error contract: backends raise only the ``storix.errors`` taxonomy
    (``PathNotFoundError``, ``IsADirectoryError``, ...), translating native
    SDK/OS failures at their boundary. Generic fallbacks and the core rely
    on this to branch portably.

    Parent handling: the core guarantees a parent directory exists before
    calling ``write``/``write_stream``/``make_dir(parents=False)``; behavior
    on a missing parent is backend-specific and unspecified by the port.
    """

    capabilities: Capabilities
    """User-observable optional features this backend supports."""

    async def read(self, path: PurePosixPath) -> bytes:
        """Return the full contents of a file.

        ``BackendBase`` derives this by collecting ``read_stream`` unless a
        whole-object backend overrides it.
        """
        ...

    def read_stream(
        self, path: PurePosixPath, *, chunk_size: int | None = None
    ) -> AsyncIterator[bytes]:
        """Stream a file's contents in bounded chunks.

        Implementations are async generator functions: plain callables
        that return the iterator directly, so the declaration here
        carries no ``async`` keyword of its own.

        Args:
            path: The file to stream.
            chunk_size: Maximum yielded chunk size. ``None`` selects the
                backend's preferred default. Smaller native chunks may pass
                through unchanged; chunk boundaries carry no meaning.

        Raises:
            ValueError: If ``chunk_size`` is zero or negative.
        """
        ...

    async def write(
        self,
        path: PurePosixPath,
        data: bytes,
        *,
        mode: EchoMode,
        content_type: str | None,
        metadata: Mapping[str, str] | None = None,
    ) -> None:
        """Write a complete in-memory payload.

        ``BackendBase`` derives this by wrapping ``data`` as one chunk for
        ``write_stream`` unless a whole-object backend overrides it.
        """
        ...

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
        """Write a file from a chunk stream.

        Mode ``'w'`` creates or truncates; ``'a'`` appends, creating the
        file if missing. ``content_type`` and ``metadata`` are only
        honored when the matching capability is set; the core never
        passes values to a backend without the capability, so others may
        ignore them.

        ``chunk_size`` is the maximum target backend batch; ``None`` selects
        the backend's preferred default. Metadata semantics are *replace*: a
        provided mapping replaces the stored metadata entirely, ``{}`` clears
        it, and ``None`` leaves existing metadata untouched on append (merge
        is the caller's job: stat, merge, write).

        Raises:
            ValueError: If ``chunk_size`` is zero or negative.
        """
        ...

    async def delete(self, path: PurePosixPath) -> None:
        """Delete a leaf: a file or an *empty* directory.

        Raises ``DirectoryNotEmptyError`` for a directory with children.
        """
        ...

    def list_dir(self, path: PurePosixPath) -> AsyncIterator[Entry]:
        """Yield the direct children of a directory.

        Raises ``NotADirectoryError`` when ``path`` is a file. Must tolerate
        deletion of already-yielded entries while iteration is in flight
        (``generic.delete_tree`` deletes as it walks); entries removed
        concurrently by others may still be yielded (readdir semantics).
        """
        ...

    def list_tree(self, path: PurePosixPath) -> AsyncIterator[PurePosixPath]:
        """Yield the absolute path of every descendant of a directory.

        Capability-gated by ``bulk_listing``: a single cheap backend
        operation (one delimiter-less recursive list on object stores) that
        streams every descendant key under ``path`` as an absolute port
        path, in no guaranteed order. Directories may or may not appear as
        entries of their own; the core relies only on descendants two or
        more levels deep to decide an immediate child's emptiness, so a
        directory-marker entry is neither required nor a problem.

        The core calls this exclusively on backends that advertise
        ``bulk_listing``; others need not implement it. Does no grouping -
        that path logic lives in the core. Raises ``NotADirectoryError``
        when ``path`` is a file.
        """
        ...

    async def stat(self, path: PurePosixPath) -> RawStat:
        """Return raw facts about a path (kind, size, timestamps)."""
        ...

    async def make_dir(self, path: PurePosixPath, *, parents: bool) -> None:
        """Create a directory.

        Plain form raises ``AlreadyExistsError`` if ``path`` exists and
        ``PathNotFoundError``/``NotADirectoryError`` for a missing or
        non-directory parent. With ``parents=True`` it behaves like
        ``mkdir -p``: creates missing ancestors and is a no-op when ``path``
        is already a directory (an existing *file* still raises).
        """
        ...

    # ops with native fast paths - required, but `generic` fallbacks are
    # one import away for backends without one
    async def move(self, src: PurePosixPath, dst: PurePosixPath) -> None:
        """Move a file or a directory tree to ``dst``."""
        ...

    async def copy(self, src: PurePosixPath, dst: PurePosixPath) -> None:
        """Copy a single file (directory copies require native support)."""
        ...

    async def delete_tree(self, path: PurePosixPath) -> None:
        """Delete ``path`` and everything below it (rmtree semantics)."""
        ...

    async def du(self, path: PurePosixPath) -> int:
        """Total content size in bytes of the tree rooted at ``path``.

        Apparent bytes (sum of file sizes; a file reports its own size) -
        never allocated blocks, which object stores do not have.
        """
        ...

    async def exists(self, path: PurePosixPath) -> bool:
        """Whether anything lives at ``path``."""
        ...

    async def set_metadata(
        self, path: PurePosixPath, metadata: Mapping[str, str]
    ) -> None:
        """Replace a file's custom metadata without touching its content.

        Replace semantics like ``write``: the mapping replaces entirely,
        ``{}`` clears. Files only (directory metadata is out of scope for
        now). Requires ``capabilities.custom_metadata``; the
        ``BackendBase`` default raises ``UnsupportedOperationError``.
        """
        ...

    async def make_url(
        self, path: PurePosixPath, *, expires_in: int | None = None
    ) -> str:
        """Mint a shareable URL for a file.

        Only meaningful when ``capabilities.presigned_urls`` is set; the
        ``BackendBase`` default raises ``UnsupportedOperationError``.
        ``expires_in`` is advisory: ``None`` means the provider's own
        default lifetime, and providers that cannot bound a URL's
        lifetime at all (public-link services, CDNs) ignore it rather
        than refuse.
        """
        ...

    def locate(self, path: PurePosixPath) -> str:
        """Fully-qualified physical locator for a port path (a URI).

        The audit/logging/cross-system primitive: where this port path
        *actually* lives, independent of the session's virtual view -
        ``file:///srv/data/x.mp4``, ``abfss://c@acct.dfs...net/x.mp4``.
        Sync (pure string math, no I/O). The ``BackendBase`` default is
        an opaque ``storix://`` form; backends with a real scheme
        override. Parsing a locator back into a backend is the URI
        factory (roadmap 0.3.0).
        """
        ...

    async def close(self) -> None:
        """Release backend resources (network clients); idempotent."""
        ...
