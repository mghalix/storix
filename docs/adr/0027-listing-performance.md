# 27. Listing performance: concurrent batch, bulk emptiness, cache cold path

Status: accepted ((b) bulk emptiness: built; (c) concurrent walk: staged)

## Context

`sx ls` on a cloud container is slow when the empty/full folder icon
(`dir_contents`) is on. Measured on a real Azure container of 8 subdirectories:
`sx --no-icons ls` 1.6s, `sx ls` 11.1s. The cost is the emptiness check.

Root causes, measured, not guessed:

1. **`is_empty` is one LIST request per subdirectory.** `is_empty` pulls the
   first entry of `list_dir` and stops, but both adapters materialize the whole
   listing (`opendal`: `[e async for e in op.list(key)]`; `LocalBackend`:
   `os.scandir` into a list), so the early-stop saves nothing at the request
   level - each `is_empty` is one directory LIST (one paginated round trip on
   Azure). N subdirectories => N requests.

2. **They ran serially.** The CLI computed the glyph per entry in a render
   loop, so the N requests were sequential: N x latency.

3. **The cache made the cold path worse.** Wrapped in the CLI `CacheLayer`,
   8 concurrent `is_empty` took 6.3s vs 2.8s with no layers (warm: 0.00s). The
   cache's `list_dir` materializes and stores the full listing per subdirectory
   on a miss - extra work, per subdir, that does not parallelize.

4. **opendal's per-client concurrency ceiling.** 8 concurrent `is_empty` bare
   ran ~2.4x faster than serial, not ~8x - a connection-pool / partial-GIL
   limit in the one shared sync `Operator`.

## Decision

Three layers, cheapest first.

**(a) Concurrent batch - shipped in 0.4.5.** The CLI batches its per-entry
lookups (emptiness, `-t` mtime, `-l`/`--sort` size) through the core
`concurrent` helper (`state.empty_all` / `stat_all`), so N distinct-target
calls run at once. This is the portable floor: it needs no backend support and
helps every provider. It took `sx ls` 11.1s -> 7.8s (bounded by (3) and (4)).

**(b) Bulk emptiness - a capability-gated port extension (built).** The real
win: derive every immediate child's emptiness from ONE request instead of N.
On an object store, a single delimiter-less LIST of the parent prefix returns
all descendant keys; grouping them by immediate-child prefix says which
children are non-empty. One round trip for the whole listing.

As built:

- Port capability `bulk_listing` and port method `list_tree(path)`, which
  yields the raw absolute path of every descendant under a directory in one
  backend operation (no grouping - that path logic is the core's). Adapters
  that can do it cheaply advertise it: the `opendal` object stores (one
  recursive `list(prefix, recursive=True)`, gated on opendal's own
  `list_with_recursive`, so `s3`/`gcs`/`azblob`/`opendal-memory` advertise it
  and the `fs` service does not) and `MemoryBackend` (one keyspace scan).
  `LocalBackend` and `AzureBackend` do not advertise it and fall back to (a);
  local disk latency is not the round-trip cost this targets.
- Core: `Storix.empty_children(path, names=...)` groups the descendant keys by
  immediate child and returns each child directory's emptiness in one call.
  `is_empty` (single) stays for the point query. The CLI `state.empty_all`
  switches to it, so the CLI keeps declaring intent while grouping and
  concurrency live in the core.
- Gating and bound: the capability gate is an internal optimization - gated
  silently, never a raised `UnsupportedOperationError`. The bulk path reads
  the subtree's KEYS: cheap for a moderately crowded container (thousands of
  keys, one response, one round trip), but a container with millions of keys
  under one prefix should not pull them all, so the core counts against a
  `BULK_LISTING_KEY_LIMIT` (10_000) key bound and falls back to (a) beyond it.
  Correctness never depends on it; it is a speed path with a portable fallback.

**(c) Cache cold path + concurrent walk - follow-ups.** The cache
materialize-per-subdir cost (3) largely disappears once (b) makes it one parent
listing (one cache entry). Independently, `walk` (and thus `sx tree` and the
`sx du` breakdown) is a sequential lazy generator in both flavors; the
whole-tree consumers want a level-buffered concurrent traversal (the deferred
concurrent-walk), which also fixes the inconsistency that `generic.du` (the du
total) is already concurrent while the breakdown is not.

Rejected: defaulting `dir_contents` off on cloud - it disables the feature
instead of making it fast, which is not what was asked. Rejected: making the
cache `list_dir` lazy so `is_empty` stops early - the adapters materialize
regardless, so it buys nothing at the request level.

## Consequences

`sx ls` on a cloud container drops from N round trips to one (bulk path) or
N/concurrency (portable floor, already shipped). The bulk path is opt-in per
adapter with a key bound, so it never turns a huge container into a huge
response silently. `is_empty` the point query is unchanged. Cost: a new port
capability and its per-adapter implementations, and the discipline that the
CLI keeps declaring intent while the concurrency and bulk logic live in the
core.

Sequencing: (a) shipped in 0.4.5. (b) and (c) are the "complete performance"
release: (b) is the headline (the port extension + opendal/local/memory
impls + the core method + the CLI switch), (c) the concurrent walk. Recipe and
benchmark (below) ship alongside so the win is documented and measured.
