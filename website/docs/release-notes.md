# Release Notes

## [0.4.8] - 2026-07-22

### What's Changed
#### Features
* feat(core): bulk emptiness from one recursive listing by @mghalix in https://github.com/mghalix/storix/pull/28
* feat(core): level-buffered concurrent walk by @mghalix in https://github.com/mghalix/storix/pull/29
* perf(backends): list-first list_dir, stat only to disambiguate by @mghalix in https://github.com/mghalix/storix/pull/30
* perf(cli): concurrent push/pull transfers and batched mkdirs by @mghalix in https://github.com/mghalix/storix/pull/31
* feat(cli): improve transfer setup and storage-root diagnostics by @mghalix in https://github.com/mghalix/storix/pull/32
* feat: storage-root provisioning protocol and sx provision by @mghalix in https://github.com/mghalix/storix/pull/34
#### Fixes
* fix(core): restore unix depth-first walk emission over concurrent traversal by @mghalix in https://github.com/mghalix/storix/pull/33
* fix(cli): complete push/pull second argument from the correct side by @mghalix in https://github.com/mghalix/storix/pull/35

## [0.4.7] - 2026-07-21

Storix 0.4.7 brings major CLI usability and performance upgrades to `sx`, featuring
complete eza-grade icon coverage, rich `ls -l` long listings, custom subcommand aliases in
`storix.toml`, recursive `push` and `pull` transfer commands and context-aware shell completions.

### Added

- **Full eza Icon Catalog**: Integrated 100% of eza's icon catalog (623 file extensions,
270 exact filename mappings, and modeline definitions) into `sx` with Nerd Font icon
rendering and aligned file classification.
- **Rich `ls -l` Long Listing**: Formats Unix/eza style file permissions/kind, human-
readable byte sizes, modification date/time, and icon-prefixed labels across single and
multi-column terminal views.
- **Subcommand Aliases (`[cli.alias]` / `[cli.aliases]`)**: Configure custom CLI shortcuts
in `storix.toml`, `.storix.toml`, or `pyproject.toml` (e.g. `l = "ls -l"`, `ll = "ls -la"`,
`lt = "tree --level=2"`), automatically expanded in both `sx` commands and the interactive
REPL shell.
- **`push` and `pull` Commands**: Transfer single files or entire directory trees
recursively between host disk and remote storage backends (`sx push <local> [remote]` and
`sx pull <remote> [local]`).

### Changed

- **Context-Aware Shell Completions**: `sx` shell tab completion dynamically detects
argument context—completing local host disk paths for `push <1>` and `pull <2>`, and remote
backend paths for `push <2>`, `pull <1>`, `cd`, `ls`, and all other backend operations.
- **Path & Space Handling**: Tilde (`~`) home shortcuts and spaces/special characters in
local and remote paths are automatically expanded and backslash-escaped during shell tab
completion.

### Fixed

- **Monotonic Transfer Progress Bar**: Accumulated byte deltas across multi-file directory
transfers so the Rich progress bar advances steadily from 0% to 100% without resetting per
file stream.

### Removed

- **Legacy `upload` and `download` commands**: Replaced completely by `push` and `pull`.

## [0.4.6] - 2026-07-20

Storix now has a clearer public entry point for developers exploring typed,
streaming storage workflows. This release focuses on documentation, examples,
package discovery, and community participation. SDK runtime behavior is
unchanged.

### Added

* A contribution guide and structured GitHub forms for bug reports and
  workflow discussions.
* Runnable streaming recipes demonstrating subprocess output written
  incrementally through Storix, including an optional yt-dlp integration.
* Clear maintainer priorities and community-driven workflow guidance in the
  public roadmap.

### Changed

* The README and documentation homepage now present Storix as an async-first,
  streaming-first storage SDK across local storage, Azure, S3, and GCS.
* Package metadata, keywords, homepage links, and project URLs now match the
  current documentation and provider support.
* Community guidance now directs open-ended workflows and API ideas to GitHub
  Discussions, while confirmed bugs remain in GitHub Issues.
* FastAPI examples now distinguish chunked `UploadFile` reads from raw request
  body streaming and avoid implying that multipart uploads bypass framework
  spooling.

### Fixed

