"""Port middleware: backends that wrap backends.

A layer implements the same ``StorageBackend`` protocol it consumes, so
layers compose with backends and with each other. Cross-cutting concerns
(sandboxing now; caching, metadata, observability later) live here
rather than inside the core or any backend.
"""
# ruff: noqa: A004 - storix error classes intentionally shadow stdlib names

from __future__ import annotations

import dataclasses
import fnmatch
import time

from typing import TYPE_CHECKING, Protocol

from storix import pathops
from storix._async._stream import ensure_chunks
from storix.constants import DEFAULT_CACHE_KEY_PREFIX
from storix.enums import Capability, PathKind
from storix.errors import (
    IsADirectoryError,
    PathError,
    PathNotFoundError,
    PermissionDeniedError,
)
from storix.serialization import json_dumpb, json_loadb
from storix.types import StorixPath


if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable, Mapping
    from pathlib import PurePosixPath
    from typing import Any, ClassVar

    from storix.models import Capabilities, Entry, RawStat
    from storix.types import EchoMode, StrPathLike

    from .backends import StorageBackend

    BoundLayer = Callable[[StorageBackend], StorageBackend]


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

    def locate(self, path: PurePosixPath) -> str:
        """Fully-qualified physical locator for a port path."""
        return self._inner.locate(path)

    async def close(self) -> None:
        """Release the inner backend's resources."""
        await self._inner.close()


def when_missing(capability: Capability, layer: BoundLayer) -> BoundLayer:
    """Apply ``layer`` only when the backend lacks ``capability``.

    The native-preference combinator: the same construction code works
    across providers, wrapping capability-poor backends and
    short-circuiting entirely (zero overhead, native behavior) on
    backends that already advertise the capability::

        Storix(backend, layers=[when_missing(Capability.PRESIGNED_URLS, DataUrlLayer)])

    Prefer-the-layer is expressed by not using the combinator.
    """

    def build(backend: StorageBackend) -> StorageBackend:
        if backend.capabilities.supports(capability):
            return backend
        return layer(backend)

    return build


class DataUrlLayer(LayerBase):
    """``url()`` everywhere, via ``data:`` URLs.

    Upgrades ``presigned_urls`` by inlining the entire file as base64
    into the URL itself. Fine for small assets and HTML embedding;
    *terrible* for LLM/agent contexts (a 1 MiB file becomes a ~1.4 M
    character URL) and for anything large. Prefer native presigned URLs
    when the backend has them::

        fs.with_layer_missing(DataUrlLayer)  # capability inferred

    ``expires_in`` is ignored - data URLs cannot expire (the advisory
    contract permits this).
    """

    provides = Capability.PRESIGNED_URLS

    def __init__(self, backend: StorageBackend) -> None:
        super().__init__(backend)
        self.capabilities = dataclasses.replace(
            backend.capabilities, presigned_urls=True
        )

    async def make_url(
        self, path: PurePosixPath, *, expires_in: int | None = None
    ) -> str:
        """Inline the file as a base64 ``data:`` URL."""
        del expires_in  # data URLs cannot expire
        from storix.utils import to_data_url

        return to_data_url(buf=await self._inner.read(path))


