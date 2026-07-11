# 13. Layer combinators over boolean flags

Status: accepted

## Context
Native-preference ("use the backend's own capability, otherwise backfill
with a layer") must work with one construction path across providers.
The obvious reach is a flag - `Storix(backend, add_url_layer=True)` or a
parameter on every layer.

## What a combinator is
A *combinator* is just a function that takes function(s) and returns a
new function, building behavior by composition instead of by branching.
`when_missing(capability, layer)` takes a layer factory and returns a
*new* layer factory that applies the layer only when the backend lacks
the capability. Nothing is mutated; the condition lives in one reusable
place; combinators nest and compose.

## Decision
Native-preference is a combinator, not a flag:
`when_missing(Capability.PRESIGNED_URLS, DataUrlLayer)` for the `layers=`
list, and `fs.with_layer_missing(layer, *args, **kw)` post-construction (capability inferred from the layer's `provides`; ParamSpec-typed, Starlette add_middleware style).
Both short-circuit to the bare backend when the capability is already
native (zero overhead), so `get_storage('local')` and
`get_storage('azure')` take the identical construction line.

## Consequences
No boolean-trap parameters accreting on constructors or layers; the same
mechanism serves any future capability/layer pair. Cost: users meet a
functional idiom (a factory returning a factory) - documented with
examples. Rejected: per-layer `only_if=`/`enabled=` flags (spreads the
same conditional across every layer's constructor).