* The Workflows discussion category now loads its structured workflow form
  correctly.

## [0.4.5] - 2026-07-18

Recursive search is now a first-class core capability, with a faster and more
capable Unix-style CLI built on the same primitives.

### Added

- `Storix.walk` lazily traverses directory trees in top-down or bottom-up
  order, while `Storix.find` filters by glob and entry kind and `Storix.glob`
  provides pathlib-style recursive matching.
- `find(kind=...)` accepts the typed `PathKindStr` literals `file` and
  `directory` as well as `PathKind` values.
- `sx find` exposes recursive search from the command line.
- `sx du` gains summary, per-file, and maximum-depth modes, and `sx tree` gains
  depth limits, long output, and sorting by name, time, or size.
- A listing-and-searching recipe and reproducible listing benchmarks document
  the new APIs and their performance model.

### Changed

- `sx ls` and `sx tree` batch per-entry metadata lookups through Storix's
  concurrency helper, avoiding one serial network round trip per entry on
  remote backends.

### Fixed

- `find` and `glob` can include hidden entries when `all=True`.
- `sx tree -l` no longer leaks dim styling from metadata columns into names.

### Removed

- The unreferenced and unexported legacy `src/storix/core` prototype is gone;
  the supported `Storix` methods now own recursive traversal. This does not
  remove a public API.

## [0.4.4] - 2026-07-18

Rich recursive-listing groundwork, Azure Blob URL parity, and real concurrency
in the sync flavor. Three backward-compatible features. See ADRs 0023-0025.

### Added

- `Storix.scandir` yields a directory's entries lazily as rich `DirEntry`
  objects (name, absolute path, `kind`, and any size the listing carried for
  free), after `os.scandir`; `iterdir` is its lazy-names sibling (after
  `pathlib`); `is_empty` answers whether a directory holds anything in one
  round trip (hidden entries counted, so a dotfile-only directory is not
  empty). `ls` is reimplemented over `scandir` with unchanged behavior, so the
  kind/size the port already produces reaches consumers without a stat per
  entry. `DirEntry` is exported from `storix` and `storix.aio`. ADR 0023.
- `AzureBlobBackend.url()` mints a read SAS from an account key locally
  (`generate_blob_sas`, pure HMAC, no request), 1:1 with `AzureBackend` (ADLS):
  the same code and credential now produce a URL on any Azure account kind.
  `presigned_urls` is advertised when the credential can sign, and
  `azure-storage-blob` joins the lean `azblob` extra so it works there too.
  ADR 0024.

### Changed

- The sync flavor's multi-target operations (`cat`, `touch`, `mkdir`, `rm`,
  `mv`, `cp`, and `du`'s subtree walk) now run concurrently. A thunk-based
  `concurrent` helper dispatches the fan-out to a bounded `ThreadPoolExecutor`
  in sync and to `asyncio.gather` in async; because the backends do
  GIL-releasing blocking I/O, the sync threads give genuine I/O concurrency. So
  `sx du`/`cp`/`rm` on a wide cloud tree parallelize like the async API. The
  async path is unchanged, error semantics stay unwrapped (the storix taxonomy
  survives), and codegen is untouched. ADR 0025.
- The `sx` CLI consumes the new core listing: its `list_entries` and
  `has_children` re-implementations are gone in favor of `scandir` and
  `is_empty`, so listing semantics live in one place.

## [0.4.3] - 2026-07-17

The `sx` revamp: completion, progress, icons, unix-consistent output, and a
persistent config file. Library code is untouched; every change lives in the
CLI. See ADR 0022.

### Added

- `Storix.layers` reports the active layers, outermost first, and
  `Storix.base_backend` walks past them to the real provider. Reading the
  stack is a legitimate need - naming what wraps a session, recording it in an
  audit trail - and the alternative was duck-typing on a layer's private
  `_inner`, which is what the CLI had been doing. Composition stays with
  `with_layer` / `without_layer`; layers are identified structurally, so
  custom ones appear beside the built-ins.
- The interactive shell runs on `prompt_toolkit`: Tab completes command names
  (with their descriptions) and remote paths, directories complete with a
  trailing slash, and arrow-key history works. Completion sources a live
  listing, so an active cache layer makes repeats instant.
