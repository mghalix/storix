"""Native-preference combinator for the layers= list."""

from __future__ import annotations

from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from ..backends import StorageBackend
    from ..core import BoundLayer, LayerFactory


def when_missing[**P](
    layer: LayerFactory[P], /, *args: P.args, **kwargs: P.kwargs
) -> BoundLayer:
    """Apply ``layer`` only when the backend lacks the capability it provides.

    The native-preference combinator: the same construction code works
    across providers, wrapping capability-poor backends and
    short-circuiting entirely (zero overhead, native behavior) on
    backends that already advertise the capability::

        Storix(backend, layers=[when_missing(DataUrlLayer)])

    The capability is inferred from the layer's ``provides`` ClassVar (no
    redundant capability argument); extra args/kwargs forward to the
    layer's constructor. Prefer-the-layer is expressed by not using the
    combinator.

    Raises:
        ValueError: If the layer declares no ``provides`` capability to
            infer (nothing to gate on - use it unconditionally instead).
    """
    capability = getattr(layer, 'provides', None)
    if capability is None:
        msg = (
            f'{getattr(layer, "__name__", layer)!r} declares no `provides` '
            f'capability to infer; use with_layer() instead'
        )
        raise ValueError(msg)

    def build(backend: StorageBackend) -> StorageBackend:
        if backend.capabilities.supports(capability):
            return backend
        return layer(backend, *args, **kwargs)

    return build
