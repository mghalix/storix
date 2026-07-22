# 29. sx transfer setup and storage-root diagnostics

Status: accepted

## Context

A real workflow (pushing a demo video to a Cloudflare R2 bucket) exposed
three gaps at once:

1. The configured bucket did not exist, and `sx -p s3 ls` printed opendal's
   entire debug dump - `ConfigInvalid (permanent) at list => S3Error {
   code: "NoSuchBucket", ... }` plus the request URI and response headers -
   instead of a one-line storix error.
2. `sx -p s3 push ./video.mp4 /storix/video.mp4` failed with
   `push: path '/storix' does not exist`: single-file push resolves the
   destination and calls `echo()`, whose contract deliberately requires the
   parent to exist. Directory push already creates every destination
   directory, so the two arms of the same command disagreed.
3. The user then tried `sx -p s3 mkdir storix && push ...`, which tangles
   four distinct things that this ADR keeps separate.

The four concepts:

- **Paths inside the storage root** - files and directories in the session
  namespace. This is what `mkdir`, `echo`, `push` operate on.
- **The storage root itself** - the S3/R2/GCS bucket, Azure Blob container,
  ADLS Gen2 filesystem, or local base directory the backend is anchored to.
  Creating one is a control-plane operation against the provider, not a
  filesystem operation; storix assumes the root exists (the local backend
  creates its base directory in its constructor, so only remote roots can
  be missing).
- **Host-shell composition** - `&&`, `;`, pipes. The host shell owns these;
  each `sx` invocation is one command.
- **The interactive `sx` command language** - one command per prompt line,
  sequenced by the user, sharing one live session.

Verified provider signals for a missing root (live, against real accounts):

| provider | raw failure | structured signal |
|----------|-------------|-------------------|
| s3 / R2 (opendal) | `ConfigInvalid` on every op | none; message embeds `code: "NoSuchBucket"` |
| azblob (opendal) | `NotFound` -> misleading `path '/' does not exist` | none; message embeds `code: "ContainerNotFound"` |
| azure ADLS (native) | `path '/' does not exist` | `HttpResponseError.error_code == 'FilesystemNotFound'` |
| gcs (opendal) | unverified (no credentials available) | unknown |

opendal's Python exceptions carry no attributes beyond the message string,
so for opendal services the only available signal is the provider error
*code* embedded verbatim in that message.

## Decision

### A. `sx push` creates missing destination parents

Single-file `sx push` creates the destination's missing parent directories
inside the storage root before transferring, exactly as directory push
already does: one `fs.mkdir(dst.parent, parents=True)` before the
transfer. Directory push loses its `suppress(StorageError)` around the
batched mkdir - `parents=True` already makes an existing directory a
silent success, so the suppression only hid real failures (permission
denied, an intermediate file, the missing bucket itself). mkdir failures
in both arms now propagate to the command's normal error exit.

- The convenience lives in the `sx push` driving adapter. `Storix.echo()`
  keeps its strict parent-must-exist contract; no `parents=` flag grows on
  it (ADR 0013: combinators over flags) and no core change is needed -
  push *composes* two existing core operations (`mkdir` + `echo`), the
  same composition directory push already performs, so no core semantics
  are duplicated in the interface.
- No `--parents` flag on `push`. push is a high-level transfer verb
  (scp/rsync-shaped, not cp-shaped); scaffolding the destination is the
  expected default, and the previous behavior was an error, so nothing
  can depend on its absence.

Behavior across the cases:

- missing parent, or several missing levels: created (`parents=True`)
- existing parent, or destination omitted (parent is the cwd), or root
  destination (parent is `/`): silent success, same call
- intermediate path component is a file: the mkdir -p contract's error
  names it - `AlreadyExistsError` when the file is the immediate parent
  (unix `mkdir -p a` on a file: File exists), `NotADirectoryError` when
  it sits deeper in the chain; exit 1 either way
- permission denied or any other backend failure during mkdir: propagates;
  exit 1 (no longer suppressed)
- object stores: real directory markers via the existing `make_dir`
  contract (implicit-prefix evaporation is already handled there)
- existing destination file: overwritten, as before (`echo` mode 'w')
- content-type detection and transfer progress: unchanged

Out of scope, unchanged: `push ./f /existing-dir` still fails with
`IsADirectoryError` rather than copying *into* the directory; a future
ergonomic pass may add cp-into-directory semantics.

### B. `StorageRootNotFoundError` and a debug escape hatch

New typed error in `storix.errors`:

```python
class StorageRootNotFoundError(ConfigurationError):
    root: str        # the configured root's name, e.g. 'media'
    root_kind: str   # short descriptive phrase, e.g. 's3 bucket'
```

