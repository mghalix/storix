# 16. Removable layers: `without_layer` / `uncached`

Status: accepted

## Context
The layer a session is built with is its *default* policy, but callers
sometimes need to opt out for one operation - most commonly a
guaranteed-fresh read that bypasses a `CacheLayer`. The only prior
escape was `CacheLayer.clear()`, which nukes the whole cache for
everyone. There was no way to say "this one read, straight to the
backend."

## Decision
`Storix.without_layer(*types)` returns a *new* session with every layer
that is an instance of one of `types` dropped, the rest re-composed so
operations bypass them - `fs.without_layer(CacheLayer).ls()`. The
mechanism is general: walk the `_inner` chain to the base backend, then
rebuild inward, `copy.copy`-ing each surviving layer onto the new inner
(shallow - only the wrapped backend changes; a layer's config is
immutable and safely shared). Absent types are a **no-op**, so it is
safe to call unconditionally, and cwd is **preserved** - a removable
layer never changes the path namespace, so the current directory stays
valid. `uncached` is sugar for `without_layer(CacheLayer)`.

**Removability is a per-layer guarantee, not a free-for-all.**
`LayerBase.removable: ClassVar[bool] = True`; a layer whose presence is
a contract sets it `False`. `SandboxLayer.removable = False` - a jail is
a security boundary, and ADR 0008's whole promise is that a sandboxed
session cannot escape it. Trying to strip a non-removable layer raises
`NonRemovableLayerError` (in the `storix.errors` taxonomy), not a bare
`ValueError`, so it is catchable and documented. The rule reads cleanly:
you can always ask for *less* (drop a cache); you can never ask your way
out of a boundary.

`without_layer` matches by type and is symmetric with `with_layer`
(the name `with`/`without` is impossible - `with` is a keyword). The
`BoundLayer` alias (`Callable[[StorageBackend], StorageBackend]`, the
`layers=`/`with_layer` shape) is also promoted from a `TYPE_CHECKING`
local to a public export, so consumers stop redefining it.

## Consequences
A one-word, always-safe fresh-read (`fs.uncached.ls()`) and a general
per-op layer bypass, with the security boundary encoded in the type
system rather than convention - `without_layer(SandboxLayer)` fails
loudly by design. The re-compose cost is a few shallow copies per call;
for a hot bypass loop, hold the derived session. 0.2.2.
