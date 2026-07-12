"""Cache MORE than metadata by subclassing CacheLayer.

The built-in CacheLayer caches stat/list_dir/exists - the navigation
hot path. Other operations have *different* invalidation, so you add
them by subclassing (not a config flag): override the read method to go
through ``_cached``, and extend ``_evict`` so mutations drop the entry.

Here we cache ``du`` (an expensive tree walk). ``du(/a)`` is invalidated
by *any* write beneath ``/a``, i.e. the size of every ancestor changes -
so eviction drops the du entry for the path and all its parents.

Run:  uv run python samples/layers/extend_cache.py
"""

import asyncio

from pathlib import PurePosixPath

from storix.aio import CacheLayer, Storix
from storix.aio.backends import MemoryBackend


class DuCacheLayer(CacheLayer):
    """CacheLayer that also caches ``du`` (with ancestor-aware eviction)."""

    async def du(self, path: PurePosixPath) -> int:
        return await self._cached('du', path, lambda: self._inner.du(path))

    async def _evict(self, path: PurePosixPath) -> None:
        await super()._evict(path)  # the metadata keys
        # a write changes du of this path AND every ancestor:
        node = path
        while True:
            await self._store.delete(self._key('du', node))
            if str(node) == '/':
                break
            node = node.parent


async def main() -> None:
    calls = {'du': 0}

    class CountingBackend(MemoryBackend):
        async def du(self, path):  # noqa: ANN001, ANN201
            calls['du'] += 1
            return await super().du(path)

    fs = Storix(DuCacheLayer(CountingBackend()))
    await fs.mkdir('/data')
    await fs.echo(b'12345', '/data/a.txt')

    print('du /data:', await fs.du('/data'), '(1st: hits backend)')
    print('du /data:', await fs.du('/data'), '(2nd: from cache)')
    print(f'  backend du() calls so far: {calls["du"]}')

    await fs.echo(b'more', '/data/b.txt')  # write -> evicts du of /data and /
    print('du /data:', await fs.du('/data'), '(after write: recomputed)')
    print(f'  backend du() calls total:  {calls["du"]}')


if __name__ == '__main__':
    asyncio.run(main())
