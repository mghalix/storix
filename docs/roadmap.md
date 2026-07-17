# Roadmap

Value-ordered; conversion before novelty. Rationale for the positioning
(ergonomic/agent layer over any plumbing, never a plumbing competitor)
and for individual decisions: `docs/adr/`.

## 0.2.0 (release gate)

- [x] CLI rewrite onto the sync core (`sx`, REPL)
- [x] everything else: hexagonal core, codegen, backends
      (memory/local/azure wire-verified), layers, capabilities,
      metadata/URLs, config/factory, workspaces, teardown,
      DataUrlLayer + MetadataLayer (portable capabilities via layers)

## 0.2.1

- [x] `CacheLayer`: configurable read-through cache. Per-op specs
  (`metadata` on by default; `du`, `read`, `url` opt-in) as
  `bool | CacheOp`, each with its own `ttl`/`store` (share one or split,
  e.g. metadata in Redis + content on a bounded local store) and,
  for `read`, a per-file `max_bytes` cap. Evict-on-mutation
  (metadata: path+parent; du: ancestor chain; read: the file); `url` is
  TTL-only and capped to the URL lifetime. Keys follow
  `<namespace>[:<environment>]:<op>:<locator>`, keyed on the physical
  `locate()` so sessions sharing a store never collide. Pluggable
  `CacheStore` (cashews-shaped; in-memory default with optional
  `maxsize` LRU, swap for Redis/etc.) - vroom (ADR 0014)

- [x] CLI layers: `sx --cache [--cache-ttl N]` (metadata+du+read,
  bounded) and `--sandbox PATH`, applied sandbox-innermost /
  cache-outermost; REPL start banner + `refresh` command +
  `provider` layers line. Opt-in, shell is where it pays off (ADR 0015)

## 0.2.2

- [x] `Storix.without_layer(*types)` / `uncached` - per-op layer bypass
  (a fresh-read view), gated by `removable` so a `SandboxLayer` can never
  be stripped (`NonRemovableLayerError`). `BoundLayer` made a public
  export; `CacheOp`/`CacheStore`/`InMemoryCacheStore` added to `__all__`
  of both flavors (ADR 0016)

## 0.4.1 - 0.4.3 (next)

Three backward-compatible features, so patches (0.4.0 is published;
versions are monotonic, there is no going back to fill 0.2.x/0.3.x).
Ship bundled as 0.4.1 or as successive patches:

- 0.4.1 `ObservabilityLayer` (v0: transfer events): a port-wrapping layer
  that counts read/write bytes at the pull boundary and emits
  `TransferEvent`s to a consumer-supplied sink - progress bars for `sx`
  and library consumers with zero core churn. The consumer owns the total
  (a percentage needs one; storix only knows bytes-so-far). First slice of
  the audit story (op-level events later), not a throwaway (ADR 0019)
- [x] 0.4.2 `OpendalBackend`: first external adapter, async-native + presign,
  spike-gated (ADR 0020)
- [x] 0.4.3 `sx` UX: prompt_toolkit autocomplete + upload/download progress
  bars over the ObservabilityLayer; grew into the full CLI revamp - Nerd
  Font icons (data-driven), unix/coreutils-consistent output, persistent
  prefs + declarative `[[cli.layers]]` config (ADR 0022), modular package

## 0.2.x - polish

- `MountLayer`: unix-style multi-container compositor (designed, see
  deferred-decisions.md)
- [x] CLI declarative layer stack: `storix.toml` / `[tool.storix.cli]`
  (ruff-style precedence) with an ordered `[[layers]]` DSL; backend
  config stays shared, layer stack is CLI-scoped (ADR 0015; landed
  in 0.4.3, ADR 0022)
- CLI cache store selection: swap the in-memory default for a persistent
  store via the `[[layers]]` `store=` (a cashews URL, or a new built-in
  disk-backed `CacheStore`). Lets one-shot `sx --cache` benefit across
  invocations; needs a cross-process staleness default (TTL/validation),
  since separate processes sharing a store reopen the single-writer
  assumption (ADR 0014/0015)
