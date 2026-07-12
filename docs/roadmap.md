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

## 0.2.x - polish

- `MountLayer`: unix-style multi-container compositor (designed, see
  deferred-decisions.md)
- CLI declarative layer stack: `storix.toml` / `[tool.storix.cli]`
  (ruff-style precedence) with an ordered `[[layers]]` DSL; backend
  config stays shared, layer stack is CLI-scoped (ADR 0015)
- CLI cache store selection: swap the in-memory default for a persistent
  store via the `[[layers]]` `store=` (a cashews URL, or a new built-in
  disk-backed `CacheStore`). Lets one-shot `sx --cache` benefit across
  invocations; needs a cross-process staleness default (TTL/validation),
  since separate processes sharing a store reopen the single-writer
  assumption (ADR 0014/0015)
- Range reads: `read_stream(start=, length=)` port extension ->
  `fs.stream`/`head`/`tail`; needed for video seeking / HTTP Range
- `tree`, `find`, `wc` on the new core; `glob`
- `echo(atomic=True)` (write-temp-then-move); `progress=` callbacks
- BackendBase template-method refactor (shared stat-validate prologues)
- docs site decision (zensical?) + honest comparison page

## 0.3.0 - adoption

Multiple ergonomic front-ends over the one core, and breadth of
providers - the two levers that make storix promotable.

- `storix.pathlike`: pathlib-flavored adapter over the same core
  (the cloudpathlib audience)
- Stateless flat facade (working name `Boring[Storix]` / `storix.flat`):
  drops cwd/session, exposes `read`/`write`/`size`/`read_stream`/
  `write_stream`/`delete`/`exists`/`list` on absolute keys - the
  object-store mental model for users unfamiliar with the unix metaphor.
  A thin front-end over the same engine, not a new one; widens the
  audience without diluting the identity (naming TBD)
- `FsspecBackend` / `OpendalBackend`: one adapter each = every provider
  those ecosystems support (S3, GCS, SFTP...) plus their maturity and
  speed - storix stays the DX layer, like FastAPI over Starlette
- fsspec-compatible *interface* (storix *implementing* `AbstractFileSystem`,
  the inverse of `FsspecBackend`): lets the data ecosystem
  (pandas/pyarrow/polars/dask) read storix paths. Big adoption lever,
  big surface - its own design pass
- URI factory (`get_storage('azure://container/path')`) + entry-point
  plugin discovery

## 0.4.0 - differentiators

- Agent story: capability-stripped sessions (a sandboxed session whose
  backend handle cannot unmask paths), audit/ObservabilityLayer,
  possible MCP server
- Staged-write transactions (`with fs.transaction():` - all-or-nothing
  for new writes, honestly scoped)

## Likely never (recorded so it stops resurfacing)

- Connection pooling as a storix feature: the SDKs already pool
  (aiohttp sessions); measure before building
- Competing with fsspec/opendal on backend count or raw throughput

## Release & CI (automation)

CI (`.github/workflows/ci.yml`) runs lint + format + codegen-drift +
tests on 3.12/3.13 for every push to main/dev and every PR.

Releases are automated (`.github/workflows/release.yml`) so the manual
dance is never needed again - the flow mirrors pydantic/FastAPI:

1. bump `version` in pyproject.toml on a branch; PR into `dev`, then `dev` -> `main`;
2. on `main`: `git tag v0.2.0 && git push origin v0.2.0`;
3. the tag fires the workflow: it checks the tag matches the package
   version, `uv build`s, publishes to PyPI via **Trusted Publishing**
   (OIDC - no token stored anywhere), and cuts the GitHub release with
   generated notes.

**One-time setup (do once on pypi.org):** project -> Settings ->
Publishing -> add a *Trusted Publisher*: owner `mghalix`, repo `storix`,
workflow `release.yml`, and set **Environment name** to `pypi` (it
matches `environment: pypi` in the workflow). After that, tagging is
the entire release.

**Manual fallback** (first release, or if CI is down):
`uv build` -> `uv publish` (needs `UV_PUBLISH_TOKEN` / a PyPI token) ->
`git tag v0.2.0 && git push origin v0.2.0` -> `gh release create v0.2.0
--generate-notes`.
