"""DataUrlLayer: url() everywhere via base64 data: URLs."""

from __future__ import annotations

import dataclasses

from typing import TYPE_CHECKING

from storix.enums import Capability

from .base import LayerBase


if TYPE_CHECKING:
    from pathlib import PurePosixPath

    from ..backends import StorageBackend


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
