# 26. Recursive walk: find, glob, and the du/tree it feeds

Status: accepted

## Context

`scandir` (ADR 0023) gave the core a lazy, rich, single-directory listing.
Three things want the *recursive* version of it and currently either do not
exist or are re-implemented in the driving adapter:

- **`find`/`glob`** - "every `*.py` under here", "all directories" - a real
  power-user need and, for the agent positioning, a first-class one (an agent
  asking "find the configs"). Nothing in the core offers it.
- **`du`'s breakdown.** Unix `du` prints a cumulative size per directory,
  bottom-up, ending with the total (`du -s` is the summary-only mode storix's
  `du` currently is). `sx du` shows only the total, which is `du -s` behavior,
  not the default.
- **`tree` flavors.** The user wants eza-style depth (`--level`), a long form
  with sizes and kind, and sorting - all of which need the recursive walk with
  entry metadata, which the CLI's current hand-rolled `tree` loop does not
  expose.

A dead first attempt (`src/storix/core/` with `Tree`/`Finder`/`word_count`) is
removed in this change: unreferenced, untested, sync-only, and built on
injected checkers rather than the port. See ADR 0023's rejection of handing out
port DTOs and the "no logic in the driving adapter" rule
(`docs/design/architecture.md`).

## Decision

One core primitive, two sugar methods over it, and the CLI consumers built on
top - all streaming, all on `scandir`.

**Core (`_async/core.py`, codegen):**

- `walk(path=None, *, all=False, top_down=True) -> AsyncIterator[DirEntry]` -
  recursively yields every descendant entry, lazily. `top_down=True` yields a
  directory before its children (pre-order, for find/tree); `False` yields
  children first (post-order, for du's bottom-up accumulation). Hidden entries
  excluded unless `all`. Per-level fan-out goes through the `concurrent` helper
  (ADR 0025), so the async flavor walks siblings concurrently and the sync CLI
  inherits it once that lands.
- `find(path=None, *, name=None, kind=None) -> AsyncIterator[DirEntry]` - `walk`
  filtered: `name` is a glob (`fnmatch`, matched against the basename), `kind`
  restricts to files or directories. The power-user / agent method.
- `glob(pattern, path=None) -> AsyncIterator[StorixPath]` - pathlib-shaped
  (`*`, `**`, `?`) over the walk, yielding paths.

`ls` stays the single-directory listing; `walk`/`find`/`glob` are the recursive
family, named after their unix/pathlib precedents (AGENTS.md, "Naming the
public surface"). No `Tree`/`Finder` classes - a streaming method is leaner
than a class with injected checkers, which was the dead code's mistake.

**CLI consumers (`sx`, presentation only):**

- **`du` becomes 1:1 with unix.** Default: a cumulative size per directory,
  bottom-up, ending with the arg's total (via a post-order `walk`). `-s`
  summary-only (today's behavior), `-a` include files, `-h` human, `-d/--max-
  depth N`. The *walk* and size accumulation are core; the CLI only formats.
- **`tree` gains flavors.** `-L/--level N` (depth cap), `-l/--long` (size + kind
  columns, eza-style), `--sort name|time|size`. It renders the `walk`; the
  branch-drawing and icons stay in the CLI.

**Deferred, recorded so they are not re-litigated (roadmap):** `wc` and the
`|`-pipe composition stay dropped (ADR 0023 discussion) - a `wc` ADR only if a
concrete need appears; content `wc` is `len(cat.splitlines())`, listing `wc` is
`len(ls())`, and pipe composition belongs in the shell (`sx ls | wc`), not the
Python API.

Rejected: computing the `du` breakdown by calling `du` per subdirectory - each
call re-walks its subtree, O(n * depth); one post-order walk is O(n). Rejected:
a `Tree` class taking injected `dir_iterator`/`dir_checker` (the dead code's
shape) - more machinery than a generator method, and it re-passes the session's
own logic back into itself.

## Consequences

The recursive listing has one home; `find`/`glob` give humans and agents real
search; `du` matches unix; `tree` gets its eza-style flavors - all as thin
consumers of one walk, not three re-implementations. Depends on `scandir`
(ADR 0023) and, for the concurrent walk, `concurrent` (ADR 0025), so it lands
after both. `DirEntry` already carries the size/kind these need.

0.4.x (backward-compatible feature -> patch; ADR 0021).

Implementation:

- [x] remove the dead `src/storix/core/`.
- [ ] `walk`/`find`/`glob` on `_async/core.py`; `just gen`; conformance +
      core tests (recursion, top_down/post-order, `name`/`kind` filters, glob
      `**`, laziness).
- [ ] `sx du` breakdown + `-s`/`-a`/`-d`; `sx tree` `-L`/`-l`/`--sort` - both
      consuming the walk; delete the CLI's hand-rolled tree recursion.
- [ ] docs: guide + reference + release notes; roadmap ticks find/glob/du/tree
      and records wc/pipe as ADR-when-picked.
