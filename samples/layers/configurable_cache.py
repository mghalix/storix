"""Configure the cache per operation: metadata, du, content, URLs.

CacheLayer caches metadata (stat/list/exists) by default. Turn on du,
read, and url too, each with its own ttl, store, and (for read) a
per-file size cap. Share one store or give an op its own.

    from storix import cache, CacheLayer, InMemoryCacheStore

    fs = get_storage('azure').with_layer(
        CacheLayer,
        metadata=True,                       # navigation hot path
        du=cache(ttl=60),                    # expensive tree walk
        read=cache(ttl=30, max_bytes=8 * 1024 * 1024,  # content <= 8 MiB
                   store=InMemoryCacheStore(maxsize=200)),
        url=cache(ttl=300),                  # presigned URLs (TTL-only)
        ttl=120,                             # default for ops without one
        namespace='storix', environment='prod',
    )

The example below runs offline and counts backend round-trips.

Run:  uv run python samples/layers/configurable_cache.py
"""

import asyncio

from collections.abc import AsyncIterator
from pathlib import PurePosixPath
from typing import ClassVar

from storix.aio import CacheLayer, Storix, cache
from storix.aio.backends import MemoryBackend
from storix.models import Capabilities


class Counting(MemoryBackend):
    """Counts the expensive ops so we can see the cache working."""

    capabilities = Capabilities(custom_metadata=True, presigned_urls=True)
    du_calls: ClassVar[int] = 0
    read_calls: ClassVar[int] = 0
    url_mints: ClassVar[int] = 0

    async def du(self, path: PurePosixPath) -> int:
        Counting.du_calls += 1
        return await super().du(path)

    async def read_stream(
        self,
        path: PurePosixPath,
        *,
        chunk_size: int | None = None,
    ) -> AsyncIterator[bytes]:
        Counting.read_calls += 1
        async for chunk in super().read_stream(path, chunk_size=chunk_size):
            yield chunk

    async def make_url(
        self,
        path: PurePosixPath,
        *,
        expires_in: int | None = None,
    ) -> str:
        del expires_in
        Counting.url_mints += 1
        return f'https://signed.example/{path}?n={Counting.url_mints}'


async def main() -> None:
    inner = Counting()
    fs = Storix(
        CacheLayer(
            inner,
            metadata=True,
            du=cache(ttl=60),
            read=cache(max_bytes=1024),  # cache files up to 1 KiB
            url=cache(ttl=300),  # presigned URLs, TTL-only
        )
    )
    await fs.mkdir('/data')
    await fs.echo(b'x' * 100, '/data/small.bin')  # cached on read
    await fs.echo(b'y' * 5000, '/data/large.bin')  # too big -> never cached

    Counting.du_calls = Counting.read_calls = Counting.url_mints = 0
    for _ in range(3):
        await fs.du('/data')
        await fs.cat('/data/small.bin')
        await fs.cat('/data/large.bin')
        await fs.url('/data/small.bin')

    print('3 rounds of du + 2 reads + 1 url each:')
    print(f'  backend du()   calls: {Counting.du_calls}   (1 = du cached)')
    print(
        f'  backend read() calls: {Counting.read_calls}   '
        f'(small cached once, large re-read every time)'
    )
    print(f'  backend url mints:    {Counting.url_mints}   (1 = url cached)')

    await fs.echo(b'z', '/data/new.bin')  # write evicts du of /data and /
    Counting.du_calls = 0
    await fs.du('/data')
    print(f'  du after write:       {Counting.du_calls}   (recomputed, not stale)')


if __name__ == '__main__':
    asyncio.run(main())
