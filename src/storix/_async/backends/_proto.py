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
    calling ``write``/``make_dir(parents=False)``; behavior on a missing
    parent is backend-specific and unspecified by the port.
    """

    capabilities: Capabilities
    """User-observable optional features this backend supports."""

    async def read(self, path: PurePosixPath) -> bytes:
        """Return the full contents of a file."""
        ...

    def read_stream(self, path: PurePosixPath) -> AsyncIterator[bytes]:
        """Stream a file's contents in chunks.

        Implementations are async generator functions: plain callables
        that return the iterator directly, so the declaration here
        carries no ``async`` keyword of its own.
        """
        ...

    async def write(
        self,
        path: PurePosixPath,
        data: AsyncIterator[bytes],
        *,
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
        """Total size in bytes of the tree rooted at ``path``.

        For a file, its size.
        """
        ...

    async def exists(self, path: PurePosixPath) -> bool:
        """Whether anything lives at ``path``."""
        ...

    async def make_url(self, path: PurePosixPath, *, expires_in: int) -> str:
        """Mint a time-limited shareable URL for a file.

        Only meaningful when ``capabilities.presigned_urls`` is set; the
        ``BackendBase`` default raises ``UnsupportedOperationError``.
        """
        ...

    async def close(self) -> None:
        """Release backend resources (network clients); idempotent."""
        ...