- `AzureBlobBackend.url` with an account key. Today the backend derives
  `presigned_urls` from opendal's `presign_read`, which azblob reports
  False for an account key and True only for a SAS token - so the *same*
  credential mints a URL on `AzureBackend` (ADLS, which signs locally via
  `generate_file_sas`) and raises `UnsupportedOperationError` on Blob.
  Same account, same key, different answer: storix's inconsistency, not
  Azure's. Fix: override `make_url` with `generate_blob_sas` (local HMAC,
  no request, mirrors the ADLS sibling) and advertise the capability when
  the credential can sign, keeping opendal's presign for SAS-token
  credentials. `azure-storage-blob` already ships under `storix[azure]`
  (transitively via the datalake SDK), so only the lean `storix[azblob]`
  (opendal-only) install would keep today's behavior - which makes the
  capability dynamic per install, the part that needs a design pass.
  Workaround now: `[[cli.layers]] name = "url"` (data: URLs), or
  `sx url --data`
- Range reads: `read_stream(start=, length=)` port extension ->
  `fs.stream`/`head`/`tail`; needed for video seeking / HTTP Range
- [~] Recursive walk on `scandir`: `walk`/`find`/`glob` core methods, and the
  consumers they feed - `sx du` 1:1 with unix (per-directory breakdown, `-s`/
  `-a`/`-d`/`-h`) and eza-style `tree` flavors (`-L` depth, `-l` long with
  size/kind, `--sort`). Dead `src/storix/core/` (Tree/Finder/word_count)
  dropped in favor of it. In progress on `feat/core-find` (ADR 0026)
- `wc` and `|`-pipe composition: dropped for now (ADR 0023/0026 discussion) -
  content `wc` is `len(cat.splitlines())`, listing `wc` is `len(ls())`, and
  pipe composition belongs in the shell (`sx ls | wc`), not the Python API.
  Revisit only on a concrete need; write an ADR then, do not resurrect the
  `__ror__` operator approach without one
- CLI aliases (`l`, `ll`, `lt`, `..`, `...`), configurable in
  `[tool.storix.cli]`; a shell-level expansion before dispatch, plus flavored
  `ls`/`tree` presets, mirroring an eza/zsh alias set (ADR when built)
- Shell input hygiene: discard or correctly buffer type-ahead so a command
  typed while the previous one is still rendering is not echoed into the next
  prompt (a prompt_toolkit paint/typeahead fix)
- `echo(atomic=True)` (write-temp-then-move); `progress=` callbacks
- BackendBase template-method refactor (shared stat-validate prologues)
- docs site decision (zensical?) + honest comparison page

## 0.4.0 - adoption

Multiple ergonomic front-ends over the one core, and breadth of
providers - the two levers that make storix promotable.

- [x] `when_missing` infers its capability from the layer's `provides`,
  dropping the explicit argument and forwarding constructor args - the
  pre-construction twin of `with_layer_missing` (breaking; ADR 0018)
- `storix.pathlike`: pathlib-flavored adapter over the same core
  (the cloudpathlib audience)
- Stateless flat facade (working name `Boring[Storix]` / `storix.flat`):
  drops cwd/session, exposes `read`/`write`/`size`/`read_stream`/
  `write_stream`/`delete`/`exists`/`list` on absolute keys - the
  object-store mental model for users unfamiliar with the unix metaphor.
  A thin front-end over the same engine, not a new one; widens the
  audience without diluting the identity (naming TBD)
- `FsspecBackend` (opendal adapter lands first, in 0.4.2, ADR 0020): the
  second ecosystem adapter, chosen for reach into the data crowd
  (pandas/dask) and the inverse `AbstractFileSystem` lever - one adapter =
  every provider fsspec supports (S3, GCS, SFTP...). storix stays the DX
  layer, like FastAPI over Starlette
- fsspec-compatible *interface* (storix *implementing* `AbstractFileSystem`,
  the inverse of `FsspecBackend`): lets the data ecosystem
  (pandas/pyarrow/polars/dask) read storix paths. Big adoption lever,
  big surface - its own design pass
- URI factory (`get_storage('azure://container/path')`) + entry-point
  plugin discovery

## 0.5.0 - differentiators

- Agent story: capability-stripped sessions (a sandboxed session whose
  backend handle cannot unmask paths), possible MCP server, and the audit
  increment of the `ObservabilityLayer` (op-start/end/error events; the
  transfer-event v0 shipped in 0.2.3, ADR 0019)
- Staged-write transactions (`with fs.transaction():` - all-or-nothing
  for new writes, honestly scoped)

## Likely never (recorded so it stops resurfacing)

- Connection pooling as a storix feature: the SDKs already pool
  (aiohttp sessions); measure before building
- Competing with fsspec/opendal on backend count or raw throughput

(Release process and versioning policy live in AGENTS.md "Releasing"
and ADR 0021, not here - the roadmap is plans only.)
