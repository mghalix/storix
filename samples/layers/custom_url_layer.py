"""How to write a storix layer: wrap, delegate, override, upgrade.

A layer is a backend that wraps a backend - it implements the same
StorageBackend protocol it consumes, so it composes with any backend
and with other layers (SandboxLayer included). Four moves:

1. store the inner backend,
2. delegate everything you don't care about,
3. override the operations you do care about,
4. *upgrade the advertised capabilities* so the core's gates open.

The example is an 'imgur-style' public-URL provider for backends that
cannot mint URLs themselves (local, memory): make_url uploads/derives a
public link. The mint step is faked so this sample runs offline -
replace `_mint` with a real API call (imgur, your CDN, a signed nginx
route...) and nothing else changes.

Run:  uv run python samples/layers/custom_url_layer.py
"""

import asyncio
import dataclasses
import hashlib

from pathlib import PurePosixPath
from typing import Any

from storix._async import Storix
from storix._async.backends import StorageBackend
from storix._async.backends.memory import MemoryBackend


class PublicUrlLayer:
    """Give any backend presigned-URL powers via an external service."""

    def __init__(self, inner: StorageBackend) -> None:
        self._inner = inner
        # the crucial move: advertise what the wrapper adds, so
        # Storix.url() opens its capability gate
        self.capabilities = dataclasses.replace(inner.capabilities, presigned_urls=True)

    def __getattr__(self, name: str) -> Any:
        # delegate every port method we don't override. Quick and terse;
        # for full static typing write the methods out explicitly like
        # storix's own SandboxLayer does.
        return getattr(self._inner, name)

    async def make_url(self, path: PurePosixPath, *, expires_in: int) -> str:
        content = await self._inner.read(path)
        token = self._mint(content)
        return f'https://cdn.example/{token}?ttl={expires_in}'

    def _mint(self, content: bytes) -> str:
        # stand-in for the real upload; deterministic so the sample
        # is reproducible offline
        return hashlib.sha256(content).hexdigest()[:16]


async def main() -> None:
    fs = Storix(PublicUrlLayer(MemoryBackend()))

    await fs.echo(b'\x89PNG...pretend pixels...', '/cat.png')
    link = await fs.url('/cat.png', expires_in=600)

    print(f'shareable link for /cat.png -> {link}')

    # everything else passes straight through to the inner backend
    print(f'still a normal filesystem: {await fs.ls("/")}')


if __name__ == '__main__':
    asyncio.run(main())
