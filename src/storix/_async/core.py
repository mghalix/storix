"""The unix-flavored engine: one stateful session over any storage backend."""
# ruff: noqa: A004 - storix error classes intentionally shadow stdlib names

from __future__ import annotations

import copy
import fnmatch
import re

from functools import partial
from itertools import batched
from typing import TYPE_CHECKING, Any, ParamSpec, Protocol, Self, cast

from storix import pathops
from storix._async._compat import concurrent
from storix._async._stream import ensure_chunks, validate_chunk_size
from storix._async.backends import generic
from storix.constants import BULK_LISTING_KEY_LIMIT, DEFAULT_CONCURRENCY
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
    from collections.abc import AsyncIterator, Callable, Iterable, Mapping, Sequence
    from contextlib import AbstractAsyncContextManager

    from storix._async.backends import StorageBackend
    from storix.types import (
        AsyncDataBuffer,
        EchoMode,
        PathKindStr,
        StrPathLike,
        WalkOrder,
    )


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


def _glob_to_regex(pattern: str) -> re.Pattern[str]:
    """Translate a pathlib-style glob into a full-match regex.

    Matched against an entry's path relative to the glob base (posix
    text). Supports ``*`` (a run of non-separator characters), ``?`` (one
    non-separator character), and ``**`` (zero or more path segments), the
    same wildcards ``pathlib.Path.glob`` understands. A plain ``*`` stops
    at a separator, so ``*.py`` matches direct children only while
    ``**/*.py`` reaches every depth.
    """
    i, n = 0, len(pattern)
    parts: list[str] = []
    while i < n:
        char = pattern[i]
        if char == '*':
            if i + 1 < n and pattern[i + 1] == '*':
                i += 2
                if i < n and pattern[i] == '/':
                    i += 1
                    parts.append('(?:[^/]+/)*')  # '**/' spans zero or more dirs
                else:
                    parts.append('.*')  # trailing '**' spans the rest
            else:
                parts.append('[^/]*')
                i += 1
        elif char == '?':
            parts.append('[^/]')
            i += 1
        else:
            parts.append(re.escape(char))
            i += 1
    return re.compile('(?s:' + ''.join(parts) + ')')


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

    async def empty_children(
        self,
        path: StrPathLike | None = None,
        *,
        names: Iterable[str] | None = None,
    ) -> dict[str, bool]:
        """Emptiness of a directory's immediate child directories, in one pass.

        The bulk sibling of ``is_empty`` (the point query): the folder-glyph
        need for a whole listing. When the backend advertises ``bulk_listing``
        and the subtree stays within the key bound, one recursive listing of
        ``path`` answers every child at once (grouping the descendant keys by
        immediate child, all path logic here in the core) - N round trips
        collapse to one. Otherwise it falls back to a concurrent per-child
        ``is_empty`` (the portable floor); correctness never depends on the
        fast path, only latency does. The capability gate is silent: a
        backend without it is never an error, just the slower path.

        Args:
            path: Directory whose children to test; the session cwd when None.
            names: The immediate child directory names to report on. Omit to
                report on every immediate child directory (one extra listing
                to discover them); a caller that already listed - as ``sx``
                does to render the entries - passes the names it has, so no
                listing is repeated.

        Returns:
            A mapping of child directory name to whether that child is empty.
            Empty when there are no children to report on.

        Raises:
            PathNotFoundError: If ``path`` does not exist.
            NotADirectoryError: If ``path`` is a file.
        """
        directory = self._resolve(path)
        if names is None:
            children = [
                entry.name
                async for entry in self._backend.list_dir(directory)
                if entry.is_dir
            ]
        else:
            children = list(names)
        if not children:
            return {}
        if self._backend.capabilities.supports(Capability.BULK_LISTING):
            nonempty = await self._nonempty_children(directory)
            if nonempty is not None:
                return {name: name not in nonempty for name in children}
        results = await concurrent(
            partial(self.is_empty, directory / name) for name in children
        )
        return dict(zip(children, results, strict=True))

    async def _nonempty_children(self, directory: StorixPath) -> set[str] | None:
        """Immediate children that hold descendants, from one recursive listing.

        Groups the backend's raw descendant keys by their immediate-child
        component: a descendant two or more levels below ``directory`` proves
        that child non-empty. Returns None to signal a fall back to the
        concurrent floor when the listing exceeds ``BULK_LISTING_KEY_LIMIT``,
        so a prefix holding millions of keys is never pulled whole.
        """
        nonempty: set[str] = set()
        budget = BULK_LISTING_KEY_LIMIT
        async for descendant in self._backend.list_tree(directory):
            if budget <= 0:
                return None
            budget -= 1
            relative = descendant.relative_to(directory)
            # a descendant below an immediate child (its parent is a named
            # subdirectory, not '.') proves that child non-empty; a direct
            # child of ``directory`` does not
            if relative.parent.name:
                nonempty.add(relative.parts[0])
        return nonempty

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

    async def _list_children(self, target: StorixPath, *, all: bool) -> list[DirEntry]:
        """Materialize one directory's entries, hidden-filtered like ``scandir``.

        The ``walk`` frontier thunk. Materialization is deliberate: the
        sync flavor runs thunks on a pool thread, and a lazily returned
        iterator would defer its I/O back onto the caller.

        Args:
            target: Resolved directory to list.
            all: Include hidden (dot-prefixed) entries.
        """
        return [
            DirEntry(
                name=entry.name,
                path=target / entry.name,
                kind=PathKind.DIRECTORY if entry.is_dir else PathKind.FILE,
                size=entry.size,
            )
            async for entry in self._backend.list_dir(target)
            if all or not pathops.is_hidden(entry.name)
        ]

    async def _list_level(
        self, frontier: Sequence[StorixPath], *, all: bool
    ) -> AsyncIterator[DirEntry]:
        """List one walk frontier concurrently, in stable submission order.

        The frontier execution of ADR 0028: the level's directories are
        listed through ``concurrent`` in chunks of at most
        ``DEFAULT_CONCURRENCY`` thunks, entries streaming out in frontier
        order with each listing's backend order intact. Completion timing
        never reorders results, and the first error propagates unwrapped.

        Args:
            frontier: Resolved directories forming one traversal level.
            all: Include hidden (dot-prefixed) entries.
        """
        for chunk in batched(frontier, DEFAULT_CONCURRENCY):
            listings = await concurrent(
                partial(self._list_children, directory, all=all) for directory in chunk
            )
            for listing in listings:
                for entry in listing:
                    yield entry

    async def _walk_by_level(
        self,
        target: StorixPath,
        *,
        all: bool,
        top_down: bool,
        max_depth: int | None,
    ) -> AsyncIterator[DirEntry]:
        """Emit the walk level by level (``order='level'``).

        ``top_down=True`` streams each level whole, in stable
        parent/listing order, before the next level is listed.
        ``top_down=False`` streams file leaves as levels are read and
        emits the retained directory entries deepest level first. Only
        the frontier and its listings are buffered.

        Args:
            target: Resolved directory to walk.
            all: Include hidden (dot-prefixed) entries.
            top_down: Yield a directory before its descendants when True,
                after them when False.
            max_depth: Deepest level to include; None means unbounded.
        """
        retained: list[list[DirEntry]] = []
        frontier: list[StorixPath] = [target] if max_depth != 0 else []
        depth = 0
        while frontier:
            depth += 1
            descend = max_depth is None or depth < max_depth
            next_frontier: list[StorixPath] = []
            level_dirs: list[DirEntry] = []
            async for entry in self._list_level(frontier, all=all):
                if not entry.is_dir:
                    yield entry
                    continue
                if descend:
                    next_frontier.append(entry.path)
                if top_down:
                    yield entry
                else:
                    level_dirs.append(entry)
            if level_dirs:
                retained.append(level_dirs)
            frontier = next_frontier
        for level in reversed(retained):
            for entry in level:
                yield entry

    async def _walk_depth_first(
        self,
        target: StorixPath,
        *,
        all: bool,
        top_down: bool,
        max_depth: int | None,
    ) -> AsyncIterator[DirEntry]:
        """Emit the walk in exact depth-first order (``order='dfs'``).

        Fetching stays level-concurrent (``_list_level``); entries buffer
        by parent as levels arrive and an explicit DFS cursor (a stack of
        per-parent positions) drains every entry whose depth-first
        position is settled once a level completes. A stall (a directory
        reached before its listing has arrived) never blocks fetching:
        the next level is listed, then the cursor resumes, so output
        streams in leftmost-spine-first bursts while total wall time
        stays that of the concurrent traversal.

        Args:
            target: Resolved directory to walk.
            all: Include hidden (dot-prefixed) entries.
            top_down: Yield a directory before its subtree when True
                (pre-order), after it when False (post-order).
            max_depth: Deepest level to include; None means unbounded.
        """
        root_len = len(target.parts)
        grouped: dict[StorixPath, list[DirEntry]] = {}
        # cursor frames: (children of one directory, next child index,
        # the directory's own entry, emitted on pop in post-order)
        stack: list[tuple[list[DirEntry], int, DirEntry | None]] = []
        pending: DirEntry | None = None
        frontier: list[StorixPath] = [target] if max_depth != 0 else []
        fetched = 0
        while frontier:
            fetched += 1
            descend = max_depth is None or fetched < max_depth
            next_frontier: list[StorixPath] = []
            async for entry in self._list_level(frontier, all=all):
                grouped.setdefault(entry.path.parent, []).append(entry)
                if entry.is_dir and descend:
                    next_frontier.append(entry.path)
            frontier = next_frontier
            if fetched == 1:
                stack.append((grouped.pop(target, []), 0, None))
            if pending is not None:  # the stalled listing just arrived
                stack.append((grouped.pop(pending.path, []), 0, pending))
                pending = None
            while stack:
                children, i, owner = stack.pop()
                if i == len(children):  # frame drained: the subtree is done
                    if not top_down and owner is not None:
                        yield owner
                    continue
                stack.append((children, i + 1, owner))
                entry = children[i]
                depth = len(entry.path.parts) - root_len
                into = entry.is_dir and (max_depth is None or depth < max_depth)
                if top_down or not into:
                    yield entry
                if not into:
                    continue
                if depth < fetched:
                    stack.append((grouped.pop(entry.path, []), 0, entry))
                else:
                    pending = entry  # its listing arrives with the next level
                    break

    async def walk(
        self,
        path: StrPathLike | None = None,
        *,
        all: bool = False,
        top_down: bool = True,
        max_depth: int | None = None,
        order: WalkOrder = 'dfs',
    ) -> AsyncIterator[DirEntry]:
        """Lazily yield every descendant entry, recursively (after ``os.walk``).

        The recursive sibling of ``scandir`` (one directory): streams a
        :class:`~storix.models.DirEntry` per descendant of ``path``, never
        the starting directory itself. Traversal is level-buffered and
        concurrent (ADR 0028): each level's directories are listed together
        through the bounded ``concurrent`` helper in chunks of at most
        ``DEFAULT_CONCURRENCY``, so a wide remote tree costs roughly the
        slowest listing per chunk instead of the sum of every directory
        latency.

        Emission order is ``order``, independent of that fetching. The
        default ``'dfs'`` is exact depth-first output, the sequence the
        sequential pre-0.4.8 walk produced: ``top_down=True`` yields a
        directory immediately followed by its whole subtree (pre-order),
        siblings in backend listing order, files and directories
        interleaved as listed; ``top_down=False`` yields each directory
        after its whole subtree (post-order), files as encountered.
        ``'level'`` yields whole levels instead, siblings contiguous in
        stable parent/listing order: ``top_down=True`` streams each level
        before the next is listed; ``top_down=False`` streams file leaves
        as levels are read and emits retained directory entries deepest
        level first. Both orders issue identical backend calls; ``'dfs'``
        buffers entries until their depth-first position is reached
        (worst case the whole tree, entries are small), ``'level'``
        buffers only the frontier and its listings.

        Hidden (dot-prefixed) entries are excluded, and hidden directories
        are neither listed nor descended into, unless ``all`` is set. See
        ``find`` for filtering and ``glob`` for pattern matching over
        this walk.

        Args:
            path: Directory to walk; the session cwd when None.
            all: Include (and descend into) hidden entries.
            top_down: Yield a directory before its descendants when True,
                after them when False.
            max_depth: Deepest level to include, counted from ``path``
                (1 = immediate children only, 0 = nothing); None means
                unbounded. Enforced before a directory is listed, so
                excluded levels cost no backend calls.
            order: Emission order: ``'dfs'`` (default) for exact
                depth-first output, ``'level'`` for whole-level output.

        Raises:
            ValueError: If ``max_depth`` is negative.
            PathNotFoundError: If ``path`` does not exist.
        """
        if max_depth is not None and max_depth < 0:
            message = f'max_depth must be non-negative, got {max_depth}'
            raise ValueError(message)
        target = self._resolve(path)
        raw = await self._backend.stat(target)
        if raw.kind is PathKind.FILE:
            # mirror scandir: walking a file yields that one entry
            yield DirEntry(name=target.name, path=target, kind=raw.kind, size=raw.size)
            return
        walker = self._walk_by_level if order == 'level' else self._walk_depth_first
        async for entry in walker(
            target, all=all, top_down=top_down, max_depth=max_depth
        ):
            yield entry

    async def find(
        self,
        path: StrPathLike | None = None,
        *,
        name: str | None = None,
        kind: PathKind | PathKindStr | None = None,
        all: bool = False,
    ) -> AsyncIterator[DirEntry]:
        """Recursively find entries, a filtered ``walk`` (after unix ``find``).

        Streams the descendants of ``path`` (pre-order) that pass the
        filters: ``name`` is a glob matched against the basename with
        ``fnmatch`` (``'*.py'``, ``'config.*'``), ``kind`` restricts to
        files or directories. Both optional - no filter yields every entry,
        exactly ``walk``. Hidden (dot-prefixed) entries, and everything under
        a hidden directory, are excluded unless ``all`` is set - so
        ``find(name='.env', all=True)`` reaches a dotfile. The power-user /
        agent search method; use ``glob`` for pathlib-style path patterns
        instead of a basename match.

        Args:
            path: Directory to search; the session cwd when None.
            name: Glob for the basename (``fnmatch``); None matches any name.
            kind: A :class:`~storix.enums.PathKind` (or its string) to keep
                only files or only directories; None matches either.
            all: Include hidden entries and descend into hidden directories.

        Raises:
            PathNotFoundError: If ``path`` does not exist.
            ValueError: If ``kind`` is not a valid ``PathKind``.
        """
        wanted = PathKind(kind) if kind is not None else None
        async for entry in self.walk(path, all=all):
            if wanted is not None and entry.kind is not wanted:
                continue
            if name is not None and not fnmatch.fnmatch(entry.name, name):
                continue
            yield entry

    async def glob(
        self, pattern: str, path: StrPathLike | None = None, *, all: bool = False
    ) -> AsyncIterator[StorixPath]:
        """Yield paths matching a glob ``pattern`` (after ``Path.glob``).

        Pattern matching over ``walk``, yielding absolute
        :class:`StorixPath`s whose location relative to ``path`` matches:
        ``*`` (a run of non-separator characters), ``?`` (one such
        character), and ``**`` (any number of directory levels), the
        pathlib wildcards. ``'*.py'`` matches direct children, ``'**/*.py'``
        every depth, ``'sub/*'`` the children of ``sub``. The path sibling
        of ``find`` (which matches a basename and yields rich entries).
        Hidden entries, and everything under a hidden directory, are excluded
        unless ``all`` is set (like ``pathlib.glob``, where a leading dot must
        be explicit).

        The whole subtree is walked and each entry tested, so a shallow
        pattern still visits every descendant; a bounded walk is a later
        optimization. Anchoring (``^``/``$``-style) and character classes
        (``[abc]``) beyond ``*``/``?``/``**`` are not supported.

        Args:
            pattern: The glob, relative to ``path`` (``'**/*.txt'``).
            path: Directory the pattern is relative to; the cwd when None.
            all: Include hidden entries and descend into hidden directories.

        Raises:
            PathNotFoundError: If ``path`` does not exist.
        """
        base = self._resolve(path)
        regex = _glob_to_regex(pattern)
        async for entry in self.walk(base, all=all):
            if regex.fullmatch(entry.path.relative_to(base).as_posix()):
                yield entry.path

    async def cat(self, path: StrPathLike, /, *paths: StrPathLike) -> bytes:
        """Read one or more files, concatenated in argument order."""
        targets = [self._resolve(p) for p in (path, *paths)]
        parts = await concurrent(
            partial(self._backend.read, target) for target in targets
        )
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
        await concurrent(
            partial(self._backend.write, target, b'', mode='a', content_type=None)
            for target in targets
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
        await concurrent(
            partial(self._backend.make_dir, target, parents=parents)
            for target in targets
        )

    # --- delete ---

    async def rm(
        self, path: StrPathLike, /, *paths: StrPathLike, recursive: bool = False
    ) -> None:
        """Delete files; with ``recursive=True`` (rm -r) also directories.

        All targets are validated before anything is deleted.
        """
        targets = [self._resolve(p) for p in (path, *paths)]
        stats = await concurrent(
            partial(self._backend.stat, target) for target in targets
        )
        for target, raw in zip(targets, stats, strict=True):
            if raw.kind is PathKind.DIRECTORY and not recursive:
                raise IsADirectoryError(target)
        await concurrent(
            partial(
                self._backend.delete_tree
                if raw.kind is PathKind.DIRECTORY
                else self._backend.delete,
                target,
            )
            for target, raw in zip(targets, stats, strict=True)
        )

    async def rmdir(self, path: StrPathLike, /, *paths: StrPathLike) -> None:
        """Delete empty directories - strict unix rmdir.

        A non-empty directory raises ``DirectoryNotEmptyError`` (use
        ``rm(recursive=True)`` for trees); a file raises
        ``NotADirectoryError``.
        """
        targets = [self._resolve(p) for p in (path, *paths)]
        stats = await concurrent(
            partial(self._backend.stat, target) for target in targets
        )
        for target, raw in zip(targets, stats, strict=True):
            if raw.kind is not PathKind.DIRECTORY:
                raise NotADirectoryError(target)
        await concurrent(partial(self._backend.delete, target) for target in targets)

    # --- move / copy ---

    async def mv(self, source: StrPathLike, /, *paths: StrPathLike) -> None:
        """Move/rename; the last argument is the destination (unix mv).

        A single source renames onto the destination (or moves *into* it
        when it is an existing directory); multiple sources require an
        existing directory destination.
        """
        sources, dst = self._split_destination('mv', source, paths)
        targets = await self._plan_destinations(sources, dst)
        await concurrent(
            partial(self._backend.move, src, target)
            for src, target in zip(sources, targets, strict=True)
        )

    async def cp(
        self, source: StrPathLike, /, *paths: StrPathLike, recursive: bool = False
    ) -> None:
        """Copy; the last argument is the destination (unix cp).

        Copying a directory requires ``recursive=True`` (cp -r), which
        overlays into existing destination directories like unix does.
        """
        sources, dst = self._split_destination('cp', source, paths)
        src_stats = await concurrent(
            partial(self._backend.stat, src) for src in sources
        )
        for src, raw in zip(sources, src_stats, strict=True):
            if raw.kind is PathKind.DIRECTORY and not recursive:
                raise IsADirectoryError(src)
        targets = await self._plan_destinations(sources, dst)
        await concurrent(
            partial(generic.copy_tree, self._backend, src, target)
            if raw.kind is PathKind.DIRECTORY
            else partial(self._backend.copy, src, target)
            for src, raw, target in zip(sources, src_stats, targets, strict=True)
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
