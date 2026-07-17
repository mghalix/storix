# 23. Rich, lazy directory listing: scandir, iterdir, is_empty, DirEntry

Status: accepted

## Context

`Storix.ls()` returns `list[StorixPath]` - names only. The driven port's
`list_dir` already yields `Entry(name, is_dir, size)`, and adapters fill `size`
in for free where their listing carries it (`LocalBackend`'s `scandir`,
opendal's `list`). The core discards both facts on the way out.

So any consumer needing an entry's kind or size has two bad options: `stat`
every entry (N extra round trips on an object store), or drop to
`fs.backend.list_dir()` and re-implement what `ls` does around it - resolve the
target, handle "listing a file returns the file", filter hidden names, sort.
`sx` took the second path (`cli/state.py: list_entries`, `has_children`), which
puts core listing semantics in two places - the exact driving-adapter overreach
`docs/design/architecture.md` warns against. `ls` also has no lazy form: a
directory of a million entries materializes fully.

Two more gaps sit on top of this one:

- **Emptiness.** Distinguishing an empty directory from a full one (the `sx`
  empty-folder icon, a guard before `rmdir`, deciding whether to recurse) needs
  a look inside. `sx` has `has_children`; the core has nothing.
- **Concurrency.** The per-subdirectory emptiness checks and `tree` traversal
  run sequentially in `sx`, because they live in the CLI on the sync flavor. In
  the async core, N such checks are `gather`-able. The primitive has to exist in
  the core for either flavor to parallelize it.

## Decision

Add three listing methods and one user-facing DTO, and reimplement `ls` over
them so listing semantics live in exactly one place.

**`DirEntry`** - the user-facing listing entry, mapped from the port's `Entry`
the way `FileProperties` maps from `RawStat`. A `@dto` (frozen, slotted,
kw-only) rather than a pydantic model, for the same reason `RawStat` is: it
crosses the boundary per entry in a listing and validating trusted data buys
nothing.

```python
@dto
class DirEntry:
    name: str                 # basename
    path: StorixPath          # absolute, session-resolved
    kind: PathKind            # file | directory (extensible: a future symlink)
    size: int | None          # bytes when the listing carried it, else None

    @property
    def is_dir(self) -> bool: ...   # kind is PathKind.DIRECTORY
    @property
    def is_file(self) -> bool: ...  # kind is PathKind.FILE
```

`kind`, not `is_dir`, on the DTO itself: a boolean cannot gain a `symlink` case
without a breaking change (AGENTS.md, "Naming the public surface"). `is_dir` /
`is_file` remain as convenience properties.

**`scandir(path=None, *, all=False) -> Iterator[DirEntry]`** (async:
`AsyncIterator`). The headline: lazy and rich, after `os.scandir`. Yields in
backend order, unsorted (sorting would force materialization; a caller sorts if
it wants to, as `sx` does for display). Mirrors `ls` semantics otherwise:
listing a file yields that one entry; hidden entries excluded unless `all`.
Does *not* carry a lazy `.stat()` on the entry in v1 - that would couple the
DTO to the session; a caller wanting full timestamps calls `fs.stat(e.path)`.

**`iterdir(path=None, *, all=False) -> Iterator[StorixPath]`** (async:
`AsyncIterator`). Lazy names, after `pathlib.Path.iterdir`; yields absolute
`StorixPath`s. Sugar over `scandir` (`e.path for e in scandir(...)`), included
now because it is two lines and gives the future pathlike adapter its parity.

**`is_empty(path=None) -> bool`**. Pulls the first entry from the backend
listing and stops - minimal cost, one round trip, no full read. Counts *any*
entry, including hidden ones: a directory holding only a dotfile is not empty
(`rmdir` would fail on it), so `is_empty` ignores the `all` filter. Replaces
`sx`'s `has_children`.

**`ls` is reimplemented over `scandir`** and keeps its exact signature, return
type, and behavior (every existing `ls` test stays green). This is the DRY
win: the resolve / list-a-file / filter-hidden logic has one home, and `ls`,
`iterdir`, `scandir` are three projections of it.

**Concurrency** is not solved by these methods themselves - they are
per-directory primitives - but they are the prerequisite. In the async flavor a
consumer batches emptiness or traversal with `gather` (`sx` can drive a batch
through one `asyncio.run`); the sync flavor stays sequential, as it is today.
An object-store optimization (one recursive `LIST` under a parent derives every
immediate child's emptiness in a single request) is possible later behind the
same `is_empty`/`scandir` surface; it reads the subtree, so it is a deliberate
v2 size trade-off, not v1.

Rejected: an `ls(detail=True)` overload or an `ls(lazy=True)` toggle - a return
type that changes with an argument value is hostile to static typing (callers
get a union pyright cannot narrow without `@overload` gymnastics). A parameter
changes behavior, not type; the three shapes are three named methods instead.
Also rejected: handing the port's `Entry` to users - it is a port DTO, and
user-facing types map from port types (the `RawStat` -> `FileProperties`
precedent).

## Consequences

The kind/size an adapter already produced reach a consumer without a stat storm
or a re-implementation; `sx` deletes `list_entries` and `has_children` and
consumes the core, and the future pathlike / flat / MCP adapters inherit all of
it. `ls` gains a lazy sibling and an emptiness primitive without changing. The
new surface is codegen (edit `_async` only, `just gen`) and slots into the
parametrized conformance suite like any backend method. Cost: one more public
DTO and three methods to keep documented and conformance-covered.

0.4.4 (backward-compatible feature -> patch; ADR 0021).

Implementation:

- [ ] `DirEntry` in `models.py` (user-facing, `@dto`, `kind` + `is_dir`/
      `is_file` properties); export from the public API and both flavors.
- [ ] `scandir`, `iterdir`, `is_empty` on `_async/core.py`; reimplement `ls`
      over `scandir`. Docstrings distinguish the three clearly (eager names /
      lazy names / lazy rich).
- [ ] `just gen`; the `_sync` twins generate.
- [ ] Conformance coverage in both flavors: rich fields present, laziness
      (a generator, not a materialized list), `is_empty` on empty vs
      dotfile-only vs populated, `ls` behavior unchanged.
- [ ] `sx`: delete `list_entries` / `has_children`, consume `scandir` /
      `is_empty`; the empty-folder icon and completion read the core.
- [ ] `just check` + `uv run pyright` green.
