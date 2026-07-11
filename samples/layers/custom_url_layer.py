"""How to write a storix layer: subclass, override, upgrade.

A layer is a backend that wraps a backend - it implements the same
StorageBackend protocol it consumes, so it composes with any backend
and with other layers (SandboxLayer included). Subclass
``PassthroughLayer``, which delegates every port method explicitly so
your class satisfies the protocol *statically* (type checkers accept it
anywhere a backend goes), then:

1. override the operations your layer changes,
2. *upgrade the advertised capabilities* so the core's gates open.

The example is an 'imgur-style' public-URL provider for backends that
cannot mint URLs themselves (local, memory): make_url uploads/derives a
public link. The mint step is faked so this sample runs offline -
replace `_mint` with a real API call (imgur, your CDN, a signed nginx
route...) and nothing else changes. Note it *ignores* expires_in, as
the port contract allows for providers without expiring links.

Run:  uv run python samples/layers/custom_url_layer.py
"""

import asyncio
import dataclasses
import hashlib

from pathlib import PurePosixPath

from storix.aio import PassthroughLayer, Storix
from storix.aio.backends import MemoryBackend, StorageBackend


class PublicUrlLayer(PassthroughLayer):
    """Give any backend presigned-URL powers via an external service."""

    def __init__(self, inner: StorageBackend) -> None:
        super().__init__(inner)
        # the crucial move: advertise what the wrapper adds, so
        # Storix.url() opens its capability gate
        self.capabilities = dataclasses.replace(
            inner.capabilities, presigned_urls=True
        )

    async def make_url(
        self, path: PurePosixPath, *, expires_in: int | None = None
    ) -> str:
        content = await self._inner.read(path)
        return f'https://cdn.example/{self._mint(content)}'

    def _mint(self, content: bytes) -> str:
        # stand-in for the real upload; deterministic so the sample
        # is reproducible offline
        return hashlib.sha256(content).hexdigest()[:16]


async def main() -> None:
    fs = Storix(PublicUrlLayer(MemoryBackend()))

    await fs.echo(b'\x89PNG...pretend pixels...', '/cat.png')
    link = await fs.url('/cat.png')  # no expiry needed; the layer has none

    print(f'shareable link for /cat.png -> {link}')

    # everything else passes straight through to the inner backend
    print(f'still a normal filesystem: {await fs.ls("/")}')


if __name__ == '__main__':
    asyncio.run(main())
