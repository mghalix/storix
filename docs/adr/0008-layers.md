# 8. Cross-cutting concerns are layers (backends wrapping backends)

Status: accepted

## Context
0.1.x sandboxing scattered to_virtual/to_real calls through every
provider method - every operation was a chance to forget one.

## Decision
A layer implements the same port it consumes, so layers compose with
backends and each other. `SandboxLayer` is chroot as middleware: one
choke point re-anchoring lexically-normalized paths under a root,
re-scoping inner errors to the virtual namespace (`raise ... from
None` so the real prefix never leaks), with `to_real`/`to_virtual`
public as the *provider's* privileged audit handle - the session stays
sandbox-unaware by design (a worker cannot unmask its own jail).
`LayerBase` writes out every delegation so custom layers satisfy
the protocol statically. Ergonomics: `Storix(backend, layers=[...])`
(factories, last is outermost), `fs.with_layer()`, `fs.chroot()` - all
returning/creating fresh sessions, never mutating a live cwd.
Containers are backend config, never sandbox knowledge.

## Consequences
Sandboxing passes the full backend conformance suite like any backend;
future CacheLayer/MetadataLayer/ObservabilityLayer follow the same
shape. Rejected: `sandboxed=True` constructor flag (boolean trap, no
root, hides the concept).

## Update (0.2.0): layer family and native-preference

`PassthroughLayer` was renamed `LayerBase` (its primary role is a
subclassing base; used alone it is a harmless passthrough). Shipped
concrete layers: `DataUrlLayer` (url() via base64 data: URLs - documented
as unfit for LLM context windows) and `MetadataLayer` (custom metadata
via a hidden, invisible JSON sidecar inside the wrapped backend).
Native-preference is a combinator, not a flag: `when_missing(capability,
layer)` (for `layers=`) and `fs.with_layer_missing(layer)` (capability inferred)
skip the layer when the backend is already native - one construction
path works across providers, zero overhead where unneeded.
