# Listing and searching

storix has one directory listing for every shape you need: eager or lazy,
names or rich entries, one level or recursive. They all share the same
semantics (hidden entries hidden unless `all=True`, a session-relative path),
so the only choice is how much you want and how you want it.

## Pick one

| Method | Depth | Yields | Eager/lazy |
| --- | --- | --- | --- |
| `ls` | one directory | `list[StorixPath]` (names) | eager |
| `iterdir` | one directory | `StorixPath` (names) | lazy |
| `scandir` | one directory | `DirEntry` (name, path, kind, size) | lazy |
| `walk` | recursive | `DirEntry` | lazy |
| `find` | recursive | `DirEntry`, filtered | lazy |
| `glob` | recursive | `StorixPath`, pattern-matched | lazy |

The rule of thumb:

- **Just the names of one directory?** `ls` (you get a list) or `iterdir`
  (you get a generator, for a huge directory you do not want to materialize).
- **Names *and* kind/size of one directory?** `scandir`. It carries the
  kind and any size the backend listed for free, so you never `stat` an entry
  just to tell a file from a directory.
- **Everything underneath?** `walk` (all of it), `find` (filtered), or `glob`
  (a path pattern). All stream, so a million-entry tree flows through bounded
  memory.

```python
from storix import get_storage

fs = get_storage("local")

# one directory
for name in fs.ls("/data"): ...                 # eager names
async for path in fs.iterdir("/data"): ...      # (aio) lazy names
for entry in fs.scandir("/data"):               # lazy, rich
    print(entry.name, entry.kind, entry.size)

# recursive
for entry in fs.walk("/data"): ...              # every descendant
for entry in fs.find("/data", name="*.py", kind="file"): ...
for path in fs.glob("**/*.parquet", "/data"): ...
```

## `find` vs `glob`

They are the same recursive walk with two matching styles:

- `find(name=..., kind=...)` matches the **basename** (`fnmatch`, so `'*.py'`,
  `'config.*'`) and can restrict to files or directories. It yields rich
  `DirEntry` objects.
- `glob(pattern)` matches a **path** pattern (`*`, `?`, `**`), pathlib-style,
  and yields paths. `'*.py'` is direct children, `'**/*.py'` is every depth.

Reach for `find` when you want the kind/size of each hit or a type filter;
`glob` when you are thinking in path patterns.

Both exclude hidden entries by default, like the rest of the family - pass an
explicit `name`/pattern to match a dotfile.

## `DirEntry` is not a stat

`scandir`/`walk`/`find` give you `DirEntry` (name, path, `kind`, `size`) - what
a listing produces for free. For the full picture (timestamps, custom
metadata) call `fs.stat(entry.path)`, which returns `FileProperties`. Keeping
them separate is deliberate: a listing of a thousand entries costs one request;
a thousand stats costs a thousand.

## A note on cost

`ls` and its siblings are one listing request per directory. On local disk
that is a cheap syscall; on an object store it is a network round trip. So:

- A **recursive** call (`walk`/`find`/`glob`/`tree`) lists every directory it
  visits - one round trip each on cloud. Filter early (`find(name=...)` stops
  yielding, but still walks) and prefer a bounded depth when you can.
- The `sx` CLI's empty/full folder icon (`dir_contents`) needs a listing *per
  subdirectory*; it batches them concurrently, but on a wide cloud directory
  that is still real work. Turn it off with `dir_contents = false` (or
  `--no-icons`) when you want the fastest possible `ls`, and keep a `cache`
  layer active in interactive sessions so repeats are free.

See [Cache with Redis or disk](caching.md) for the read-through cache, and
[The sx CLI](../guide/cli.md) for the shell.
