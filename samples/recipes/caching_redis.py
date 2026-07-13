"""Cache with Redis (or disk) through Cashews and async storix.

CacheLayer's store is a small cashews-shaped protocol (get / set / delete /
delete_match). A cashews.Cache plugs directly into the async CacheLayer. Point
it at Redis for a cache shared across processes, or at a disk backend for one
that survives restarts. Keys are namespaced, so environments never collide in
a shared store.
"""

from __future__ import annotations

import asyncio

from cashews import Cache

from storix.aio import CacheLayer, cache, get_storage


store = Cache()
store.setup('redis://localhost:6379')  # or 'disk://.cache' for a local disk cache


async def main() -> None:
    fs = get_storage('local', base='~/storix-data/cache-recipe').with_layer(
        CacheLayer,
        store=store,  # Cashews satisfies the async CacheStore protocol as-is.
        du=cache(ttl=60),
        read=cache(max_bytes=8 * 1024 * 1024),
        environment='prod',
    )
    try:
        await fs.echo('cached content', '/example.txt')
        await fs.cat('/example.txt')  # fills the content cache
        await fs.cat('/example.txt')  # served from the content cache
    finally:
        await fs.close()
        await store.close()


if __name__ == '__main__':
    asyncio.run(main())
