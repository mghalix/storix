# 20. External backend adapter: opendal first, fsspec second

Status: accepted (opendal-first; the conformance spike is the acceptance gate)

## Context
storix wins on DX, not backend count (roadmap "likely never: competing with
fsspec/opendal on backend count"). But "doesn't support my stack" bounces a
reader before DX ever gets a chance. The leverage is not one native backend per
provider; it is one adapter over an existing ecosystem. Candidates: cloudpathlib,
fsspec, opendal.

## Decision
Reject cloudpathlib as a backend: it is a *peer* DX layer (pathlib-over-cloud),
client-side, three providers. It is a competitor to study and the audience for
`storix.pathlike`, not a plumbing source.

Adopt **opendal first**, validated by a conformance spike; **fsspec second**.
Criteria, storix-specific, and how each scores:

1. Async-native (storix is async-first, the whole codegen premise). opendal:
   native `AsyncOperator`. fsspec: uneven - `AsyncFileSystem` exists but many
   implementations are sync-only, so an async-first core pays a threadpool tax.
2. Presign as a first-class op (storix has a `make_url` capability). opendal:
   native `presign`. fsspec: `sign()` only on some backends, so `make_url` would
   be spotty.
3. Port fit / adapter size. opendal's operator API maps ~1:1 to the port; both
   are small because `backends/generic.py` already supplies
   copy/copy_tree/delete_tree/du/exists/read/write over the primitives.
4. Ecosystem gravity + the inverse `AbstractFileSystem` lever. fsspec wins
   decisively (pandas/dask/pyarrow install base; the same library as storix
   *implementing* `AbstractFileSystem`). This is why fsspec is second, not
   dropped.
5. Dependency weight. fsspec lighter and granular (per-backend extras); opendal
   one compiled wheel covering ~50 services.

opendal wins 1-3 (architectural fit); fsspec wins 4-5 (ecosystem). Lead with fit,
follow with ecosystem.

The spike is the acceptance gate, not a separate decision: implement
`OpendalBackend` for `memory` + `s3`, run the existing parametrized conformance
suite, and record two numbers - adapter LOC and methods written vs inherited from
`generic`. Pass (~100-150 lines, conformance green) proves "backends are cheap";
failure (fighting the port) flips the lead to fsspec or triggers a port review,
for a day's work instead of a month's bet.

Primitive surface an adapter implements: `read_stream`, `write_stream`,
`delete`, `list_dir`, `stat`, `make_dir`, `locate`, `close` (~8), plus
capability-gated `make_url` (opendal `presign`) and `set_metadata`. The rest
inherit from `generic`.

Rejected: cloudpathlib-as-backend (above); adopting both adapters at once (ship
one, prove the pattern, add fsspec deliberately for the data-ecosystem audience
and the inverse lever).

## Consequences
One adapter unlocks S3/GCS/Azblob/... so "fits my stack" stops bouncing readers,
and storix stays the DX layer over mature plumbing (FastAPI-over-Starlette).
Cost: opendal is a compiled dependency and newer in Python; gate it behind a
`storix[opendal]` extra with the clear missing-extra error (board item). The
fsspec adapter and the inverse `AbstractFileSystem` implementation stay
roadmapped.

Implementation (HAND-WRITTEN twin like `azure.py`/`local.py`, NOT codegen -
opendal's async/sync primitives differ per flavor; write both `_async` and
`_sync`):

- [x] Spike first: `src/storix/_async/backends/opendal.py` `OpendalBackend` over
      `opendal.AsyncOperator`; wire `memory` + `s3`; run the conformance suite;
      record the two numbers. Only proceed past the spike if it passes.
      Spike result (opendal 0.47, conformance green on `memory` and `s3`/minio
      in both flavors): ~260 code lines per twin (~130 excluding the error
      translation and the object-store directory-marker handling); 9 port
      methods written (`stat`, `read_stream`, `write_stream`, `delete`,
      `list_dir`, `make_dir`, `locate`, `set_metadata`, `make_url`) vs 8
      inherited from `generic` (`read`, `write`, `move`, `copy`, `delete_tree`,
      `du`, `exists`, `close`).
- [x] Capabilities: advertise `presigned_urls` (opendal `presign`) where the
      service supports it; gate `make_url` on it. Metadata where available.
- [x] Factory: register `opendal` service resolvers; lazy import guarded to
      raise the typed missing-extra error (`storix[opendal]`).
- [x] `pyproject.toml`: `storix[opendal]` optional-dependency group.
      (Superseded by the amendment below: the extras are provider-named.)
- [x] Write the `_sync` twin by hand (`opendal.Operator`); do NOT run the async
      tree through `unasync`. `just check`.

Amendment (2026-07-16, post-review): the adapter is an INTERNAL engine, not
the public surface. Users see typed per-provider facades - `S3Backend`,
`GcsBackend` - that subclass the engine with explicit, documented
constructors, Azure-grade env config (`STORIX_S3_*`, `STORIX_GCS_*`), and
provider-named extras (`storix[s3]`, `storix[gcs]`). opendal and its
service/option vocabulary never appear in the public API or docs. The facades
are flavor-neutral (an `__init__` and a `locate` override), so they run
through `unasync`; only the engine twins are hand-written. A new service is a
facade plus a config class (~50 lines), added on demand.

0.4.2 (backward-compatible feature -> patch; opendal is not in the
published 0.4.0).
