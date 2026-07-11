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

## 0.2.x - polish

- `MountLayer`: unix-style multi-container compositor (designed, see
  deferred-decisions.md)
- Range reads: `read_stream(start=, length=)` port extension ->
  `fs.stream`/`head`/`tail`; needed for video seeking / HTTP Range
- `tree`, `find`, `wc` on the new core; `glob`
- `echo(atomic=True)` (write-temp-then-move); `progress=` callbacks
- BackendBase template-method refactor (shared stat-validate prologues)
- docs site decision (zensical?) + honest comparison page

## 0.3.0 - adoption

- `storix.pathlike`: pathlib-flavored adapter over the same core
  (the cloudpathlib audience)
- `FsspecBackend` / `OpendalBackend`: one adapter each = every provider
  those ecosystems support (S3, GCS, SFTP...) plus their maturity and
  speed - storix stays the DX layer, like FastAPI over Starlette
- URI factory (`get_storage('azure://container/path')`) + entry-point
  plugin discovery

## 0.4.0 - differentiators

- Agent story: capability-stripped sessions (a sandboxed session whose
  backend handle cannot unmask paths), audit/ObservabilityLayer,
  possible MCP server
- `CacheLayer`
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
workflow `release.yml`. After that, tagging is the entire release.

**Manual fallback** (first release, or if CI is down):
`uv build` -> `uv publish` (needs `UV_PUBLISH_TOKEN` / a PyPI token) ->
`git tag v0.2.0 && git push origin v0.2.0` -> `gh release create v0.2.0
--generate-notes`.
