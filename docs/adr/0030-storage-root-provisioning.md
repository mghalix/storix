# 30. Storage-root provisioning (provisioning capability, sx provision)

Status: accepted

## Context

ADR 0029 gave a missing storage root a concise diagnostic
(`StorageRootNotFoundError`: the configured S3/R2/GCS bucket, Azure Blob
container, or ADLS Gen2 filesystem does not exist) and deliberately left
*creating* the root out, pointing the user at provider tooling. It also
recorded the agreed future shape in `docs/design/deferred-decisions.md`:
a separate, optional control-plane protocol beside the port, surfaced as
an explicit, idempotent `sx provision`, with absence of the protocol as
the unsupported path.

This ADR promotes that deferred decision into a concrete, shipped design
and supersedes the deferred-decisions note.

Creating a storage root is a **control-plane** operation, categorically
different from the data-plane operations `StorageBackend` exposes:

- Credentials that grant object read/write frequently cannot create a
  bucket or container.
- Creation options differ per provider (region, storage tier, HNS).
- A session must never silently create a misspelled root, so provisioning
  must be explicit and never implicit at session start.
- `mkdir` operates inside an existing root and must never be overloaded to
  mean "create the bucket."

### The decisive technical finding

The design turns on what each backend engine can actually do, verified
empirically (opendal 0.47, azure-storage-file-datalake):

| backend | engine | can create its root? | how |
|---------|--------|----------------------|-----|
| LocalBackend | os | yes (already does) | base dir created in `__init__` |
| MemoryBackend | dict | n/a (always present) | no-op |
| AzureBackend (ADLS Gen2) | native azure SDK | **yes** | `FileSystemClient.create_file_system()` / `.exists()` |
| AzureBlobBackend | opendal azblob | **no** | opendal is data-plane only |
| S3Backend (S3/R2/MinIO) | opendal s3 | **no** | opendal is data-plane only |
| GcsBackend | opendal gcs | **no** | opendal is data-plane only |

opendal's `Operator` API is entirely data-plane (`stat`, `read`, `write`,
`list`, `create_dir`, `delete`, `presign_*`, `exists`) - there is no
create-bucket / create-container operation. `create_dir` makes a directory
*marker inside* the bucket, not the bucket itself.

