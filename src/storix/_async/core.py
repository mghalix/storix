"""The unix-flavored engine: one stateful session over any storage backend."""
# ruff: noqa: A004 - storix error classes intentionally shadow stdlib names

from __future__ import annotations

import copy

from typing import TYPE_CHECKING, Any, ParamSpec, Protocol, Self, cast

from storix import pathops
from storix._async._compat import gather
from storix._async._stream import ensure_chunks, validate_chunk_size
from storix._async.backends import generic
from storix.enums import Capability, PathKind
from storix.errors import (
    IsADirectoryError,
    NonRemovableLayerError,
    NotADirectoryError,
    PathNotFoundError,
    UnsupportedOperationError,
)
from storix.models import DirEntry, FileProperties
from storix.types import StorixPath


if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable, Iterable, Mapping
    from contextlib import AbstractAsyncContextManager

    from storix._async.backends import StorageBackend
    from storix.types import AsyncDataBuffer, EchoMode, StrPathLike


P = ParamSpec('P')


class LayerFactory(Protocol[P]):
    """A layer class/factory: backend first, then its own params.

    Public so integrators writing their own layer helpers can name the
    type; it appears in the ``when_missing`` signature.
    """

    def __call__(
        self, backend: StorageBackend, /, *args: P.args, **kwargs: P.kwargs
    ) -> StorageBackend: ...