- `upload` and `download` render a live progress bar driven by the
  `ObservabilityLayer`. `sx` owns the total (the local file's size for an
  upload, `stat` for a download) and the layer supplies transferred bytes, per
  ADR 0019.
- Listings decorate entries with Nerd Font icons, the glyph set eza and
  nvim-web-devicons draw from, with per-category colors. The table ships as
  package data (`storix/cli/data/icons.toml`), so retheming is a data edit.
  Icons disable automatically when output is not a terminal.
- A persistent config file for CLI preferences and an always-on layer stack
  (ADR 0022). Precedence, strongest first: flags, the nearest project config
  (`storix.toml` > `.storix.toml` > `pyproject.toml [tool.storix.cli]`, found
  by walking upward), `STORIX_CLI_*` environment variables,
  `~/.config/storix/config.toml`, defaults. The ordered `[[cli.layers]]` array
  resolves the curated CLI layer set (`cache`, `sandbox`) by name, completing
  the DSL ADR 0015 deferred. Unknown keys, and connection settings put in the
  CLI table by mistake, exit with the correct home named rather than being
  silently ignored.
- `ls -t` (sort by modification time) and `-r` (reverse); `tree -a`; `du -h`;
  `--icons/--no-icons`.
- CLI preferences `provider` (which backend `sx` opens by default, overriding
  `STORIX_PROVIDER` for the CLI only, with `-p` still winning) and
  `dir_contents` (whether flat listings check emptiness).
- `r2` and `minio` install extras, aliases for `s3`, whose API both stores
  speak. Installing for the store you use no longer requires knowing that.
- The configured `[[cli.layers]]` stack covers every built-in layer a config
  file can express: `cache`, `sandbox`, `url`, and `metadata`. The two
  capability-backfilling layers go through `with_layer_missing`, so one config
  yields a native SAS URL where the backend has one and a `data:` URL where it
  does not.

### Changed

- `du -h` and `ls -l` humanize sizes in binary units with coreutils'
  single-letter suffixes (`165M`), matching `du -h` / `numfmt --to=iec
  --round=up` exactly, including the boundary where rounding promotes the unit.
- `tree` closes with unix tree's `N directories, M files` summary, counts the
  root directory as tree does, and reads entry kinds from the listing instead
  of a stat per child (one request per level).
- `upload` detects a content type (extension first, else sniffing the head)
  and sets it on backends advertising the `content_type` capability. Uploads
  previously left Azure to default every blob to `application/octet-stream`.
- `upload` and `download` stream instead of materializing the whole file, so a
  transfer larger than memory succeeds.
- `du` echoes the path as given rather than the resolved one, like unix `du`.
- The CLI package is split by concern: `app` (commands), `state` (session and
  layer-stack access), `render` (consoles, icons, sizes), `config`
  (preferences), `shell` (REPL), `data/` (assets).
- The `cli` extra gained `prompt-toolkit`; the launcher's missing-extra guard
  covers it.

### Fixed

- Directory icons tell the truth about emptiness. Flat listings now check
  (`dir_contents`, on by default), so an empty folder reads as empty and a
  populated one as populated, rather than every directory sharing one glyph.
  `tree` already knew, for free.
- `sx` verifies a sandbox root before jailing the session. A missing root
  used to surface later, correctly rescoped and unreadable, as
  `PathNotFoundError: path '/' does not exist` - inside the jail the missing
  root *is* `/`. The check names the real root and the provider while it
  still can.
- Well-known filenames (`Makefile`, `Dockerfile`, `pyproject.toml`,
  `.gitignore`, ...) get their own icon instead of the generic file glyph.
- The shell prompt is just the working directory again. The backend name and
  layer stack, which grow with every layer, print once in the start banner
  and on demand via `provider` instead of prefixing every command.
- `SandboxLayer` no longer reports `path '/' does not exist` when its root is
  missing: true inside the jail, where the absent root *is* `/`, and nonsense
  to anyone reading it. It now says `sandbox root does not exist`, still
  without naming the real root it exists to hide. Library users get this too,
  not just `sx`.

## [0.4.2] - 2026-07-16