Message template: `configured {root_kind} '{root}' does not exist`. It is
a `ConfigurationError` because that class already owns "a lazily checked
setting only the provider can validate on first I/O" - a configured bucket
name is exactly that - so existing `except ConfigurationError` /
`except StorageError` handlers keep working. It is deliberately *not* a
`PathError` and not a `FileNotFoundError`: there is no offending port path
(the namespace itself is absent), and a handler that reacts to a missing
*file* by creating it must not fire for a missing bucket. `root_kind` is
descriptive vocabulary for humans and logs, not a dispatch key - dispatch
on the type.

Translation happens at each backend's existing error boundary:

- **opendal adapter**: a per-service table maps the service to the
  provider's missing-root error code and root vocabulary -
  `s3 -> ('NoSuchBucket', 'bucket')`,
  `azblob -> ('ContainerNotFound', 'container')`. When a caught opendal
  error's message contains the quoted code token (`code: "NoSuchBucket"`),
  the adapter raises `StorageRootNotFoundError` naming the configured
  bucket/container. Matching the quoted form, not the bare word, keeps a
  path that merely echoes the word (the raw message embeds the request
  URI) from ever matching.
  String matching is unavoidable here (opendal exposes no structured
  fields); it is confined to this one table, matches the provider's
  stable API error *code* rather than prose, is unit-tested against the
  exact captured messages, and anything unmatched falls through to the
  existing translation unchanged. gcs is deliberately absent until its
  real missing-bucket message is captured against a live account; a
  missing gcs bucket keeps today's behavior (the generic fallback).
- **native azure (ADLS)**: `error_code == 'FilesystemNotFound'` (a
  structured SDK field) now maps to `StorageRootNotFoundError` instead of
  the misleading `PathNotFoundError: path '/' does not exist`.
- **local / memory**: cannot happen (the constructor creates the base;
  memory always has a root).
- **custom backends**: may raise it themselves; nothing is required of
  them.

The CLI needs no special rendering: `_die` already prints `{cmd}: {exc}`,
which now reads `ls: configured s3 bucket 'media' does not exist`.

`sx --debug` is added as a global flag: when set, the CLI's single error
boundary (`_die`) prints the full exception chain (traceback, causes -
where the raw provider context, request IDs, and HTTP detail live via
`__cause__`) before the one-line summary. It is coherent across every
command because every command already funnels failures through `_die`.
Normal output stays concise; nothing is lost, only relocated.

The non-root `ConfigurationError` fallback (bad region, bad credentials)
keeps its full opendal message in normal mode: there the detail *is* the
diagnosis. Only the missing-root case had a concise, actionable answer
being drowned by it.

### C. Root provisioning: deferred

No `sx provision` in this change, and no provider-administration methods
on `StorageBackend`. Bucket/container creation is a control-plane
operation: credentials that allow object I/O often cannot create buckets,
creation options differ per provider (region, tier, HNS), and a session
must never silently create a misspelled root. `mkdir` never pretends to
create a bucket or container - it operates inside an existing root,
full stop.

The agreed future shape (recorded in
`docs/design/deferred-decisions.md`): a separate, optional control-plane
protocol implemented by capable backends (`exists()` / `create()`),
surfaced as an explicit, idempotent `sx provision [--if-missing]`, with
absence of the protocol as the unsupported path for custom backends.
Reusable by library users and future front-ends because it lives beside
the backend, not in the CLI. Trigger: a second concrete request for
in-tool provisioning, or the agent/MCP story needing programmatic root
setup. Until then the concise error plus the provider's own tooling
(`aws s3 mb`, `az storage container create`, the R2 dashboard) is the
answer, and the docs say so explicitly.

### D. No command chaining in sx

`&&`, `;`, pipelines, redirections, command substitution, and host
command execution are rejected - they belong to the host shell, which
already composes one-shot `sx` invocations, while the interactive shell
already sequences commands over one live session. Reimplementing a
fraction of bash inside sx would be a worse bash. A fail-fast batch
runner (`sx run commands.sx`) is deferred with no committed design:
worth revisiting only if a real workflow shows the host shell plus the
interactive session cannot serve it (for example, paying session/auth
setup once across many commands at scale).

## Consequences

`sx push ./video.mp4 /storix/demos/video.mp4` now works against an
existing bucket with no prior `mkdir`, file and directory push agree,
and mkdir failures during push surface instead of being swallowed. A
missing bucket/container/filesystem reads as one actionable line on s3,
R2, azblob, and ADLS; `--debug` recovers the raw provider detail. gcs
missing-bucket detection is an acknowledged gap pending live
verification. Library users gain a typed, provider-neutral
`StorageRootNotFoundError` that existing handlers already catch.

Compatibility (ADR 0021): everything is backward-compatible - a new
error subclass under `ConfigurationError`, a CLI convenience where the
old behavior was an error, and diagnostics refinement. The one nuance:
a missing azblob container / ADLS filesystem previously surfaced as
`PathNotFoundError` (so `except FileNotFoundError` caught it); that was
a misdiagnosis being corrected on a failure path, judged a bug fix, not
a public API break. PATCH bump.