The honest consequence, stated plainly: **the motivating case for this
work (a missing R2/S3 bucket) is exactly the case storix cannot
provision.** The only way to give S3/GCS/azblob real root creation would be
to add provider control-plane SDKs (boto3, google-cloud-storage, the Azure
management plane) as dependencies. storix does not do that - it is the
ergonomic layer over opendal, not a re-implementation of provider admin
tooling (roadmap "likely never: competing with fsspec/opendal on backend
breadth"). So `sx provision` delivers a real cloud capability only for
ADLS; for the opendal backends it gives a clear, actionable unsupported
message rather than a false promise.

This is a smaller win than the command name suggests. It is recorded here
so the maintainer can weigh the ADLS-only value against the added surface
before merging, rather than discovering the limitation after.

## Decision

Ship a small, honest control-plane surface: an optional protocol capable
backends implement, one core method that gates it, and one CLI command.

### A. `provision()` on the port, gated by a `provisioning` capability

Provisioning follows the exact idiom the codebase already uses for every
optional backend feature (ADR 0027's `bulk_listing`, the earlier
`content_type` / `custom_metadata` / `presigned_urls`): a capability flag
plus a port method with a raising default on `BackendBase`.

- New `provisioning: bool = False` field on `Capabilities` and a matching
  `Capability.PROVISIONING` member (the alignment test keeps the two in
  lockstep, as for every other capability).
- `async def provision(self) -> bool` on the `StorageBackend` port
  (generated async -> sync), with a `BackendBase` default that
  `raise UnsupportedOperationError(Capability.PROVISIONING)` - identical to
  how `list_tree` defaults for non-`bulk_listing` backends. Capable
  backends override it and set the flag; the rest inherit the raising
  default and never advertise it.

This was chosen over a separate `StorageProvisioner` `Protocol` +
`isinstance` gate (the shape sketched in deferred-decisions). A bespoke
protocol would reinvent a gate the codebase already has one blessed,
tested idiom for; capabilities are equally additive and non-breaking (every
field defaults False), they are *discoverable* (`backend.capabilities.
provisioning`, which `sx` and library callers can check before calling),
and they keep provisioning consistent with every other optional feature.
The one cost - a control-plane method now sits on the data-plane port - is
mild: the port already carries non-data-plane members (`locate`,
`capabilities`), and `BackendBase`'s default keeps it a no-op for the
backends and custom subclasses that cannot provision.

- One method, idempotent, returning "did I create it". No separate
  `exists()`: `provision` subsumes the check, and a pure existence probe
  is already answerable at the data plane (ADR 0029's missing-root
  detection). No `deprovision`/delete: destroying a root is not a
  workflow storix needs to own (YAGNI - revisit only with a concrete
  ephemeral-root use case, and only behind explicit confirmation).

Implementers (this PR) advertise `provisioning=True`:

- **AzureBackend (ADLS)**: attempts `create_file_system()` on the native
  SDK client it already holds, catching `ResourceExistsError` as
  already-present (race-safe). The one real cloud provisioner.
- **LocalBackend**: the base directory is created in the constructor, so
  `provision()` is idempotent and returns False (already present). Honest:
  a local root is provisioned at construction.
- **MemoryBackend**: always present; `provision()` is a no-op returning
  False.

Non-advertisers: **S3Backend, GcsBackend, AzureBlobBackend** (opendal,
data-plane only) and any custom backend. `provisioning` stays False, so the
core gate raises for them.

### B. `Storix.provision()` - the single gate

The core session owns the one place that answers "can this backend
provision, and if not, what do I say":

```python
async def provision(self) -> bool:
    base = self.base_backend
    if not base.capabilities.supports(Capability.PROVISIONING):
        raise UnsupportedOperationError(
            Capability.PROVISIONING,
            f'{type(base).__name__} cannot create its storage root from '
            'storix (creating a bucket or container is a provider '
            'control-plane operation); create it with your provider tooling '
            '(aws s3 mb / az storage container create / gcloud storage '
            'buckets create), then retry',
        )
    return await base.provision()
```

- Reuses `UnsupportedOperationError` from the ADR 0004 taxonomy rather than
  minting a new error class: nothing went wrong with a path, the backend
  simply cannot do what was asked - exactly that error's meaning. The
  custom message keeps the actionable provider-tooling pointer over the
  generic default.
- Gates on the *base* backend's capability, beneath any layers. A sandbox
  jails *paths*, not the root's existence; creating the container the jail
  lives in is not
  a sandbox escape (it grants no data access outside the jail), and it is
  the correct target. Provisioning is why a driving adapter reaches for the
  core, not `base_backend` directly - the "is it supported, else what"
  logic lives here once (the core-boundary rule from AGENTS.md), so the
  CLI, a future MCP server, and library users share it.

### C. `sx provision`

```bash
sx -p azure provision
```

- Capable + created: `provisioned <root uri>` (via `fs.locate('/')`, which
  already names the container/bucket), exit 0.
- Capable + already present: `already present: <root uri>`, exit 0
  (idempotent).
- Not capable (opendal or custom): the `UnsupportedOperationError` message
  through the CLI's normal `_die` boundary, exit 1.

`sx mkdir` is untouched and never creates a root; the docs say so
explicitly next to `provision`.

**No `--if-missing` flag.** `provision` is idempotent by default (its job
is "make sure the root is there," the useful default for scripts and CI),
so a flag distinguishing "create, error if present" from "ensure present"
buys nothing - the same reasoning ADR 0012 used to reject `exist_ok` on
`mkdir`. Add a flag only if a concrete need for the strict mode appears.

### D. Deliberately excluded

- No provider control-plane SDKs (boto3, google-cloud-storage, Azure mgmt)
  and therefore no S3/R2/GCS/azblob root creation.
- No implicit provisioning at session build (no factory / `storix.toml` /
  env `create_if_missing`); `sx provision` and `fs.provision()` are the only
  triggers. A silent create-on-connect would turn a typo'd bucket name into
  a new empty bucket that hides the real data - the exact footgun.
- No deprovision/delete-root; no `--if-missing`.

## Consequences

`sx -p azure provision` creates a missing ADLS filesystem idempotently and
names it; local/memory report already-present; S3/R2/GCS/azblob and custom
backends get a clear, actionable unsupported message instead of a silent
failure or a false success. Library users and future front-ends call
`fs.provision()` and get the same gate. The `provisioning` capability is the
extension point: if a control-plane path for the opendal backends ever lands
(an opendal admin API, or a user opting into a heavy extra), that backend
advertises the capability and overrides `provision()`, and both
`fs.provision()` and `sx provision` cover it with no surface change.

The acknowledged limitation is that the headline cloud case (S3/R2) is
unsupported; this ADR chooses an honest narrow capability over adding
provider admin SDKs to storix.

Compatibility (ADR 0021): purely additive - a new `provisioning` capability
(field + enum member), a `provision()` port method with a raising
`BackendBase` default, a new core method and CLI command, and `provision`
overrides on three backends. Existing custom backends subclassing
`BackendBase` inherit the default and keep working. No existing behavior
changes. Backward-compatible feature -> PATCH bump.

Supersedes the "Storage-root provisioning" entry in
`docs/design/deferred-decisions.md`.
