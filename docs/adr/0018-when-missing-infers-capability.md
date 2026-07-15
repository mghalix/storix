# 18. `when_missing` infers its capability (breaking signature)

Status: accepted

## Context
Native-preference ships in two forms today, and they disagree on where
the capability comes from:

- `when_missing(capability, layer)` (`layers/native.py`), the free
  combinator for the `layers=` list, takes the capability *explicitly*.
- `Storix.with_layer_missing(layer, *args, **kwargs)` (`core.py`), the
  post-construction method, *infers* it from the layer's `provides`
  ClassVar.

ADR 0008 kept the explicit form on purpose. PEP 612 forbids a named
parameter (`unless=`) alongside `**P.kwargs`, so the *method* could not
carry both the forwarded kwargs and an explicit capability; inference was
the only way to give the method ParamSpec typing. The free combinator,
which does no arg forwarding, kept the explicit capability "for the rare
gate-on-a-different-capability case."

Two things make that split a liability now:

1. It is a silent footgun. `when_missing(Capability.PRESIGNED_URLS,
   MetadataLayer)` type-checks and runs; the capability and the layer
   disagree and nothing complains. The layer either backfills a
   capability nobody asked about, or is skipped for the wrong reason.
2. We are about to push users onto exactly this function. The
   config-driven pattern (build a `list[BoundLayer]` from config, pass it
   to `Storix(backend, layers=...)`) is the pre-construction path, and
   the free `when_missing` is *the* tool for it. The internal callers all
   pass matching capability/layer pairs, so the footgun is theoretical
   today; it goes live the moment an integrator assembles a layer stack
   from config.

The "rare gate-on-a-different-capability" case that justified the
explicit form has no shipped use, and it *is* the footgun wearing a
feature costume.

## Decision
The free combinator infers its capability from the layer, exactly like
the method, and drops the explicit parameter. Breaking signature change:

    # was
    def when_missing(capability: Capability, layer: BoundLayer) -> BoundLayer

    # now
    def when_missing(
        layer: LayerFactory[P], /, *args: P.args, **kwargs: P.kwargs
    ) -> BoundLayer

Behavior: read `layer.provides`; raise `ValueError` if it is `None` (same
message and reason as `with_layer_missing`, `core.py:164`, since a layer
with no `provides` has nothing to infer); apply the layer only when the
backend lacks that capability, else return the backend untouched (zero
overhead, unchanged). The added ParamSpec forwarding means the
conditional case no longer needs a manual `functools.partial`:

    layers = [
        when_missing(MetadataLayer, serialize=..., deserialize=...),  # inferred
        partial(SandboxLayer, root=root),                             # unconditional
        partial(CacheLayer, **cache_kwargs),
    ]

`when_missing` is now the pre-construction twin of `with_layer_missing`:
same inference, same forwarding. One returns a `BoundLayer` for
`layers=`, the other a new session. The method may be reimplemented on
top of the combinator so the skip logic has one home (optional; verify no
import cycle).

The gate-on-a-different-capability escape hatch is not lost, it is
unbundled. A `BoundLayer` is a four-line closure, so anyone who genuinely
needs to gate a layer on an unrelated capability writes it inline, rather
than every caller paying a footgun tax for a case nobody has hit:

    def when_missing_cap(cap, layer):
        def build(be):
            return be if be.capabilities.supports(cap) else layer(be)
        return build

`LayerFactory` (the ParamSpec layer-factory protocol, `core.py`) moves out
of `TYPE_CHECKING` and is exported beside `BoundLayer`: it now appears in
a public signature (`when_missing`), and integrators writing their own
layer helpers need to name the type. `BoundLayer` was already promoted in
0016; this closes the pair.

Rejected: a `bind(layer, *args, **kwargs) -> BoundLayer` twin for the
unconditional case (a typed, named `partial`). With `when_missing` now
forwarding args, `partial` survives only on unconditional layers, where
it is stdlib, already a documented `BoundLayer` (`core.py:74`), and
pyright-checked. `bind` would add vocabulary symmetry and zero behavior.
Revisit only if the `partial` import proves a real friction point for
integrators.

Also rejected: an overload keeping the old `when_missing(capability,
layer)` alongside the new form. It preserves the footgun as a supported
path and invites the capability/layer disagreement we are removing.
storix is pre-1.0; break it cleanly.

## Consequences
One inference rule for native-preference across both the pre- and
post-construction APIs, and the config-driven `list[BoundLayer]` pattern
that motivated this becomes clean: `config -> list[BoundLayer]`, a pure
function, no `fs` threaded through. Supersedes the explicit-capability
`when_missing` signature in 0013 and 0008 (the combinator-over-flags
philosophy of 0013 is unchanged; only where the capability comes from
changes).

Breaking: `when_missing(Capability.X, Layer)` call sites must drop the
capability. In-tree that is one test (`tests/_async/test_layers.py:118`,
sync twin generated) plus the ADR references above. Downstream: a
minor-version breaking note; trivial mechanical migration (delete the
first argument).

Implementation (edit `_async` only, then `just gen`; full gate
`just check`):

- [ ] `src/storix/_async/layers/native.py`: new signature, infer from
      `provides`, `ValueError` on none, forward `*args/**kwargs`. Import
      `LayerFactory` (see next).
- [ ] `src/storix/_async/core.py`: move `LayerFactory` and its
      `ParamSpec P` out of `TYPE_CHECKING` (runtime defs; a `Protocol`
      costs nothing at runtime). Confirm `native.py` importing it from
      `core` creates no cycle (core loads before layers in
      `_async/__init__.py`); if it does, lift both `LayerFactory` and
      `BoundLayer` to a small shared module.
- [ ] Export `LayerFactory` from `_async/__init__.py`, `aio/__init__.py`,
      `storix/__init__.py`, and add it to each `__all__` (mirror how
      `BoundLayer` is exported).
- [ ] `tests/_async/test_layers.py:118`: update to the inferred signature
      (`when_missing(DataUrlLayer)`); add a case asserting `ValueError`
      when the layer has no `provides`.
- [ ] Optional: reimplement `with_layer_missing` over `when_missing`.
- [ ] `just gen` (regenerate `_sync`), then `just check`.
- [ ] Amend ADR 0013 and 0008 with a one-line "superseded by 0018"
      pointer (append-only; do not edit their bodies).

0.2.x.