Object stores: S3, GCS, and Azure Blob through the first external backend
adapter. See ADR 0020.

### Added

- `S3Backend` and `GcsBackend` over an internal opendal engine, reaching
  Amazon S3, S3-compatible stores (MinIO, R2), and Google Cloud Storage, with
  the `s3` and `gcs` extras.
- `AzureBlobBackend` and a self-detecting `azure` provider that builds either
  Azure backend from one schema, so a flat (non-HNS) account works without
  code changes.
- Lean install profiles: `azadls` (ADLS Gen2 only) and `azblob` (blob only);
  `azure` composes the two.
- Documentation for the object-store backends: guide, reference, install
  profiles, a recipe, and an S3 sample against a throwaway local MinIO.

### Fixed

- `storix[azure]` bundles the blob engine, and optional-dependency errors name
  the exact extra to install.

## [0.4.1] - 2026-07-16

Transfer progress as composable observability events, with documentation,
typing, and project presentation improvements.

### Added

- `ObservabilityLayer` wraps streaming reads and writes and emits a cumulative
  `TransferEvent` for each transferred chunk. Its sink may be synchronous or
  asynchronous, and omitting the sink leaves the layer as a pure passthrough.
- `ObservabilityLayer` and `TransferEvent` are exported from the sync, async,
  and top-level public APIs.
- The documentation includes an observability guide, API reference, and a
  runnable Rich progress-bar recipe.

### Changed

- Storix dataclass DTOs now share the `@dto` house-style decorator, keeping
  them consistently frozen, slotted, and keyword-only without changing their
  public behavior.
- The README and documentation site use the refreshed Storix brand kit,
  including dark/light banners, favicon, and header logo variants.

### Fixed

- Layer re-composition and Click command annotations now pass the configured
  static type checks without changing runtime behavior.

## [0.4.0] - 2026-07-15

`when_missing` infers its capability from the layer. Breaking combinator
signature. See ADR 0018.

### Changed (breaking)

- The free `when_missing` combinator infers the gated capability from the
  layer's `provides` ClassVar and drops the explicit first argument, matching
  `with_layer_missing`. It now forwards constructor args to the layer, so the
  conditional case no longer needs `functools.partial`. Migration is
  mechanical: delete the leading capability argument.

  ```python
  # was
  when_missing(Capability.PRESIGNED_URLS, DataUrlLayer)
  # now
  when_missing(DataUrlLayer)

  # constructor kwargs forward directly (no functools.partial):
  when_missing(MetadataLayer, serialize=dumps, deserialize=loads)
  ```

  It raises `ValueError` if the layer declares no `provides` (nothing to
  infer, use it unconditionally instead). `functools.partial` stays the shape
  for unconditional layers in a `layers=` list.

### Added

- `LayerFactory` (the ParamSpec layer-factory protocol behind `with_layer` and
  now `when_missing`) is a public export from `storix` and `storix.aio`, beside
  `BoundLayer`, so integrators writing their own layer helpers can name the
  type.

## [0.3.0] - 2026-07-14

Bounded, provider-aware streaming in both directions. This is a breaking
backend-port release. See ADR 0017.

### Added

- `get_storage("memory")` and `STORIX_PROVIDER=memory` now expose the built-in
  zero-configuration memory backend through the same typed factory as local and
  Azure storage.
- `Storix.stream(..., chunk_size=)` now exposes a consumer-facing maximum
  chunk size. It splits oversized provider chunks without coalescing smaller
  ones; `None` selects the backend default.
- `Storix.echo(..., chunk_size=)` controls target write batches for every
  accepted source shape. Tiny iterator yields are combined and oversized
  values are split with a linear, bounded-memory stdlib implementation.
- The backend port now has explicit whole-object and streaming pairs:
  `read`/`read_stream` and `write`/`write_stream`. `BackendBase` derives either
  form from the other, so a custom backend may implement native streaming or
  the simpler whole-object form independently per direction.
- Azure transfer settings: `read_chunk_size` (4 MiB default),
  `write_chunk_size` (4 MiB), and `read_prefetch_size` (32 MiB), also available
  as `STORIX_AZURE_*` configuration.

### Changed (breaking)