class MetadataLayer(LayerBase):
    """Custom metadata for backends without native support, via a sidecar.

    Upgrades ``custom_metadata`` by keeping a hidden JSON table
    (``/.storix-meta.json``) *inside the wrapped backend itself*, so it
    works over any backend and travels with the data. Port semantics are
    preserved exactly (replace; ``{}`` clears; ``None`` preserves on
    append) - the conformance suite runs against this layer.

    Honest limits: the sidecar is last-writer-wins under concurrent
    writers; every stat/metadata operation costs one extra sidecar read;
    external writes that bypass the layer leave stale entries (a delete
    through the layer cleans up). ``copy`` does not carry metadata, per
    the port contract. Prefer native metadata when available::

        fs.with_layer_missing(MetadataLayer)  # capability inferred

    ``serialize``/``deserialize`` swap the sidecar codec (default: stdlib
    json). They are object<->*bytes* callables (not str), so pass
    ``orjson.dumps``/``orjson.loads`` or a custom ``.dumpb``/``.loads`` -
    NOT ``json.dumps`` (which returns str).
    """

    provides = Capability.CUSTOM_METADATA
    _SIDECAR = StorixPath('/.storix-meta.json')

    def __init__(
        self,
        backend: StorageBackend,
        *,
        serialize: Callable[[Any], bytes] = json_dumpb,
        deserialize: Callable[[bytes], Any] = json_loadb,
    ) -> None:
        super().__init__(backend)
        self.capabilities = dataclasses.replace(
            backend.capabilities, custom_metadata=True
        )
        self._serialize = serialize
        self._deserialize = deserialize

    async def _load(self) -> dict[str, dict[str, str]]:
        try:
            raw = await self._inner.read(self._SIDECAR)
        except PathNotFoundError:
            return {}
        return self._deserialize(raw) if raw else {}

    async def _save(self, table: dict[str, dict[str, str]]) -> None:
        if table:
            payload = self._serialize(table)
            await self._inner.write(
                self._SIDECAR, ensure_chunks(payload), mode='w', content_type=None
            )
        elif await self._inner.exists(self._SIDECAR):
            await self._inner.delete(self._SIDECAR)

    async def write(
        self,
        path: PurePosixPath,
        data: AsyncIterator[bytes],
        *,
        mode: EchoMode,
        content_type: str | None,
        metadata: Mapping[str, str] | None = None,
    ) -> None:
        """Write content, then maintain the sidecar per port semantics."""
        await self._inner.write(path, data, mode=mode, content_type=content_type)
        key = str(path)
        if metadata is None and mode == 'a':
            return  # None preserves on append
        table = await self._load()
        if metadata:
            table[key] = dict(metadata)
        else:  # create/truncate without metadata, or explicit {} clear
            table.pop(key, None)
        await self._save(table)

    async def stat(self, path: PurePosixPath) -> RawStat:
        """Merge sidecar metadata into the inner stat."""
        if path == self._SIDECAR:  # the sidecar is invisible to consumers
            raise PathNotFoundError(path)
        raw = await self._inner.stat(path)
        if raw.kind is not PathKind.FILE:
            return raw
        table = await self._load()
        stored = table.get(str(path))
        return dataclasses.replace(raw, metadata=dict(stored) if stored else None)

    async def exists(self, path: PurePosixPath) -> bool:
        """Whether anything lives at ``path`` (the sidecar reads absent)."""
        if path == self._SIDECAR:
            return False
        return await self._inner.exists(path)

    async def read_stream(self, path: PurePosixPath) -> AsyncIterator[bytes]:
        """Stream a file's contents (the sidecar is not readable)."""
        if path == self._SIDECAR:
            raise PathNotFoundError(path)
        async for chunk in self._inner.read_stream(path):
            yield chunk

    async def list_dir(self, path: PurePosixPath) -> AsyncIterator[Entry]:
        """Yield children, hiding the sidecar from its parent directory."""
        async for entry in self._inner.list_dir(path):
            if path / entry.name != self._SIDECAR:
                yield entry

    async def du(self, path: PurePosixPath) -> int:
        """Tree size excluding the sidecar (walks via this layer)."""
        from .backends import generic

        return await generic.du(self, path)

    async def set_metadata(
        self, path: PurePosixPath, metadata: Mapping[str, str]
    ) -> None:
        """Replace a file's metadata in the sidecar."""
        raw = await self._inner.stat(path)  # raises for missing paths
        if raw.kind is not PathKind.FILE:
            raise IsADirectoryError(path)
        table = await self._load()
        if metadata:
            table[str(path)] = dict(metadata)
        else:
            table.pop(str(path), None)
        await self._save(table)

    async def delete(self, path: PurePosixPath) -> None:
        """Delete the leaf and drop its sidecar entry."""
        await self._inner.delete(path)
        table = await self._load()
        if table.pop(str(path), None) is not None:
            await self._save(table)

    async def delete_tree(self, path: PurePosixPath) -> None:
        """Delete the tree and every sidecar entry beneath it."""
        await self._inner.delete_tree(path)
        prefix = str(path).rstrip('/') + '/'
        table = await self._load()
        kept = {
            key: value
            for key, value in table.items()
            if key != str(path) and not key.startswith(prefix)
        }
        if kept != table:
            await self._save(kept)

    async def move(self, src: PurePosixPath, dst: PurePosixPath) -> None:
        """Move content and re-key sidecar entries (trees included)."""
        await self._inner.move(src, dst)
        src_key, dst_key = str(src), str(dst)
        src_prefix = src_key.rstrip('/') + '/'
        table = await self._load()
        moved: dict[str, dict[str, str]] = {}
        for key in list(table):
            if key == src_key:
                moved[dst_key] = table.pop(key)
            elif key.startswith(src_prefix):
                moved[dst_key + key.removeprefix(src_key)] = table.pop(key)
        if moved:
            table.update(moved)
            await self._save(table)


