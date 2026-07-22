# 28. Concurrent recursive traversal: level-buffered core walk

Status: proposed

## Context

One `scandir` is one remote directory operation, but recursive consumers issue
those operations sequentially today. `Storix.walk` descends depth-first and
does not list the next directory until the current subtree returns. `sx tree`
does not consume that core method at all: it has a second depth-first recursion
around `scandir`. `find` and `glob` inherit the core walk, while `sx du` uses its
post-order form. All four therefore pay roughly the sum of directory latencies.

The effect is visible on the HNS Azure container used for ADR 0027. `sx tree -L
1` (one root listing) took 1.62s. `sx tree -L 2` (the root plus its nine child
directories) took 14.36s. An unrestricted traversal was still running after
72.33s and was interrupted. This is network wait, not rendering or CPU.

ADR 0025 provides the portable `concurrent` thunk helper: bounded asyncio work
in async and a bounded thread pool in sync, with results returned in submission
order and errors left in the Storix taxonomy. ADR 0026 intended recursive
consumers to use it, but the implemented walk stayed sequential and the CLI
kept its own traversal. ADR 0027 deferred the correction as concurrent walk.

The core boundary applies: traversal, depth limits, concurrency, hidden-entry
semantics, and backend errors belong to `Storix`. `sx tree` may choose colors,
branches, and sibling sort order, but it must not decide how storage is walked.

## Decision

Replace recursive depth-first I/O with a bounded, level-buffered traversal in
the core. It continues to use the portable `scandir` port path; no backend
capability or recursive-listing fast path is required.

### Frontier execution

The engine holds a frontier of directories at one depth, initially the
requested root. It splits that frontier into chunks no larger than
`DEFAULT_CONCURRENCY`. For each chunk it calls `concurrent` with one thunk per
directory. A thunk materializes that directory's immediate `scandir` result:
materialization is necessary because returning a generator from a sync worker
would defer its I/O back onto the caller thread.

`concurrent` returns listings in frontier submission order, not completion
order. Within a listing, backend order remains intact. The engine filters
hidden entries exactly as `scandir` does and collects visible child directories
for the next frontier. It never creates one task for every directory in the
tree; concurrency and task memory are bounded per chunk.

The public method gains an additive depth bound:

```python
walk(
    path=None,
    *,
    all=False,
    top_down=True,
    max_depth: int | None = None,
) -> Iterator[DirEntry]
```

Depth 1 includes immediate children and does not list inside child
directories. Zero includes no descendants. Negative values raise `ValueError`.
The bound is enforced before a directory enters the next frontier, so `tree -L
N` avoids the remote calls it excludes instead of walking and filtering later.

### Ordering

Emission order is decoupled from frontier fetching through an additive
keyword (`type WalkOrder = Literal['dfs', 'level']`):

```python
walk(..., order: WalkOrder = 'dfs')
```

The default `order='dfs'` is the exact depth-first contract of the
sequential walk (storix 0.4.7 and earlier). `top_down=True` yields a
directory immediately followed by its whole subtree, siblings in backend
listing order, files and directories interleaved as listed.
`top_down=False` yields files as encountered and each directory only
after its entire subtree, which keeps `sx du`'s single-pass size
propagation correct. Entries buffer per parent as fetched levels arrive,
and an explicit depth-first cursor drains every entry whose position is
settled each time a level completes. A stalled cursor never blocks
fetching, so total wall time stays that of the concurrent traversal while
output streams in leftmost-spine-first bursts. The cost is honest
buffering: entries are held until their depth-first position is reached,
worst case the whole tree (entries are small: name, path, kind, size).

`order='level'` emits what the traversal fetches, level by level, and
buffers only the frontier and its listings. `top_down=True` emits a
level's entries whole in stable parent/listing order before the next
level is listed, so sibling groups arrive contiguous. `top_down=False`
emits file leaves as levels are read, retains directory entries by depth,
and after traversal emits directories from deepest level to shallowest,
preserving stable order within a level.

Relative to released storix (v0.4.7), the default contract is restored,
not changed: the level-only emission existed only unreleased on main and
never shipped. `order='dfs'` guarantees exact depth-first output;
`order='level'` guarantees the relational contract (ancestor before or
after descendant, whole levels at a time).

### Core consumers and CLI

`find` and `glob` continue to filter the top-down walk and `sx du` the
post-order walk, all on the default `order='dfs'`, so their output keeps
the unix depth-first order while inheriting frontier concurrency without
their own thread or task management. `sx find` prints each entry as the
walk yields it.

`sx tree` deletes its `children_of`/recursive storage loop and calls
`walk(max_depth=level, order='level')`, the one consumer of level
emission: contiguous sibling groups are what sorting and branch glyphs
need. It renders pull-driven rather than materializing the stream,
buffering the walk one complete level at a time and printing each line as
soon as its subtree membership is known. `--sort name|time|size` and
branch drawing stay presentation over facts the core already fetched, not
another traversal. Missing sizes or timestamps needed for a requested
sort remain batched through the existing `stat_all` helper.

Closing a walk or encountering an error leaves no orphan work. A frontier chunk
finishes under `concurrent`'s existing semantics, then the first error in stable
submission order propagates unwrapped.

### Verification

Add a latency backend whose `list_dir` records active calls. Tests cover both
generated flavors and prove:

- sibling directory listings overlap and never exceed `DEFAULT_CONCURRENCY`;
- top-down ancestors precede descendants and post-order reverses that relation;
- the default order reproduces the sequential depth-first sequence exactly,
  in both `top_down` modes;
- `max_depth` prevents excluded backend calls;
- hidden directories are neither yielded nor scheduled unless `all=True`;
- completion timing does not reorder results;
- errors propagate as the original Storix exception; and
- `sx tree` delegates traversal to `walk` rather than calling `scandir`
  recursively.

Benchmark the deterministic latency backend and the ADR 0027 Azure container.
For a wide level, expected latency moves from the sum of sibling listings toward
the slowest listing in each bounded chunk. A single deep chain has no available
fan-out and is not expected to improve.

Rejected: use backend `list_tree` for all recursive consumers. A delimiter-less
recursive listing loses per-directory request boundaries, can exceed the key
bound before proving emptiness, and cannot replace the portable rich-entry walk
on every backend. Rejected: add concurrency only inside `sx tree`; `find`,
`glob`, and `du` would remain slow and the driving adapter would continue to own
core behavior. Rejected: recursively spawn one task per directory; a large tree
would create unbounded work and make cancellation and error order unpredictable.
Rejected: preserve exact depth-first output with one-level sibling prefetch; it
helps a shallow wide root but leaves deeper sibling frontiers serialized and
does not deliver the measured tree-wide improvement.

## Consequences

Wide remote trees become bounded by level/chunk latency instead of the sum of
every directory latency. Sync and async keep one source-level algorithm and use
their audited `concurrent` twins. `tree`, `find`, `glob`, and `du` share one
traversal and one error model.

Costs: `order='level'` buffers one frontier and its immediate listings
(post-order additionally retains directory entries until the
reverse-depth emission); the default `order='dfs'` buffers entries until
their depth-first position is reached, worst case the whole tree. Default
output order is unchanged from released storix (v0.4.7), so the work
ships as a backward-compatible change per ADR 0021, not under a new minor
line. Deep single-child chains do not become faster, because they contain
no independent directory listings to overlap.

Implementation is staged. ADR acceptance precedes code changes.