- `StorageBackend.write(path, data, ...)` now takes one complete `bytes`
  payload. Streaming backends implement `write_stream(path, iterator, ...)`.
- `StorageBackend.read_stream` and `write_stream` accept the keyword-only
  `chunk_size` control. Custom backends and layers overriding either method
  must add it and honor the port contract.
- Explicit zero or negative chunk sizes raise stdlib `ValueError`. There is no
  `-1` whole-file sentinel; use `cat()` for a complete read.

### Fixed

- Local and memory reads no longer reuse the former 100 MiB write batch, which
  made ordinary files appear as one chunk. Generic/local defaults are now 1
  MiB, while Azure keeps provider-appropriate 4 MiB transfer batches.
- Azure reads no longer coalesce SDK chunks just to fill the requested output
  size, and Azure writes no longer issue one append request per tiny producer
  yield.
- The `cli` extra now declares its direct `click` dependency. The `sx` launcher
  reports an actionable install command without a traceback when the extra is
  absent, and Azure uses the same optional-extra error style.
- Azure client authentication failures now raise `ConfigurationError` with a
  credential hint. `PermissionDeniedError` is reserved for authorization
  failures after authentication succeeds.

## [0.2.2] - 2026-07-12

Per-op cache bypass, and public-API fixes.

### Added

- `Storix.without_layer(*types)` - a *new* session with the given layer
  types bypassed, the rest re-composed (absent types are a no-op; cwd is
  preserved). `Storix.uncached` is sugar for `without_layer(CacheLayer)`,
  for a guaranteed-fresh read: `fs.uncached.ls()`. Layers gate this with
  `removable: ClassVar[bool]` (default `True`); `SandboxLayer` sets it
  `False` - a jail is a security boundary and raises
  `NonRemovableLayerError` if you try to strip it. (ADR 0016)
- `BoundLayer` (`Callable[[StorageBackend], StorageBackend]`, the
  `layers=` / `with_layer` shape) is now a public export from `storix`
  and `storix.aio`, so consumers stop redefining it.

### Fixed

- `CacheOp`, `CacheStore`, and `InMemoryCacheStore` are now in the
  `__all__` of both `storix` and `storix.aio` - they were importable at
  runtime but rejected by type checkers. `storix.aio` also regains the
  `PathKind`/`RawStat` exports the sync namespace already had, so the two
  flavors are symmetric (now guarded by a test).

## [0.2.1] - 2026-07-12

Configurable read-through caching, in the library and the `sx` CLI.

### Added

- `CacheLayer`: a configurable per-op read-through cache. metadata
  (stat/list/exists, on by default), `du`, `read` (content) and `url`
  (presigned) each toggle as `bool | CacheOp` - `cache(ttl=, store=,
  max_bytes=)` per op, or the layer defaults. Eviction is per op on every
  mutation through the layer (metadata: path+parent; du: ancestor chain;
  read: the file); `url` is TTL-only, capped to the URL's lifetime. Keys
  follow `<namespace>[:<environment>]:<op>:<locator>` and are keyed on the
  physical `locate()`, so sessions sharing a store never collide.
  (ADR 0014)
- Pluggable `CacheStore` - a cashews-shaped async protocol
  (`get`/`set`/`delete`/`delete_match`) with loose returns, so a
  `cashews.Cache` (Redis, disk, ...) satisfies the async flavor with no
  adapter. The sync flavor uses synchronous implementations of the same four
  methods. Ships
  `InMemoryCacheStore` (optional `maxsize` LRU) as the default. New
  exports: `CacheLayer`, `CacheOp`, `cache`, `CacheStore`,
  `InMemoryCacheStore`.
- CLI layer flags: `sx --cache [--cache-ttl N]` (metadata+du+read, content
  capped at 8 MiB) and `sx --sandbox PATH`, applied sandbox-innermost /
  cache-outermost. The REPL prints the active stack and gains a `refresh`
  built-in (namespace-scoped cache clear); `provider` lists the layers and
  the backing store. (ADR 0015)
- `sx url <file> --expire <seconds>` to set presigned-URL lifetime.

### Changed

- The `sx` shell prompt and `provider` now show the real backend annotated
  with the active stack (e.g. `LocalBackend(cache, sandbox)`) instead of
  the outermost layer's class name.