# distinct from a cached ``None`` (a known-absent path)
_MISS: Any = object()


class CacheStore(Protocol):
    """Cashews-shaped async cache backend for ``CacheLayer``.

    Four coroutine methods; the in-memory default ships. Pass any object
    that provides them for a shared/persistent cache - a ``cashews.Cache``
    fits directly. Return types are intentionally loose (``Any``) so real
    caches (whose ``set``/``delete`` return bool/int) satisfy it
    structurally with no adapter.
    """

    async def get(self, key: str, default: Any = None) -> Any:
        """Return the value for ``key``, or ``default`` on miss."""
        ...

    async def set(self, key: str, value: Any, *, expire: float | None = None) -> Any:
        """Store ``value`` under ``key``, expiring after ``expire`` seconds."""
        ...

    async def delete(self, key: str) -> Any:
        """Drop ``key``."""
        ...

    async def delete_match(self, pattern: str) -> Any:
        """Drop every key matching a glob ``pattern`` (e.g. ``stat:/a/*``)."""
        ...


class InMemoryCacheStore:
    """Default ``CacheStore``: an in-process dict with per-key expiry."""

    def __init__(self) -> None:
        self._data: dict[str, tuple[float | None, Any]] = {}

    async def get(self, key: str, default: Any = None) -> Any:
        """Return the (unexpired) value for ``key``, else ``default``."""
        entry = self._data.get(key)
        if entry is None:
            return default
        deadline, value = entry
        if deadline is not None and time.monotonic() > deadline:
            self._data.pop(key, None)
            return default
        return value

    async def set(self, key: str, value: Any, *, expire: float | None = None) -> None:
        """Store ``value``; ``expire`` seconds from now if given."""
        deadline = None if expire is None else time.monotonic() + expire
        self._data[key] = (deadline, value)

    async def delete(self, key: str) -> None:
        """Drop ``key`` if present."""
        self._data.pop(key, None)

    async def delete_match(self, pattern: str) -> None:
        """Drop every key matching the glob ``pattern``."""
        for key in [k for k in self._data if fnmatch.fnmatch(k, pattern)]:
            self._data.pop(key, None)