# a fully-bound layer (the layers= list, and what with_layer produces):
# backend in, backend out. Public so consumers need not redefine it.
type BoundLayer = Callable[[StorageBackend], StorageBackend]


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

    def __init__(
        self,
        backend: StorageBackend,
        *,
        home: StrPathLike = '/',
        layers: Iterable[BoundLayer] = (),
    ) -> None:
        """Open a session over ``backend``, optionally stacking layers.

        ``layers`` are factories taking a backend and returning a wrapped
        one (a layer class taking only the backend, or a
        ``functools.partial`` carrying its options). Applied in order:
        each wraps the previous, so the *last* entry is outermost.
        """
        for build in layers:
            backend = build(backend)
        self._backend = backend
        self._home = pathops.resolve(home, cwd=_ROOT, home=_ROOT)
        self._cwd = self._home

    # --- identity ---

    @property
    def backend(self) -> StorageBackend:
        """Escape hatch: the raw port for backend-specific operations."""
        return self._backend

    @property
    def layers(self) -> tuple[StorageBackend, ...]:
        """The active layers, outermost first (empty when there are none).

        Reading the stack is a legitimate need - a UI naming what wraps a
        session, an audit trail recording it - and the alternative is
        duck-typing on a layer's private ``_inner``, which is nobody
        else's business. A tuple, because this is a snapshot to read, not
        the stack to edit: composition stays with ``with_layer`` /
        ``without_layer``::

            any(isinstance(layer, CacheLayer) for layer in fs.layers)

        The base backend is *not* included; it is ``base_backend``. Layers
        are identified structurally (anything wrapping an inner backend),
        so custom layers appear alongside the built-ins.
        """
        stack: list[StorageBackend] = []
        node = self._backend
        while (inner := getattr(node, '_inner', None)) is not None:
            stack.append(node)
            node = inner
        return tuple(stack)

    @property
    def base_backend(self) -> StorageBackend:
        """The real backend under any layers - the actual provider.

        ``backend`` hands back the outermost object, which is whatever
        layer happens to wrap the session; this walks past them to the
        thing that really talks to storage.
        """
        node = self._backend
        while (inner := getattr(node, '_inner', None)) is not None:
            node = inner
        return node

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

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    def chroot(self, path: StrPathLike, /) -> Self:
        """Return a *new* session whose root is ``path`` (resolved here).

        Sugar for wrapping this session's backend in a ``SandboxLayer`` -
        the new session cannot see or escape above ``path``, and errors
        inside it are re-scoped to its namespace. The current session is
        untouched. Keep an explicit ``SandboxLayer`` instead when you
        need the privileged ``to_real``/``to_virtual`` handle (audit).
        """
        from .layers import SandboxLayer

        return type(self)(SandboxLayer(self._backend, root=self._resolve(path)))

    def with_layer(
        self, layer: LayerFactory[P], /, *args: P.args, **kwargs: P.kwargs
    ) -> Self:
        """Return a *new* session over this backend wrapped in ``layer``.

        Strongly-typed forwarder (Starlette ``add_middleware`` style):
        extra args/kwargs go to the layer's constructor and are checked
        against its signature::

            fs.with_layer(MetadataLayer, serialize=orjson.dumps)

        The current session is untouched; the new one starts at its home
        (a live cwd may not exist inside the new namespace). For
        native-preference use ``with_layer_missing``.
        """
        return type(self)(layer(self._backend, *args, **kwargs), home=self._home)

    def with_layer_missing(
        self, layer: LayerFactory[P], /, *args: P.args, **kwargs: P.kwargs
    ) -> Self:
        """Like ``with_layer``, but skip it when the backend is already native.

        Native-preference with the capability *inferred* from the layer's
        ``provides`` - no redundant capability argument. One construction
        path spans providers (Azure's native SAS wins, the layer no-ops)::

            fs.with_layer_missing(DataUrlLayer)  # provides PRESIGNED_URLS
            fs.with_layer_missing(MetadataLayer)  # provides CUSTOM_METADATA

        Returns the current session unchanged when the capability is
        native. Raises ``ValueError`` if the layer declares no
        ``provides`` (nothing to infer - use ``with_layer``).
        """
        from .layers.native import when_missing

        wrapped = when_missing(layer, *args, **kwargs)(self._backend)
        if wrapped is self._backend:  # native: skipped, no new session
            return self
        return type(self)(wrapped, home=self._home)

    def without_layer(self, *layers: type) -> Self:
        """Return a *new* session with the given layer types bypassed.

        Walks the stack and drops every layer that is an instance of one of
        ``layers``, re-composing the rest so operations go straight past
        them - e.g. ``fs.without_layer(CacheLayer).ls()`` forces a
        cache-bypassing read. Layer types not present are a no-op, so this
        is safe to call unconditionally. The current session is untouched;
        cwd is preserved (a removable layer never changes the path
        namespace).

        Raises :class:`~storix.errors.NonRemovableLayerError` if a matched
        layer sets ``removable = False`` - a :class:`SandboxLayer` is a
        security boundary and can never be stripped.
        """
        chain: list[StorageBackend] = []
        node = self._backend
        while (inner := getattr(node, '_inner', None)) is not None:
            chain.append(node)
            node = inner
        for lyr in chain:
            if isinstance(lyr, layers) and not getattr(lyr, 'removable', True):
                raise NonRemovableLayerError(type(lyr).__name__)
        rebuilt = node  # the base backend
        for lyr in reversed(chain):
            if isinstance(lyr, layers):
                continue
            # shallow copy: only the wrapped backend changes. The chain walk
            # is duck-typed on '_inner', so the port type cannot carry the
            # attribute; Any reflects that honestly.
            clone = cast('Any', copy.copy(lyr))
            clone._inner = rebuilt  # noqa: SLF001 - core owns layer re-composition
            rebuilt = clone
        new = type(self)(rebuilt, home=self._home)
        new._cwd = self._cwd  # noqa: SLF001 - carry cwd (same namespace, same class)
        return new

    @property
    def uncached(self) -> Self:
        """This session with any ``CacheLayer`` bypassed (a fresh-read view).

        Sugar for ``without_layer(CacheLayer)``; a no-op when no cache is
        active. Use for a guaranteed-fresh read: ``fs.uncached.ls()``.
        """
        from .layers import CacheLayer

        return self.without_layer(CacheLayer)

    def scratch(
        self, *, root: StrPathLike | None = None, prefix: str = 'scratch-'
    ) -> AbstractAsyncContextManager[Storix]:
        """Ephemeral (or pinned) workspace on this session's own backend.

        Sugar for ``storix.scratch(fs.backend, ...)``; see it for the
        pin-vs-dispose semantics.
        """
        from .temporary import scratch

        return scratch(self._backend, root=root, prefix=prefix)

    # --- resolution ---

    def _resolve(self, path: StrPathLike | None = None) -> StorixPath:
        """Funnel every user path through the lexical pipeline."""
        if path is None:
            return self._cwd
        return pathops.resolve(path, cwd=self._cwd, home=self._home)

    def resolve(self, path: StrPathLike | None = None) -> StorixPath:
        """Absolute session path for ``path`` (cwd/``~``/``..`` applied).

        This is the **navigable, bookmarkable** form - a plain port path
        you can hand back to ``cd``/``cat``/anything::

            here = fs.resolve()  # '/raw/videos'
            await fs.cd('/tmp')
            await fs.cd(here)  # back to the bookmark

        Stable within a session (and across sessions built the same way).
        For an *external* reference to the object, use ``locate``.
        """
        return self._resolve(path)

    def locate(self, path: StrPathLike | None = None) -> str:
        """Fully-qualified physical locator for a path - a URI.

        For *external* reference (audit records, logs, other tools):
        where the path actually lives, resolved through any sandbox to
        the real backend location (``file:///srv/data/x``,
        ``abfss://c@acct.dfs...net/x``).

        Not a port path - you cannot ``cd`` to it (and by design a
        sandboxed session must not navigate to a real path above its
        root). To navigate, use ``resolve``; to rebuild a session *from*
        a locator, the URI factory (roadmap 0.3.0).
        """
        return self._backend.locate(self._resolve(path))

    async def _ensure_parent(self, path: StorixPath) -> None:
        """Raise unless ``path``'s parent exists and is a directory."""
        parent = path.parent
        raw = await self._backend.stat(parent)
        if raw.kind is not PathKind.DIRECTORY:
            raise NotADirectoryError(parent)

    def _ensure_capability(self, capability: Capability) -> None:
        """Raise unless the backend advertises the capability."""
        if not self._backend.capabilities.supports(capability):
            raise UnsupportedOperationError(capability)

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

    async def scandir(
        self,
        path: StrPathLike | None = None,
        *,
        all: bool = False,
    ) -> AsyncIterator[DirEntry]:
        """Lazily list a directory as rich entries (after ``os.scandir``).

        Yields a :class:`~storix.models.DirEntry` per child - name,
        absolute path, kind, and any size the listing carried for free -
        in backend order, unsorted (sorting would force the whole
        directory to materialize; a caller sorts if it wants to, as ``sx``
        does for display). Mirrors ``ls`` semantics otherwise: listing a
        file yields that one entry, and hidden (dot-prefixed) entries are
        excluded unless ``all`` is set. The lazy, rich sibling of ``ls``
        (names only) and ``iterdir`` (lazy names).

        Args:
            path: Directory (or file) to list; the session cwd when None.
            all: Include hidden (dot-prefixed) entries.

        Raises:
            PathNotFoundError: If ``path`` does not exist.
        """
        target = self._resolve(path)
        raw = await self._backend.stat(target)
        if raw.kind is PathKind.FILE:
            yield DirEntry(name=target.name, path=target, kind=raw.kind, size=raw.size)
            return
        async for entry in self._backend.list_dir(target):
            if not all and pathops.is_hidden(entry.name):
                continue
            yield DirEntry(
                name=entry.name,
                path=target / entry.name,
                kind=PathKind.DIRECTORY if entry.is_dir else PathKind.FILE,
                size=entry.size,
            )

    async def iterdir(
        self,
        path: StrPathLike | None = None,
        *,
        all: bool = False,
    ) -> AsyncIterator[StorixPath]:
        """Lazily list a directory as absolute paths (after ``Path.iterdir``).

        The lazy-names sibling of ``ls`` and sugar over ``scandir``: yields
        absolute, session-resolved :class:`StorixPath`s in backend order,
        hidden entries excluded unless ``all`` is set.

        Args:
            path: Directory (or file) to list; the session cwd when None.
            all: Include hidden (dot-prefixed) entries.

        Raises:
            PathNotFoundError: If ``path`` does not exist.
        """
        async for entry in self.scandir(path, all=all):
            yield entry.path

    async def is_empty(self, path: StrPathLike | None = None) -> bool:
        """Whether a directory holds no entries at all (hidden included).

        Pulls only the first entry from the listing and stops - one round
        trip, no full read. Counts *any* entry, including hidden ones: a
        directory holding only a dotfile is not empty (``rmdir`` would fail
        on it), so this ignores the hidden filter ``ls``/``scandir`` apply.

        Args:
            path: Directory to test; the session cwd when None.

        Raises:
            PathNotFoundError: If ``path`` does not exist.
            NotADirectoryError: If ``path`` is a file.
        """
        async for _ in self._backend.list_dir(self._resolve(path)):
            return False
        return True

    async def ls(
        self,
        path: StrPathLike | None = None,
        *,
        all: bool = False,
        abs: bool = False,
    ) -> list[StorixPath]:
        """List a directory (hidden entries excluded unless ``all=True``).

        Like unix ls, listing a file returns the file itself. Names only;
        for each entry's kind and size use ``scandir``, and for a lazy
        stream of names use ``iterdir``.
        """
        return [
            entry.path if abs else StorixPath(entry.name)
            async for entry in self.scandir(path, all=all)
        ]

    async def cat(self, path: StrPathLike, /, *paths: StrPathLike) -> bytes:
        """Read one or more files, concatenated in argument order."""
        targets = [self._resolve(p) for p in (path, *paths)]
        parts = await gather(*(self._backend.read(target) for target in targets))
        return b''.join(parts)

    async def stream(
        self,
        path: StrPathLike,
        /,
        *paths: StrPathLike,
        chunk_size: int | None = None,
    ) -> AsyncIterator[bytes]:
        """Stream file contents in chunks - the streaming form of ``cat``.

        Multiple paths concatenate in order, chunk by chunk. Streaming-native
        backends use bounded memory however large the files; a whole-object
        backend fallback may materialize a file before splitting it. Feeds
        straight into e.g. FastAPI's ``StreamingResponse``. Range reads
        (``head -c``/seek) are a planned port extension.

        Args:
            path: The first (or only) file to stream.
            paths: Further files, concatenated after ``path`` in order.
            chunk_size: Maximum yielded chunk size. ``None`` selects each
                backend's preferred default. Smaller native chunks may pass
                through unchanged; chunk boundaries carry no meaning.

        Raises:
            ValueError: If ``chunk_size`` is zero or negative.
            PathNotFoundError: If any requested path does not exist.
            IsADirectoryError: If any requested path is a directory.
        """
        validate_chunk_size(chunk_size)
        for target in [self._resolve(p) for p in (path, *paths)]:
            async for chunk in self._backend.read_stream(target, chunk_size=chunk_size):
                yield chunk

    async def stat(self, path: StrPathLike | None = None) -> FileProperties:
        """Return the user-facing properties of a path."""
        target = self._resolve(path)
        raw = await self._backend.stat(target)
        return FileProperties.from_raw(target.name or '/', raw)

    async def set_metadata(
        self,
        path: StrPathLike,
        metadata: Mapping[str, str],
        /,
        *,
        merge: bool = False,
    ) -> None:
        """Replace (default) or merge a file's custom metadata.

        Replace costs one backend request; ``merge=True`` stats first
        (read-merge-write - not atomic under concurrent writers).
        Requires ``capabilities.custom_metadata``.
        """
        self._ensure_capability(Capability.CUSTOM_METADATA)
        target = self._resolve(path)
        payload = dict(metadata)
        if merge:
            existing = (await self._backend.stat(target)).metadata or {}
            payload = {**existing, **payload}
        await self._backend.set_metadata(target, payload)

    async def url(
        self,
        path: StrPathLike | None = None,
        *,
        expires_in: int | None = None,
    ) -> str:
        """Mint a shareable URL for a file (Azure: a SAS URL).

        Requires ``capabilities.presigned_urls``. ``expires_in`` is
        advisory: ``None`` means the provider's default lifetime, and
        providers without expiring links ignore it.
        """
        self._ensure_capability(Capability.PRESIGNED_URLS)
        return await self._backend.make_url(self._resolve(path), expires_in=expires_in)

    async def data_url(self, path: StrPathLike | None = None) -> str:
        """Return the file inlined as a base64 ``data:`` URL (any backend)."""
        from storix.utils import to_data_url

        return to_data_url(buf=await self._backend.read(self._resolve(path)))

    async def du(self, path: StrPathLike | None = None) -> int:
        """Total *content* size in bytes of the tree rooted at ``path``.

        Apparent bytes, like ``du -sb`` on files: the sum of file sizes.
        GNU du's default output differs by design - it counts allocated
        filesystem blocks and directory entries, concepts that do not
        exist on object stores.
        """
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
                self._backend.write(target, b'', mode='a', content_type=None)
                for target in targets
            )
        )

    async def echo(
        self,
        data: AsyncDataBuffer[str] | AsyncDataBuffer[bytes],
        path: StrPathLike,
        /,
        *,
        chunk_size: int | None = None,
        mode: EchoMode = 'w',
        content_type: str | None = None,
        metadata: Mapping[str, str] | None = None,
    ) -> None:
        """Write data into a file, creating it if missing.

        ``mode='w'`` truncates, ``mode='a'`` appends. Accepts str/bytes,
        readable file-like objects, and (async) iterables of either. Source
        boundaries are normalized into efficient backend write batches.
        ``content_type`` and ``metadata`` require the matching backend
        capability.

        Args:
            data: Complete contents or a lazy source producing them.
            path: Destination file.
            chunk_size: Maximum target write-batch size. ``None`` selects the
                backend's preferred default.
            mode: ``'w'`` to replace or ``'a'`` to append.
            content_type: Optional media type for capable backends.
            metadata: Optional replacement metadata for capable backends.

        Raises:
            ValueError: If ``chunk_size`` is zero or negative.
            UnsupportedOperationError: If requested metadata or content type
                is not supported by the backend stack.
            PathNotFoundError: If the destination parent does not exist.
            IsADirectoryError: If the destination is a directory.
        """
        validate_chunk_size(chunk_size)
        if content_type is not None:
            self._ensure_capability(Capability.CONTENT_TYPE)
        if metadata is not None:
            self._ensure_capability(Capability.CUSTOM_METADATA)
        target = self._resolve(path)
        await self._ensure_parent(target)
        await self._backend.write_stream(
            target,
            ensure_chunks(data),
            chunk_size=chunk_size,
            mode=mode,
            content_type=content_type,
            metadata=metadata,
        )

    async def mkdir(
        self, path: StrPathLike, /, *paths: StrPathLike, parents: bool = False
    ) -> None:
        """Create directories.

        ``parents=True`` is ``mkdir -p`` with both of its unix meanings:
        missing ancestors are created *and* an already-existing directory
        is a silent success (an existing file still raises). Plain mkdir
        raises ``AlreadyExistsError`` on any existing target.
        """
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
