"""Native-preference combinator for the layers= list."""

from __future__ import annotations

from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from collections.abc import Callable

    from storix.enums import Capability

    from ..backends import StorageBackend

    BoundLayer = Callable[[StorageBackend], StorageBackend]


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
