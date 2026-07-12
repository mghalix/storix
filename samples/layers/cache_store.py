"""Pluggable cache backends for CacheLayer.

CacheLayer caches metadata in an in-process dict by default. Pass a
``store`` - anything satisfying the ``CacheStore`` protocol (four async
methods shaped like cashews) - to share one cache across app instances
(Redis, a database, ...) or to add bounds/eviction policy.

A ``cashews.Cache`` fits ``CacheStore`` directly (get/set/delete/
delete_match with matching shapes), so in your project:

    from cashews import Cache
    cache = Cache(); cache.setup('redis://localhost')
    fs = Storix(CacheLayer(backend, store=cache, ttl=30))

The example below uses a tiny custom store so it runs offline.

Run:  uv run python samples/layers/cache_store.py
"""

import asyncio

from typing import Any

from storix.aio import CacheLayer, Storix
from storix.aio.backends import MemoryBackend


class LoggingStore:
    """A CacheStore that prints every hit/miss - handy for tuning.

    Implement these four coroutines and you have a backend; here we wrap
    a plain dict, but the same shape fronts Redis, memcached, etc.
    """

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    async def get(self, key: str, default: Any = None) -> Any:
        hit = key in self._data
        print(f'  cache {"HIT " if hit else "miss"} {key}')
        return self._data.get(key, default)

    async def set(self, key: str, value: Any, *, expire: float | None = None) -> None:
        self._data[key] = value

    async def delete(self, key: str) -> None:
        self._data.pop(key, None)

    async def delete_match(self, pattern: str) -> None:
        import fnmatch

        for key in [k for k in self._data if fnmatch.fnmatch(k, pattern)]:
            self._data.pop(key, None)


async def main() -> None:
    fs = Storix(CacheLayer(MemoryBackend(), store=LoggingStore(), ttl=60))
    await fs.mkdir('/docs')
    await fs.touch('/docs/a.txt')

    print('first ls  (fills the cache):')
    await fs.ls('/docs')
    print('second ls (served from the store):')
    await fs.ls('/docs')
    print('after touch (mutation evicts, next ls re-reads):')
    await fs.touch('/docs/b.txt')
    print(sorted(p.name for p in await fs.ls('/docs')))


if __name__ == '__main__':
    asyncio.run(main())
