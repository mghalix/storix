"""CacheLayer, its per-op config, and the pluggable CacheStore backend."""

from __future__ import annotations

import dataclasses
import fnmatch
import time

from collections import OrderedDict
from typing import TYPE_CHECKING, Protocol

from storix._async._stream import validate_chunk_size
from storix.constants import DEFAULT_CACHE_NAMESPACE, DEFAULT_URL_EXPIRY_SECONDS
from storix.errors import PathNotFoundError

from .base import LayerBase


if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Mapping
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
    """Default ``CacheStore``: an in-process dict with per-key expiry.

    ``maxsize`` bounds the entry count with LRU eviction - the simple way
    to cap total memory (covers metadata growth and content alike). For
    byte-precise bounds use a size-aware store (e.g. cashews).
    """

    def __init__(self, *, maxsize: int | None = None) -> None:
        self._data: OrderedDict[str, tuple[float | None, Any]] = OrderedDict()
        self._maxsize = maxsize

    async def get(self, key: str, default: Any = None) -> Any:
        """Return the (unexpired) value for ``key``, else ``default``."""
        entry = self._data.get(key)
        if entry is None:
            return default
        deadline, value = entry
        if deadline is not None and time.monotonic() > deadline:
            self._data.pop(key, None)
            return default
        self._data.move_to_end(key)  # mark most-recently-used
        return value

    async def set(self, key: str, value: Any, *, expire: float | None = None) -> None:
        """Store ``value``; ``expire`` seconds from now if given."""
        deadline = None if expire is None else time.monotonic() + expire
        self._data[key] = (deadline, value)
        self._data.move_to_end(key)
        if self._maxsize is not None:
            while len(self._data) > self._maxsize:
                self._data.popitem(last=False)  # evict least-recently-used

    async def delete(self, key: str) -> None:
        """Drop ``key`` if present."""
        self._data.pop(key, None)

    async def delete_match(self, pattern: str) -> None:
        """Drop every key matching the glob ``pattern``."""
        for key in [k for k in self._data if fnmatch.fnmatch(k, pattern)]:
            self._data.pop(key, None)


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class CacheOp:
    """Per-operation cache settings. Fields default to the layer's.

    ``ttl`` / ``store``: inherit the ``CacheLayer`` defaults when None.
    ``max_bytes``: for ``read`` only - skip caching files larger than this.
    Build one with the :func:`cache` helper.
    """

    ttl: float | None = None
    store: CacheStore | None = None
    max_bytes: int | None = None


def cache(
    *,
    ttl: float | None = None,
    store: CacheStore | None = None,
    max_bytes: int | None = None,
) -> CacheOp:
    """Build a per-op cache spec: ``du=cache(ttl=60)``."""
    return CacheOp(ttl=ttl, store=store, max_bytes=max_bytes)


@dataclasses.dataclass(frozen=True, slots=True)
class _Op:
    """A resolved (enabled) operation: concrete store + settings."""

    store: CacheStore
    ttl: float | None
    max_bytes: int | None


