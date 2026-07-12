# 14. CacheLayer: configurable per-op read-through cache

Status: accepted

## Context
The ergonomic/agent layer re-reads the same facts constantly:
navigation stats a path and its parent, `du` walks a whole tree, a
prompt cats the same file twice. Against a cloud backend each repeat is
a round-trip. A cache is a cross-cutting concern, so it is a layer
(ADR 0008) - not baked into the core or any one backend.

## Decision
**Per-op specs, one layer.** The four cacheable reads - metadata
(stat/list_dir/exists), `du`, `read` (content), `url` (presigned) - are
each toggled `bool | CacheOp`. `metadata` defaults on (the navigation
hot path); `du`/`read`/`url` are opt-in. `cache(ttl=, store=,
max_bytes=)` overrides one op, `True` inherits the layer defaults,
`False` disables. One class, one construction path - no
`ConfigurableCacheLayer` subclass zoo.

**Per-op stores and TTLs.** Each op inherits the layer's `store`/`ttl`
or carries its own (metadata in Redis, content on a bounded local
store). `read` alone honors `max_bytes` - skip caching files over the
cap, since one giant file is a single entry that blows any count-based
bound.

**Keys follow `<namespace>[:<environment>]:<op>:<locator>`** - the
`sdk:env:resource:id` convention (base `storix`, optional
`environment`, both overridable). Keyed on the physical `locate()` URI,
never the virtual path: two sessions sharing one store (different
sandboxes, different backends) must not collide on `/x`, and must share
on the same physical object. `locate()` is pure (no I/O) and
prefix-consistent - a child's locator extends its parent's - so tree
eviction is a glob.

**Invalidation is per op, in that op's store, on every mutation through
the layer.** metadata evicts the path + its parent listing; `du` walks
the ancestor chain (a write changes every ancestor's size); `read`
evicts the file; `url` is TTL-only - a minted URL stays valid for its
lifetime no matter how the object changes, so mutations never touch it,
and the entry is capped to the URL lifetime so a cached URL is never
served dead. The session always sees its own writes.

**Pluggable `CacheStore`** - a cashews-shaped async protocol
(`get`/`set`/`delete`/`delete_match`) with deliberately loose `Any`
returns, so a real `cashews.Cache` (whose `set`/`delete` return
bool/int) satisfies it structurally with no adapter. The in-memory
default takes an optional `maxsize` (LRU) as the simple total-memory
bound. Same reasoning as the MetadataLayer codec (ADR 0010): shape to
the ecosystem, do not impose a contract.

**Correctness assumes a single writer of the store(s).** The cache
cannot see writes made *outside* the layer (another process, the cloud
console). `ttl` bounds staleness; the default `None` never expires and
is safe only for a sole owner. Carried as a prominent docstring
warning, not a silent assumption.

## Consequences
Navigation and `du` collapse from per-op round-trips to in-process
hits; the same layer spans a throwaway in-memory cache and a shared
Redis with no code change; a session sharing a store with others never
clashes because keys are physical. The one liability - staleness under
concurrent external writers - is made explicit and bounded by `ttl`,
never hidden. Shipped 0.2.1.