### Notes

- `CacheLayer` correctness assumes a single writer of its store(s); pass
  `ttl` to bound staleness (the default never expires). A declarative
  `[tool.storix.cli]` layer stack and CLI cache-store selection
  (disk/redis) are designed and deferred - see `docs/adr/0015` and
  `docs/roadmap.md`.

## [0.2.0] - 2026-07-12

Ground-up hexagonal rework: one core engine (`Storix`) owns every unix
semantic over a small backend port; the sync flavor is generated from
the async source of truth. Breaking release.

### Added

- One `Storix` engine over a ~14-method backend port; the sync flavor is
  generated from the async source of truth (`scripts/unasync.py`), so the
  two never drift and one conformance suite proves both.
- `MemoryBackend` (dict-backed reference backend) alongside `LocalBackend`
  and the HNS-only `AzureBackend`; bring your own via the port +
  `register_backend()`.
- Layers - backends that wrap backends: `SandboxLayer` (chroot as
  middleware, with `to_real`/`to_virtual` for audit), `DataUrlLayer` and
  `MetadataLayer` (portable capabilities - `url()` and custom metadata on
  backends that lack them natively), and `LayerBase` for writing your
  own. Compose with `Storix(be, layers=[...])`, `fs.with_layer()`
  (ParamSpec-typed, Starlette-style kwarg forwarding), or
  `fs.with_layer_missing()` (skips the layer when the backend is already
  native - capability inferred from the layer's `provides`).
- `temporary()` and `scratch(backend, root=...)` disposable/pinned
  workspaces; `fs.scratch()` and `fs.chroot()` on any session.
- Capabilities with typed gates (`UnsupportedOperationError` names the
  missing one): `content_type`, `custom_metadata` (write-through +
  `fs.set_metadata(..., merge=)`), `presigned_urls` (`fs.url()`, SAS on
  Azure) and the backend-agnostic `fs.data_url()`.
- `fs.stream()` (streaming `cat`), `fs.resolve()` (navigable/bookmarkable
  port path) and `fs.locate()` (physical URI - file://, abfss:// - for
  audit/cross-system reference, resolved through any sandbox).
- Typed factory: `get_storage('azure', container=...)` with full IDE
  completion, `register_backend()` + `available_providers()` for third
  parties; namespaced `STORIX_*` configuration.
- `MetadataLayer` takes pluggable `serialize`/`deserialize` callables
  (default stdlib json; pass `orjson.dumps`/`orjson.loads` or any
  object<->bytes pair).
- Typed, fact-carrying error taxonomy (`storix.errors`) with errno and
  dual stdlib inheritance; every failure raises - no boolean returns.
- Rewritten `sx` CLI + REPL on the new core (session cwd persists; the
  shell reuses the Typer parser, so every flag matches the one-shot CLI).
- `py.typed`: the package is now typed for downstream checkers.

### Changed (breaking)

| 0.1.x | 0.2.0 |
|---|---|
| `LocalFilesystem(...)` | `Storix(LocalBackend(base))` |
| `AzureDataLake(...)` | `Storix(AzureBackend(container, account_name=..., credential=...))` |
| `STORAGE_*` / `ADLSG2_*` env vars | `STORIX_PROVIDER`, `STORIX_LOCAL_*`, `STORIX_AZURE_*` (see env.example) |
| `touch(path, data)` | `touch(*paths)` creates/refreshes only; data goes through `echo` |
| `rm(path)` file-only + `rmdir(recursive=True)` | `rm(*paths, recursive=True)` is rm -r; `rmdir(*paths)` strictly empty dirs |
| `mv(src, dst)` / `cp(src, dst)` | variadic, last argument is the destination (unix) |
| `ls()` shows dotfiles | hidden by default; `ls(all=True)` shows them |
| failed ops return `False` | typed exceptions, always |
| `sandboxed=True` constructor flag | explicit `SandboxLayer(backend, root=...)` composition |
| `FileProperties.file_kind` | `FileProperties.kind` |
| `PathNotFoundError` subclasses `ValueError` | subclasses `FileNotFoundError` only |

### Notes

- Azure behavior is wire-verified: the full conformance suite (80
  integration params, both flavors) passes against a real HNS account.
  Run yours with `pytest -m integration` (needs `ADLSG2_*` credentials).
- `tree`/`find`/`wc` are not yet core methods (the CLI provides `tree`);
  along with `MountLayer`, `CacheLayer`, range reads, `glob`, and a
  pathlib-style adapter they are on the 0.2.x/0.3.x roadmap
  (`docs/roadmap.md`).
- Design rationale for the rework lives in `docs/adr/` (13 records).


## [0.1.3] - 2026-07-05

### Fixed

- Loosened dependency lower bounds to their tested minimums so `storix` no longer
  conflicts with packages that pin older versions (e.g. `pyrit`'s `aiofiles>=24,<25`):
  `aiofiles>=24.1.0`, `rich>=13.0.0`, `typer>=0.13.0`, `loguru>=0.7.2`,
  `azure-storage-file-datalake>=12.14.0`, `aiohttp>=3.9.0`. No code changes;
  functionality is identical to 0.1.2.
- Removed the unused `rich-toolkit` dependency from the `cli` extra.

## [0.1.2] - 2026-06-02

### Improvements

- `StorixPath` is now always in POSIX path form, making it platform-agnostic across
  Windows and Unix systems.
- `StorixPath` is now recognized by Pydantic as a valid type for model fields and
  validation.

### Internal

- `storix.errors` is now eagerly imported (no longer lazy-loaded), since the module
  is lightweight and needed at import time for isinstance checks.

## [0.1.0] - 2025-12-14

### Highlights

- Add test coverage for `du()` / `stat()` and `StorixPath` helpers across providers.

### BREAKING CHANGES

- `ls()` now always returns `StorixPath` items (never `str`).

    Migration:
    - If you previously relied on strings, convert explicitly:

        ```python
        files = fs.ls("/")
        names = [p.name for p in files]
        paths_as_str = [str(p) for p in files]
        ```

### Internal

- Added test coverage for `du`/`stat` and `StorixPath` helpers across providers.

## [0.0.3] - 2025-12-14

### Features

- Smart MIME type inference when writing files (path-first → buffer sniff →
  default), with explicit `content_type` override for sync/async Azure `touch`
  and `echo`.
- New helpers: `storix.utils.detect_mimetype` and
  `storix.utils.guess_mimetype_from_path`.
- Unified missing-path exception: `PathNotFoundError` (subclasses
  `FileNotFoundError` & `ValueError`) replacing previous raw `ValueError` while
  keeping backward compatibility.
- Introduce StorixPath as the standardized return for logical path operations + bonus
  defined operations such as mimetype detection and file type guess
- Introduce new function `echo` for efficient streaming writes
- Introduce simple implementation of `tree` and extras such as `wc` and `find`

### Fixes

- Storage protocols are now runtime checkable to easily check isinstance() and support
  for tools that enforce type hints through instance checks like pydantic
- settings are loaded by `get_settings`; to avoid cached settings, allowing
  manipulation of environment dynamically during runtime affecting filesystems
  initialization defaults and `get_storage()`.

## [0.0.2] – 2025‑10‑16

### Highlights

- **Python 3.12+ support** – raised the minimum Python version to 3.12 (tested
  on 3.13) and dropped support for older versions.
- **`src` layout & build upgrade** – moved all code under the `src/` directory
  and switched from `hatchling` to **uv_build** for packaging. This aligns with
  best practices and simplifies installation via `uv`.
- **Lazy imports & module reorganisation** – refactored modules into `storix`
  and `storix.aio` packages under `src`, introducing `__getattr__` to lazily load
  providers (avoids importing optional dependencies until needed).
- **Sandbox refactor** – replaced `PathSandboxable` with **PathSandboxer** and
  `SandboxedPathHandler`, strengthening sandbox enforcement and path‑resolution
  logic to block traversal & symlink escapes.
- **New utility & model modules** – added `storix/utils` (e.g. `to_data_url`,
  `PathLogicMixin`) and data models such as `AzureFileProperties` to standardize
  metadata returned by `stat()`.
- **Scripts & CLI updates** – updated scripts (`coverage`, `format`, `lint`) to
  operate on the new `src` layout; `pyproject.toml` now defines pytest discovery
  paths and richer `ruff` formatting/linting rules.
- **Miscellaneous improvements** – improved `get_storage()` typing
  (`StrPathLike`), added lazy provider lookup maps, fixed configuration for
  docstring formatting, and defined version statically rather than dynamically.

### Migration notes

- **Sandbox handlers** – if you rely on custom sandbox handlers, update them to
  implement `PathSandboxer` rather than the old `PathSandboxable` interface.
- **Async API** – the asynchronous API remains identical; just import from
  `storix.aio` and use `await` on file operations.

## [0.0.1] - 2024-07-06

### 🎉 Initial Release

Storix is a blazing-fast, secure, and developer-friendly storage abstraction
for Python that provides Unix-style file operations across local and cloud
storage backends.

### ✨ Key Features

- **Unified API**: Seamless sync and async support with identical interfaces
- **Local Filesystem & Azure Data Lake Storage Gen2**: Production-ready backends
- **CLI Tool (`sx`)**: Interactive shell and command-line interface
- **Sandboxing**: Secure file operations with path traversal protection
- **Smart Configuration**: Automatic `.env` discovery and environment variable support

### 📦 Installation

```bash
# Basic (local filesystem only)
uv add storix

# With CLI tools
uv add "storix[cli]"

# With Azure support
uv add "storix[azure]"

# Everything included
uv add "storix[all]"
```

### 🚀 Quick Start

```python
from storix import get_storage

fs = get_storage()
fs.touch("hello.txt", "Hello, Storix!")
content = fs.cat("hello.txt").decode()
print(content)  # Hello, Storix!
```

### 🔧 Configuration

Create a `.env` file:

```env
STORAGE_PROVIDER=local
STORAGE_INITIAL_PATH=.
STORAGE_INITIAL_PATH_LOCAL=/path/to/your/data
STORAGE_INITIAL_PATH_AZURE=/your/azure/path
ADLSG2_CONTAINER_NAME=my-container
ADLSG2_ACCOUNT_NAME=my-storage-account
ADLSG2_TOKEN=your-sas-token-or-account-key
```

### 📚 Documentation

- [GitHub Repository](https://github.com/mghalix/storix)
- [Sandbox Implementation](https://github.com/mghalix/storix/blob/v0.1.0/docs/SANDBOX_IMPLEMENTATION.md)
- [Async Migration Guide](https://github.com/mghalix/storix/blob/v0.1.0/docs/ASYNC_MIGRATION.md)

---

## Version History

### <0.1.2> – 2026-06-02

- `StorixPath` is now always in posix path form - platform agnostic.
- `StorixPath` is now recognized by pydantic.
- `storix.errors` is now eagerly imported for reliable isinstance checks.

### <0.1.1> – 2026-06-02 *(yanked — republished as 0.1.2)*

### <0.1.0> – 2025-12-14

- Breaking: `ls()` now always returns `StorixPath` items (never `str`).
- Added test coverage for `du()` / `stat()` and `StorixPath` helpers across providers.

### <0.0.3> – 2025-12-14

- Smart MIME type inference for sync/async Azure `touch()` and `echo()` (with explicit
  `content_type` override).
- Added `storix.utils.detect_mimetype()` and `storix.utils.guess_mimetype_from_path()`.
- Unified missing-path exception as `PathNotFoundError` (subclasses `FileNotFoundError`
  & `ValueError`).

### <0.0.2> – 2025‑10‑16

- Introduced Python 3.12+ requirement and removed support for Python < 3.12.
- Adopted a `src` layout and switched packaging to `uv_build`.
- Implemented lazy imports via `__getattr__` and reorganized modules under
  `storix` and `storix.aio`.
- Refactored sandbox to use `PathSandboxer`/`SandboxedPathHandler`.
- Added new utility and model modules (`utils`, `AzureFileProperties`).
- Updated scripts and tooling (`coverage`, `format`, `lint`, `pyproject.toml`).

### <0.0.1> - 2024-07-06

- Initial release with local filesystem and Azure Data Lake Storage Gen2 support
- Sync and async APIs with unified interface
- CLI tool with interactive shell
- Sandboxing and security features
- Comprehensive test suite and documentation