class CacheLayer(LayerBase):
    """Configurable read-through cache: metadata, du, content, and URLs.

    ``metadata`` (default on) caches stat/list_dir/exists - the ops
    navigation hammers. ``du`` caches the expensive tree-size walk.
    ``read`` caches file content. ``url`` caches presigned URLs
    (TTL-only; see :meth:`make_url`). Each is ``bool | CacheOp``: ``True``
    for defaults, ``cache(ttl=.., store=.., max_bytes=..)`` to override,
    ``False`` to disable. Every mutation *through this layer* evicts the
    entries it affects (metadata: path+parent; du: ancestors; read: the
    file), so the session always sees its own writes.

    ``store``/``ttl`` are the defaults each op inherits; an op may carry
    its own (metadata in Redis, content on a bounded local store). Keys
    follow ``<namespace>[:<environment>]:<op>:<locator>`` and are keyed on
    the *physical* locator, so sessions sharing one store never collide.
    Not a capability (``provides`` stays None): compose with
    ``with_layer(CacheLayer, du=cache(ttl=60), ...)``.

    .. warning::
       Correctness assumes yours is the only writer of the store(s). The
       cache cannot see changes made *outside* this layer (another
       process, the cloud console). Pass ``ttl`` to bound staleness; the
       default ``None`` never expires and is only safe for a single owner.
    """

    def __init__(  # noqa: PLR0913 - a kw-only config surface, not a call site
        self,
        backend: StorageBackend,
        *,
        metadata: bool | CacheOp = True,
        du: bool | CacheOp = False,
        read: bool | CacheOp = False,
        url: bool | CacheOp = False,
        store: CacheStore | None = None,
        ttl: float | None = None,
        namespace: str = DEFAULT_CACHE_NAMESPACE,
        environment: str | None = None,
    ) -> None:
        super().__init__(backend)
        default_store = store or InMemoryCacheStore()
        self._segments = tuple(p for p in (namespace, environment) if p)
        self._ops: dict[str, _Op] = {}
        for name, spec in (
            ('metadata', metadata),
            ('du', du),
            ('read', read),
            ('url', url),
        ):
            resolved = self._resolve(spec, default_store, ttl)
            if resolved is not None:
                self._ops[name] = resolved

    @staticmethod
    def _resolve(
        spec: bool | CacheOp,  # noqa: FBT001 - a config union (bool|CacheOp), not a flag
        default_store: CacheStore,
        default_ttl: float | None,
    ) -> _Op | None:
        if not spec:  # False (a CacheOp is truthy)
            return None
        if spec is True:
            return _Op(store=default_store, ttl=default_ttl, max_bytes=None)
        return _Op(
            store=spec.store or default_store,
            ttl=spec.ttl if spec.ttl is not None else default_ttl,
            max_bytes=spec.max_bytes,
        )

    def _kbase(self, op: str, locator: str) -> str:
        return ':'.join((*self._segments, op, locator))

    def _key(self, op: str, path: PurePosixPath) -> str:
        # key on the *physical* locator, not the virtual path: two
        # sessions sharing one store (different sandboxes/backends) must
        # not collide on the same virtual path, and must share on the same
        # physical object. locate() is pure (no I/O) and prefix-consistent
        # (a child's locator extends its parent's), so tree eviction works.
        return self._kbase(op, self._inner.locate(path))

    # --- cached reads (each a pass-through when its op is disabled) ---

    async def stat(self, path: PurePosixPath) -> RawStat:
        """Return raw facts, cached (negatives cached as absent too)."""
        op = self._ops.get('metadata')
        if op is None:
            return await self._inner.stat(path)
        key = self._key('stat', path)
        hit = await op.store.get(key, _MISS)
        if hit is not _MISS:
            if hit is None:
                raise PathNotFoundError(path)
            return hit
        try:
            raw = await self._inner.stat(path)
        except PathNotFoundError:
            await op.store.set(key, None, expire=op.ttl)
            raise
        await op.store.set(key, raw, expire=op.ttl)
        return raw

    async def exists(self, path: PurePosixPath) -> bool:
        """Derive existence from the stat cache (shares one key)."""
        if 'metadata' not in self._ops:
            return await self._inner.exists(path)
        try:
            await self.stat(path)
        except PathNotFoundError:
            return False
        return True

    async def list_dir(self, path: PurePosixPath) -> AsyncIterator[Entry]:
        """Yield children, cached as a materialized list."""
        op = self._ops.get('metadata')
        if op is None:
            async for entry in self._inner.list_dir(path):
                yield entry
            return
        key = self._key('list', path)
        hit = await op.store.get(key, _MISS)
        if hit is not _MISS:
            for entry in hit:
                yield entry
            return
        entries = [entry async for entry in self._inner.list_dir(path)]
        await op.store.set(key, entries, expire=op.ttl)
        for entry in entries:
            yield entry

    async def du(self, path: PurePosixPath) -> int:
        """Total tree size, cached (invalidated up the ancestor chain)."""
        op = self._ops.get('du')
        if op is None:
            return await self._inner.du(path)
        key = self._key('du', path)
        hit = await op.store.get(key, _MISS)
        if hit is not _MISS:
            return hit
        value = await self._inner.du(path)
        await op.store.set(key, value, expire=op.ttl)
        return value

    async def read(self, path: PurePosixPath) -> bytes:
        """Return file content, cached (files over ``max_bytes`` skipped)."""
        op = self._ops.get('read')
        if op is None:
            return await self._inner.read(path)
        key = self._key('read', path)
        hit = await op.store.get(key, _MISS)
        if hit is not _MISS:
            return hit
        data = await self._inner.read(path)
        if op.max_bytes is None or len(data) <= op.max_bytes:
            await op.store.set(key, data, expire=op.ttl)
        return data

    async def make_url(
        self, path: PurePosixPath, *, expires_in: int | None = None
    ) -> str:
        """Return a presigned URL, cached until (before) it expires.

        Unlike the other ops this is TTL-only: a minted URL stays valid
        for its lifetime no matter how the object changes, so mutations do
        not evict it. The entry never outlives the URL - it is capped at
        the URL's lifetime (``expires_in``, or the provider default), so a
        cached URL is never served dead. ``expires_in`` is part of the key
        (different lifetimes are different URLs). Set the op's ``ttl``
        below ``expires_in`` for a safety margin.
        """
        op = self._ops.get('url')
        if op is None:
            return await self._inner.make_url(path, expires_in=expires_in)
        lifetime = expires_in if expires_in is not None else DEFAULT_URL_EXPIRY_SECONDS
        key = f'{self._key("url", path)}:{expires_in}'
        hit = await op.store.get(key, _MISS)
        if hit is not _MISS:
            return hit
        signed = await self._inner.make_url(path, expires_in=expires_in)
        cache_ttl = min(op.ttl, lifetime) if op.ttl is not None else lifetime
        await op.store.set(key, signed, expire=cache_ttl)
        return signed

    async def clear(self) -> None:
        """Drop every entry this layer owns, across its store(s).

        Scoped to the layer's ``<namespace>[:<environment>]`` prefix - a
        shared store keeps other namespaces' keys. Deletes once per
        distinct store when ops share one.
        """
        prefix = ':'.join(self._segments)
        pattern = f'{prefix}:*' if prefix else '*'
        seen: set[int] = set()
        for op in self._ops.values():
            if id(op.store) in seen:
                continue
            seen.add(id(op.store))
            await op.store.delete_match(pattern)

    @property
    def enabled(self) -> tuple[str, ...]:
        """Names of the ops this layer caches, e.g. ``('metadata', 'du')``."""
        return tuple(self._ops)

    def store_names(self) -> tuple[str, ...]:
        """Distinct store class names backing the enabled ops (in order)."""
        names: dict[str, None] = {}
        for op in self._ops.values():
            names[type(op.store).__name__] = None
        return tuple(names)

    # --- eviction (per enabled op, in that op's store) ---

    async def _evict(self, path: PurePosixPath) -> None:
        if (op := self._ops.get('metadata')) is not None:
            await op.store.delete(self._key('stat', path))
            await op.store.delete(self._key('list', path))
            await op.store.delete(self._key('list', path.parent))
        if (op := self._ops.get('read')) is not None:
            await op.store.delete(self._key('read', path))
        if (op := self._ops.get('du')) is not None:
            await self._evict_du_chain(op, path)

    async def _evict_tree(self, path: PurePosixPath) -> None:
        locator = self._inner.locate(path)
        if (op := self._ops.get('metadata')) is not None:
            await op.store.delete(self._key('stat', path))
            await op.store.delete(self._key('list', path))
            await op.store.delete_match(f'{self._kbase("stat", locator)}/*')
            await op.store.delete_match(f'{self._kbase("list", locator)}/*')
            await op.store.delete(self._key('list', path.parent))
        if (op := self._ops.get('read')) is not None:
            await op.store.delete(self._key('read', path))
            await op.store.delete_match(f'{self._kbase("read", locator)}/*')
        if (op := self._ops.get('du')) is not None:
            await op.store.delete_match(f'{self._kbase("du", locator)}/*')
            await self._evict_du_chain(op, path)

    async def _evict_du_chain(self, op: _Op, path: PurePosixPath) -> None:
        # a write changes du of the path and every ancestor
        node = path
        while True:
            await op.store.delete(self._key('du', node))
            if str(node) == '/':
                return
            node = node.parent

    # --- mutations evict, then delegate ---

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
        """Write a bounded stream, then evict the affected entries.

        Raises:
            ValueError: If ``chunk_size`` is zero or negative.
        """
        validate_chunk_size(chunk_size)
        await self._inner.write_stream(
            path,
            data,
            chunk_size=chunk_size,
            mode=mode,
            content_type=content_type,
            metadata=metadata,
        )
        await self._evict(path)

    async def delete(self, path: PurePosixPath) -> None:
        """Delete a leaf, then evict it."""
        await self._inner.delete(path)
        await self._evict(path)

    async def delete_tree(self, path: PurePosixPath) -> None:
        """Delete a tree, then evict every entry beneath it."""
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
