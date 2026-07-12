"""CacheLayer and the pluggable CacheStore backend."""

from __future__ import annotations

import fnmatch
import time

from typing import TYPE_CHECKING, Protocol

from storix.constants import DEFAULT_CACHE_NAMESPACE
from storix.errors import PathNotFoundError

from .base import LayerBase


if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable, Mapping
    from pathlib import PurePosixPath
    from typing import Any

    from storix.models import Entry, RawStat
    from storix.types import EchoMode

    from ..backends import StorageBackend


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

    Caching *more* operations is a subclass, not a config flag - each op
    has its own invalidation. Use the protected primitives (``_cached``,
    ``_key``, ``_store``, ``_evict``); see ``samples/layers/`` for a
    ``du``-caching subclass.

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
        namespace: str = DEFAULT_CACHE_NAMESPACE,
        environment: str | None = None,
    ) -> None:
        super().__init__(backend)
        self._store: CacheStore = store or InMemoryCacheStore()
        self._ttl = ttl
        # key layout follows the ``sdk:env:resource:id`` convention:
        # <namespace>[:<environment>]:<op>:<locator>
        self._segments = tuple(p for p in (namespace, environment) if p)

    def _kbase(self, op: str, locator: str) -> str:
        return ':'.join((*self._segments, op, locator))

    def _key(self, op: str, path: PurePosixPath) -> str:
        # key on the *physical* locator, not the virtual path: two
        # sessions sharing one store (different sandboxes/backends) must
        # not collide on the same virtual path, and must share on the same
        # physical object. locate() is pure (no I/O) and prefix-consistent
        # (a child's locator extends its parent's), so tree eviction works.
        return self._kbase(op, self._inner.locate(path))

    async def _cached(
        self, op: str, path: PurePosixPath, fetch: Callable[[], Any]
    ) -> Any:
        """Read-through a scalar op: cache hit, or fetch-then-store.

        The extension point for subclasses caching more operations - call
        it from the read method, and extend ``_evict``/``_evict_tree``
        with that op's key so mutations invalidate it.
        """
        key = self._key(op, path)
        hit = await self._store.get(key, _MISS)
        if hit is not _MISS:
            return hit
        value = await fetch()
        await self._store.set(key, value, expire=self._ttl)
        return value

    async def _evict(self, path: PurePosixPath) -> None:
        await self._store.delete(self._key('stat', path))
        await self._store.delete(self._key('list', path))  # the path's listing
        await self._store.delete(self._key('list', path.parent))  # parent membership

    async def _evict_tree(self, path: PurePosixPath) -> None:
        locator = self._inner.locate(path)
        await self._store.delete(self._key('stat', path))
        await self._store.delete(self._key('list', path))
        await self._store.delete_match(f'{self._kbase("stat", locator)}/*')
        await self._store.delete_match(f'{self._kbase("list", locator)}/*')
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