class CacheLayer(LayerBase):
    """Read-through cache for metadata: stat / list_dir / exists.

    Serves the operations navigation hammers (``ls``, ``cd``, ``tree``)
    from memory after the first hit - a big win on network backends where
    each is a round-trip. ``read`` stays a pass-through (content is not
    cached in this version).

    Every mutation *through this layer* evicts the entries it affects, so
    the session always sees its own writes. Not a capability (``provides``
    stays None): compose with ``with_layer(CacheLayer, ttl=...)``.

    ``store`` is the cache backend (default: in-process
    :class:`InMemoryCacheStore`). Pass a shared store - a ``cashews.Cache``
    or any :class:`CacheStore` - so multiple app instances share one
    metadata cache. ``ttl`` (seconds) applies to every entry.

    .. warning::
       Correctness assumes yours is the only writer of this store. The
       cache cannot see changes made *outside* this layer (another
       process, a second storix session, the cloud console). If the store
       has other writers, pass ``ttl`` to bound how long a stale entry can
       live - the default ``None`` never expires and is only safe for a
       single owner.
    """

    def __init__(
        self,
        backend: StorageBackend,
        *,
        store: CacheStore | None = None,
        ttl: float | None = None,
        prefix: str = DEFAULT_CACHE_KEY_PREFIX,
    ) -> None:
        super().__init__(backend)
        self._store: CacheStore = store or InMemoryCacheStore()
        self._ttl = ttl
        self._prefix = prefix

    def _key(self, op: str, path: PurePosixPath) -> str:
        # key on the *physical* locator, not the virtual path: two
        # sessions sharing one store (different sandboxes/backends) must
        # not collide on the same virtual path, and must share on the same
        # physical object. locate() is pure (no I/O) and prefix-consistent
        # (a child's locator extends its parent's), so tree eviction works.
        return f'{self._prefix}:{op}:{self._inner.locate(path)}'

    async def _evict(self, path: PurePosixPath) -> None:
        await self._store.delete(self._key('stat', path))
        await self._store.delete(self._key('list', path))  # the path's listing
        await self._store.delete(self._key('list', path.parent))  # parent membership

    async def _evict_tree(self, path: PurePosixPath) -> None:
        locator = self._inner.locate(path)
        await self._store.delete(self._key('stat', path))
        await self._store.delete(self._key('list', path))
        await self._store.delete_match(f'{self._prefix}:stat:{locator}/*')
        await self._store.delete_match(f'{self._prefix}:list:{locator}/*')
        await self._store.delete(self._key('list', path.parent))

    # --- cached reads ---

    async def stat(self, path: PurePosixPath) -> RawStat:
        """Return raw facts, cached (negatives cached as absent too)."""
        hit = await self._store.get(self._key('stat', path), _MISS)
        if hit is not _MISS:
            if hit is None:
                raise PathNotFoundError(path)
            return hit
        try:
            raw = await self._inner.stat(path)
        except PathNotFoundError:
            await self._store.set(self._key('stat', path), None, expire=self._ttl)
            raise
        await self._store.set(self._key('stat', path), raw, expire=self._ttl)
        return raw

    async def exists(self, path: PurePosixPath) -> bool:
        """Derive existence from the stat cache (shares one key)."""
        try:
            await self.stat(path)
        except PathNotFoundError:
            return False
        return True

    async def list_dir(self, path: PurePosixPath) -> AsyncIterator[Entry]:
        """Yield children, cached as a materialized list."""
        hit = await self._store.get(self._key('list', path), _MISS)
        if hit is not _MISS:
            for entry in hit:
                yield entry
            return
        entries = [entry async for entry in self._inner.list_dir(path)]
        await self._store.set(self._key('list', path), entries, expire=self._ttl)
        for entry in entries:
            yield entry

    # --- mutations evict, then delegate ---

    async def write(
        self,
        path: PurePosixPath,
        data: AsyncIterator[bytes],
        *,
        mode: EchoMode,
        content_type: str | None,
        metadata: Mapping[str, str] | None = None,
    ) -> None:
        """Write, then evict the path and its parent listing."""
        await self._inner.write(
            path, data, mode=mode, content_type=content_type, metadata=metadata
        )
        await self._evict(path)

    async def delete(self, path: PurePosixPath) -> None:
        """Delete a leaf, then evict it and its parent listing."""
        await self._inner.delete(path)
        await self._evict(path)

    async def delete_tree(self, path: PurePosixPath) -> None:
        """Delete a tree, then evict every cached entry beneath it."""
        await self._inner.delete_tree(path)
        await self._evict_tree(path)

    async def make_dir(self, path: PurePosixPath, *, parents: bool) -> None:
        """Create a directory, then evict it and its parent listing."""
        await self._inner.make_dir(path, parents=parents)
        await self._evict(path)

    async def move(self, src: PurePosixPath, dst: PurePosixPath) -> None:
        """Move, then evict both subtrees."""
        await self._inner.move(src, dst)
        await self._evict_tree(src)
        await self._evict_tree(dst)

    async def copy(self, src: PurePosixPath, dst: PurePosixPath) -> None:
        """Copy, then evict the destination."""
        await self._inner.copy(src, dst)
        await self._evict(dst)

    async def set_metadata(
        self, path: PurePosixPath, metadata: Mapping[str, str]
    ) -> None:
        """Replace metadata, then evict the path's cached stat."""
        await self._inner.set_metadata(path, metadata)
        await self._evict(path)
