"""The unix-flavored engine: one stateful session over any storage backend."""
# ruff: noqa: A004 - storix error classes intentionally shadow stdlib names

from __future__ import annotations

from typing import TYPE_CHECKING, Self

from storix import pathops
from storix._async._compat import gather
from storix._async._stream import ensure_chunks
from storix._async.backends import generic
from storix.constants import DEFAULT_URL_EXPIRY_SECONDS
from storix.enums import PathKind
from storix.errors import (
    IsADirectoryError,
    NotADirectoryError,
    PathNotFoundError,
    UnsupportedOperationError,
)
from storix.models import FileProperties
from storix.types import StorixPath


if TYPE_CHECKING:
    from collections.abc import Mapping
    from types import TracebackType

    from storix._async.backends import StorageBackend
    from storix.types import AsyncDataBuffer, EchoMode, StrPathLike


_ROOT = StorixPath('/')


class Storix:
    """A unix-flavored filesystem session over a storage backend.

    One instance is one stateful session (cwd, home) over one backend.
    Every user-supplied path funnels through ``pathops.resolve`` (cwd,
    ``~``, ``..``) before reaching the port, and every failure raises a
    typed ``storix.errors`` exception - no boolean error returns.

    ``home`` is resolved lexically at construction but neither validated
    nor created; the first operation against a missing home fails with
    ``PathNotFoundError`` like any other path would.
    """

    def __init__(self, backend: StorageBackend, *, home: StrPathLike = '/') -> None:
        self._backend = backend
        self._home = pathops.resolve(home, cwd=_ROOT, home=_ROOT)
        self._cwd = self._home

    # --- identity ---

    @property
    def backend(self) -> StorageBackend:
        """Escape hatch: the raw port for backend-specific operations."""
        return self._backend

    @property
    def root(self) -> StorixPath:
        """The filesystem root (always ``/``)."""
        return _ROOT

    @property
    def home(self) -> StorixPath:
        """The session's home directory (the ``~`` anchor)."""
        return self._home

    def pwd(self) -> StorixPath:
        """Return the current working directory."""
        return self._cwd

    # --- lifecycle ---

    async def close(self) -> None:
        """Release the backend's resources (idempotent)."""
        await self._backend.close()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.close()

    # --- resolution ---

    def _resolve(self, path: StrPathLike | None = None) -> StorixPath:
        """Funnel every user path through the lexical pipeline."""
        if path is None:
            return self._cwd
        return pathops.resolve(path, cwd=self._cwd, home=self._home)

    async def _ensure_parent(self, path: StorixPath) -> None:
        """Raise unless ``path``'s parent exists and is a directory."""
        parent = path.parent
        raw = await self._backend.stat(parent)
        if raw.kind is not PathKind.DIRECTORY:
            raise NotADirectoryError(parent)

    # --- navigation ---

    async def cd(self, path: StrPathLike | None = None) -> Self:
        """Change the working directory; no argument returns home."""
        target = self._home if path is None else self._resolve(path)
        raw = await self._backend.stat(target)
        if raw.kind is not PathKind.DIRECTORY:
            raise NotADirectoryError(target)
        self._cwd = target
        return self

    # --- read ---

    async def ls(
        self,
        path: StrPathLike | None = None,
        *,
        all: bool = False,
        abs: bool = False,
    ) -> list[StorixPath]:
        """List a directory (hidden entries excluded unless ``all=True``).

        Like unix ls, listing a file returns the file itself.
        """
        target = self._resolve(path)
        raw = await self._backend.stat(target)
        if raw.kind is PathKind.FILE:
            return [target if abs else StorixPath(target.name)]

        names = [entry.name async for entry in self._backend.list_dir(target)]
        if not all:
            names = [name for name in names if not pathops.is_hidden(name)]
        if abs:
            return [target / name for name in names]
        return [StorixPath(name) for name in names]

    async def cat(self, path: StrPathLike, /, *paths: StrPathLike) -> bytes:
        """Read one or more files, concatenated in argument order."""
        targets = [self._resolve(p) for p in (path, *paths)]
        parts = await gather(*(self._backend.read(target) for target in targets))
        return b''.join(parts)

    async def stat(self, path: StrPathLike | None = None) -> FileProperties:
        """Return the user-facing properties of a path."""
        target = self._resolve(path)
        raw = await self._backend.stat(target)
        return FileProperties(
            name=target.name or '/',
            size=raw.size,
            create_time=raw.created,
            modify_time=raw.modified,
            access_time=raw.accessed,
            file_kind=raw.kind,
            metadata=raw.metadata,
        )

    async def url(
        self,
        path: StrPathLike | None = None,
        *,
        expires_in: int = DEFAULT_URL_EXPIRY_SECONDS,
    ) -> str:
        """Mint a time-limited shareable URL for a file.

        Requires ``capabilities.presigned_urls`` (Azure: a SAS URL).
        """
        if not self._backend.capabilities.presigned_urls:
            operation = 'presigned_urls'
            raise UnsupportedOperationError(operation)
        return await self._backend.make_url(self._resolve(path), expires_in=expires_in)

    async def data_url(self, path: StrPathLike | None = None) -> str:
        """Return the file inlined as a base64 ``data:`` URL (any backend)."""
        from storix.utils import to_data_url

        return to_data_url(buf=await self._backend.read(self._resolve(path)))

    async def du(self, path: StrPathLike | None = None) -> int:
        """Total size in bytes of the tree rooted at ``path``."""
        return await self._backend.du(self._resolve(path))

    async def exists(self, path: StrPathLike | None = None) -> bool:
        """Whether anything lives at ``path``."""
        return await self._backend.exists(self._resolve(path))

    async def isfile(self, path: StrPathLike | None = None) -> bool:
        """Whether ``path`` is a file (False when missing, like ``test -f``)."""
        try:
            raw = await self._backend.stat(self._resolve(path))
        except PathNotFoundError:
            return False
        return raw.kind is PathKind.FILE

    async def isdir(self, path: StrPathLike | None = None) -> bool:
        """Whether ``path`` is a directory (False when missing)."""
        try:
            raw = await self._backend.stat(self._resolve(path))
        except PathNotFoundError:
            return False
        return raw.kind is PathKind.DIRECTORY

    # --- write ---

    async def touch(self, path: StrPathLike, /, *paths: StrPathLike) -> None:
        """Create files if missing; refresh mtime of existing files.

        Unlike unix touch, directories are rejected (``IsADirectoryError``)
        - storage backends cannot bump a directory's mtime portably.
        """
        targets = [self._resolve(p) for p in (path, *paths)]
        for target in targets:
            await self._ensure_parent(target)
        await gather(
            *(
                self._backend.write(
                    target, ensure_chunks(b''), mode='a', content_type=None
                )
                for target in targets
            )
        )

    async def echo(
        self,
        data: AsyncDataBuffer[str] | AsyncDataBuffer[bytes],
        path: StrPathLike,
        /,
        *,
        mode: EchoMode = 'w',
        content_type: str | None = None,
        metadata: Mapping[str, str] | None = None,
    ) -> None:
        """Write data into a file, creating it if missing.

        ``mode='w'`` truncates, ``mode='a'`` appends. Accepts str/bytes,
        readable file-like objects, and (async) iterables of either.
        ``content_type`` and ``metadata`` require the matching backend
        capability.
        """
        if content_type is not None and not self._backend.capabilities.content_type:
            operation = 'content_type'
            raise UnsupportedOperationError(operation)
        if metadata is not None and not self._backend.capabilities.custom_metadata:
            operation = 'custom_metadata'
            raise UnsupportedOperationError(operation)
        target = self._resolve(path)
        await self._ensure_parent(target)
        await self._backend.write(
            target,
            ensure_chunks(data),
            mode=mode,
            content_type=content_type,
            metadata=metadata,
        )

    async def mkdir(
        self, path: StrPathLike, /, *paths: StrPathLike, parents: bool = False
    ) -> None:
        """Create directories (``parents=True`` behaves like mkdir -p)."""
        targets = [self._resolve(p) for p in (path, *paths)]
        await gather(
            *(self._backend.make_dir(target, parents=parents) for target in targets)
        )

    # --- delete ---

    async def rm(
        self, path: StrPathLike, /, *paths: StrPathLike, recursive: bool = False
    ) -> None:
        """Delete files; with ``recursive=True`` (rm -r) also directories.

        All targets are validated before anything is deleted.
        """
        targets = [self._resolve(p) for p in (path, *paths)]
        stats = await gather(*(self._backend.stat(target) for target in targets))
        for target, raw in zip(targets, stats, strict=True):
            if raw.kind is PathKind.DIRECTORY and not recursive:
                raise IsADirectoryError(target)
        await gather(
            *(
                self._backend.delete_tree(target)
                if raw.kind is PathKind.DIRECTORY
                else self._backend.delete(target)
                for target, raw in zip(targets, stats, strict=True)
            )
        )

    async def rmdir(self, path: StrPathLike, /, *paths: StrPathLike) -> None:
        """Delete empty directories - strict unix rmdir.

        A non-empty directory raises ``DirectoryNotEmptyError`` (use
        ``rm(recursive=True)`` for trees); a file raises
        ``NotADirectoryError``.
        """
        targets = [self._resolve(p) for p in (path, *paths)]
        stats = await gather(*(self._backend.stat(target) for target in targets))
        for target, raw in zip(targets, stats, strict=True):
            if raw.kind is not PathKind.DIRECTORY:
                raise NotADirectoryError(target)
        await gather(*(self._backend.delete(target) for target in targets))

    # --- move / copy ---

    async def mv(self, source: StrPathLike, /, *paths: StrPathLike) -> None:
        """Move/rename; the last argument is the destination (unix mv).

        A single source renames onto the destination (or moves *into* it
        when it is an existing directory); multiple sources require an
        existing directory destination.
        """
        sources, dst = self._split_destination('mv', source, paths)
        targets = await self._plan_destinations(sources, dst)
        await gather(
            *(
                self._backend.move(src, target)
                for src, target in zip(sources, targets, strict=True)
            )
        )

    async def cp(
        self, source: StrPathLike, /, *paths: StrPathLike, recursive: bool = False
    ) -> None:
        """Copy; the last argument is the destination (unix cp).

        Copying a directory requires ``recursive=True`` (cp -r), which
        overlays into existing destination directories like unix does.
        """
        sources, dst = self._split_destination('cp', source, paths)
        src_stats = await gather(*(self._backend.stat(src) for src in sources))
        for src, raw in zip(sources, src_stats, strict=True):
            if raw.kind is PathKind.DIRECTORY and not recursive:
                raise IsADirectoryError(src)
        targets = await self._plan_destinations(sources, dst)
        await gather(
            *(
                generic.copy_tree(self._backend, src, target)
                if raw.kind is PathKind.DIRECTORY
                else self._backend.copy(src, target)
                for src, raw, target in zip(sources, src_stats, targets, strict=True)
            )
        )

    def _split_destination(
        self, op: str, first: StrPathLike, rest: tuple[StrPathLike, ...]
    ) -> tuple[list[StorixPath], StorixPath]:
        """Split unix-style variadic arguments into (sources, destination)."""
        if not rest:
            msg = f'{op}() needs a source and a destination: {op}(src, ..., dst)'
            raise TypeError(msg)
        *more, dst = rest
        sources = [self._resolve(p) for p in (first, *more)]
        return sources, self._resolve(dst)

    async def _plan_destinations(
        self, sources: list[StorixPath], dst: StorixPath
    ) -> list[StorixPath]:
        """Map sources onto final target paths, honoring unix semantics.

        An existing directory destination receives the sources *inside*
        it; anything else is a rename target, valid only for a single
        source and requiring an existing parent.
        """
        try:
            dst_kind = (await self._backend.stat(dst)).kind
        except PathNotFoundError:
            dst_kind = None

        if dst_kind is PathKind.DIRECTORY:
            return [dst / src.name for src in sources]
        if len(sources) > 1:
            raise NotADirectoryError(dst)
        await self._ensure_parent(dst)
        return [dst]
