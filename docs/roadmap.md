# Roadmap

What Storix is working toward, organized by the workflows it improves.

Items are grouped by status. Community feedback influences priorities - if
your workflow needs something listed here (or something missing), start a
[workflow discussion](https://github.com/mghalix/storix/discussions).

No dates are promised. Items move between groups as design work progresses
and real-world usage clarifies priorities.

---

## Current maintainer priorities

Community needs can change the order. When community feedback does not identify
a more important workflow, default priorities are:

1. Strengthen and document existing streaming workflows.
2. Add compelling, verified end-to-end recipes.
3. Design consistent resilience and retry semantics across providers.
4. Improve documentation discoverability for humans and coding agents.
5. Continue improving provider consistency and DX as real workflows expose gaps.

---

## Available now

These ship in the current release and are covered by the conformance suite.

### Core operations
- Unix-flavored session with `ls`, `cat`, `echo`, `mv`, `cp`, `rm`, `du`,
  `mkdir`, `touch`, `stat`, `cd`, `pwd` across all backends
- Streaming reads (`stream`) and writes (`echo` from any iterable/async
  iterable/file-like/bytes) with bounded memory
- Recursive traversal: `walk`, `find` (filtered), `glob` (pattern matching)
- Path resolution: `resolve` (session path), `locate` (physical URI)
- Presigned URLs via `url()` on capable backends
- Custom metadata on capable backends
- Data URLs on any backend via `DataUrlLayer`
- Storage-root provisioning via the optional `provisioning` capability and
  `fs.provision()` / `sx provision`: creates a missing ADLS filesystem
  idempotently; local/memory report already-present; the opendal backends
  (S3/R2/GCS/Azure Blob) are data-plane only and report it unsupported,
  pointing at provider tooling (ADR 0030)

### Backends
- **Local disk** - anchored at a base directory
- **In-memory** - full reference backend, ideal for tests
- **Azure ADLS Gen2** - HNS accounts, native streaming
- **Azure Blob** - any account kind, via opendal
- **Amazon S3** - also R2, MinIO, and S3-compatible stores
- **Google Cloud Storage** - via opendal
- Custom backends via `StorageBackend` protocol and `register_backend()`

### Layers and composition
- **SandboxLayer** - escape-proof chroot with real-path auditing
  (`to_real`/`to_virtual`)
- **CacheLayer** - read-through cache with per-operation specs, pluggable
  `CacheStore`, evict-on-mutation
- **ObservabilityLayer** - transfer events (bytes read/written) for progress
  bars and metrics (ADR 0019)
- **DataUrlLayer** / **MetadataLayer** - backfill capabilities on any provider
- `with_layer` / `with_layer_missing` / `without_layer` / `uncached`
  composition
- `chroot()` convenience for sandboxed sessions
- `scratch()` for ephemeral workspaces

### Developer experience
- Sync and async APIs generated from a single async source
- Fully typed (`py.typed`), strict BasedPyright and mypy checked
- Typed errors with stdlib dual inheritance (`PathNotFoundError` is also
  `FileNotFoundError`)
- `get_storage()` factory with env-driven configuration
- `temporary()` for disposable sessions in tests and scripts

### CLI (`sx`)
- Interactive shell with path tab-completion
- Upload/download with progress bars via `ObservabilityLayer`
- Nerd Font icons and coreutils-style output
- Declarative layer stack via `storix.toml` / `pyproject.toml`
- `sx provision` to create a missing storage root (ADLS only; unsupported on the
  opendal backends)

---

## Planned

Designed or prototyped, not yet shipped.

### Streaming and transfer reliability
- Range reads: `read_stream(start=, length=)` port extension for `head`/
  `tail`/video seeking
- `echo(atomic=True)` - write-temp-then-move for safe overwrites
- Define consistent resilience semantics across provider-native retries and an
  optional Storix retry layer, including idempotency, cancellation, backoff,
  provider error classification, and observability

### Provider capabilities
- **AzureBlobBackend.url** with account-key signing (local HMAC, no request)
  - currently limited to SAS-token credentials (ADR 0024)
- CLI persistent cache store across invocations

### Cloud workflow ergonomics
- **MountLayer** - unix-style multi-container compositor
- URI factory: `get_storage('azure://container/path')` with entry-point
  plugin discovery

### Framework and tool integrations
- **storix.pathlike** - pathlib-flavored adapter for the cloudpathlib audience
- **Stateless flat facade** - `read`/`write`/`list` on absolute keys for users
  who prefer the object-store mental model over the unix metaphor
- **FsspecBackend** - use any fsspec-supported store as a storix backend
- **fsspec interface** - storix implementing `AbstractFileSystem` so
  pandas/pyarrow/polars can read storix paths

### Documentation for coding agents
- Coding agent documentation (`llms.txt` and `llms-full.txt` generated from public docs)
- Storix Agent Skill covering installation, sync versus async selection, providers, common workflows, public API constraints, and safe extension patterns

---

## Under consideration

Ideas that need a concrete use case or design pass before committing.

### Reliability and resilience
- Resumable uploads for large files
- Progress reporting with total-size awareness
- Multipart upload tuning per provider

### Observability
- Operation-level events (start/end/error) beyond transfer bytes
- Telemetry hooks (OpenTelemetry integration)

### Agent and automation
- Capability-stripped sessions (sandbox without path-unmask escape)
- MCP server for AI agent workflows
- Audit-grade operation logging
- Open Knowledge Format export or bundle for LLM indexing

### Transactions
- Staged-write transactions (`with fs.transaction():` - all-or-nothing for
  new writes, honestly scoped)

### Performance
- Concurrent walk (per-level fan-out for recursive operations)

---

## Likely never

Recorded so these do not resurface without new evidence.

- **Connection pooling as a storix feature** - the underlying SDKs already
  pool (aiohttp sessions, opendal); measure before building
- **Competing with fsspec/opendal on backend count or raw throughput** -
  storix is the ergonomic layer, not the plumbing

---

Release process and versioning policy live in
[AGENTS.md](../AGENTS.md) and
[ADR 0021](adr/0021-versioning-policy.md).
Rationale for individual decisions: [docs/adr/](adr/).
