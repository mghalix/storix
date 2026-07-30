# 33. Conditional writes for safe concurrent updates

Status: accepted

## Context

Every write storix performs is last-write-wins. `write` and `write_stream`
send bytes and the store keeps whatever arrived last, so two writers holding
the same path silently destroy one another's work with no error on either
side. Nothing in the port can express "write this only if the object is still
what I read".

`sx edit` makes the gap concrete. It downloads a file, opens `$EDITOR`, and
uploads the buffer on save. Between the download and the upload sits however
long a person spends editing, and a second writer inside that window is
overwritten without trace. Read-modify-write over stored metadata has the same
shape, and the port documents the hazard rather than solving it: metadata
semantics are replace, and "merge is the caller's job: stat, merge, write".

Local file locking does not address this. `flock` and `fcntl` coordinate
processes through one kernel, and an editor's `.swp` sentinel is a file beside
the original on one machine. Two people editing the same blob from two laptops
share no kernel and never see each other's locks. The contention is remote, so
the arbitration has to be remote.

Every store storix targets already offers the primitive, because HTTP does.
A read returns an opaque validator for the object's current state, and a write
carries a precondition naming the validator it expects:

| store          | validator                    | write precondition                    |
| -------------- | ---------------------------- | ------------------------------------- |
| Azure Blob     | `ETag`                       | `If-Match`, `If-None-Match`           |
| Azure ADLS     | `ETag`                       | `If-Match`, `If-None-Match`           |
| Amazon S3      | `ETag`                       | `If-Match` on PUT, `If-None-Match: *` |
| GCS            | generation                   | `ifGenerationMatch`                   |
| local disk     | none the kernel arbitrates   | `O_EXCL` for create-only              |

The service compares and writes as one operation, so there is no window
between the check and the write. This is optimistic concurrency control, the
same mechanism Cosmos DB exposes as `_etag` plus `If-Match`, and the same one
`compare_and_swap` names in hardware.

## Decision

Add conditional writes to the port as an opt-in precondition, gated by a
capability, reported by a typed error.

### D1. `RawStat` carries an opaque `version`

`RawStat` gains `version: str | None = None`, the validator the backend read
from the same response that produced the rest of the stat. It is opaque: a
token to hand back, never to parse, compare for ordering, or construct. GCS
generations are integers and ETags are quoted strings; storix stringifies both
and interprets neither.

This costs nothing. Backends already parse a stat or properties response, and
the validator arrives in that same response. No backend issues an extra
request to populate it.

Backends that have no validator leave it `None`. A new optional field with a
default keeps every existing backend and every third-party backend valid.

### D2. Writes accept `if_match`, and a create-only sentinel

`write` and `write_stream` accept `if_match: str | None = None`:

- `None` (the default) writes unconditionally, exactly as today.
- a version string writes only if the stored object still carries it.
- `IF_MATCH_ABSENT`, a module-level sentinel, writes only if the path does
  not exist, mapping to `If-None-Match: *` and to `O_EXCL` on local disk.

The default preserves today's behavior on every path, so no existing caller
changes and no existing write pays for the feature.

`mode='a'` rejects `if_match`. An append is defined by the store's own
concatenation semantics and there is no validator for "the file as it will be
after other appends"; a precondition there would read as a guarantee storix
cannot make.

### D3. Two capabilities, and no emulation

`Capabilities` gains **two** flags, because the two forms are two separate
guarantees and a store can offer either without the other:

- `conditional_writes` - can compare a stored version (`If-Match`)
- `exclusive_create` - can refuse an occupied path (`If-None-Match: *`,
  `O_EXCL`)

One flag covering both would tell a caller yes and then have the write reject
it. This is not hypothetical: local disk creates exclusively and cannot compare
a version, and opendal reports `write_with_if_match` and
`write_with_if_not_exists` separately per service, so an S3-compatible endpoint
can genuinely support one and not the other. It is also the case the naming
rule in AGENTS.md is about: a boolean is only for a genuinely two-valued fact.

Passing a form the backend does not advertise raises
`UnsupportedOperationError` naming the missing capability, the established
behavior for a user-facing optional feature.

`BackendBase` deliberately does **not** emulate it. The available emulation is
to stat, compare the validator, and write if it matched, which reintroduces
precisely the window the feature exists to close: two writers can both observe
a match and both write. An emulation that turns a real guarantee into a
narrower race, while advertising the capability that says the guarantee holds,
is worse than the absent capability. This is the opposite call from
`ranged_reads` and `bulk_listing`, and for a different reason: those are speed
gates whose fallback is slower but equally correct, while this one's fallback
is silently unsafe.

A backend therefore advertises a capability only when the service it speaks to
performs the comparison and the write as one operation.

### D4. `PreconditionFailedError`

A failed precondition is a new member of `storix.errors`, raised when the store
rejects the write:

```python
class PreconditionFailedError(StorageError):
    """A conditional write lost: the stored object changed underneath it."""
```

It is not `FileExistsError` and not a generic `StorageError`, because the whole
value of the feature is a caller distinguishing "someone else changed this"
from "the write failed" and retrying its read-modify-write loop. Backends
translate their native form (HTTP 412, `ConditionNotMet`, `FileExistsError`
from `O_EXCL`) into it.

### D5. The core exposes it, and stays out of the retry business

`Storix.echo` and the write paths grow the same `if_match` keyword and pass it
through. The core does not retry, does not loop, and does not merge: what to do
when a precondition fails is the caller's decision, and a core that guessed
would be choosing for a `sx edit` that should ask a person and a metadata merge
that should recompute. The read-modify-write loop belongs to whoever owns the
data.

### D6. Per-backend support

| backend                    | `conditional_writes` | `exclusive_create` |
| -------------------------- | -------------------- | ------------------ |
| `MemoryBackend`            | yes                  | yes                |
| `LocalBackend`             | no (POSIX has no CAS)| yes (`O_EXCL`)     |
| `S3Backend`, `GcsBackend`, `AzureBlobBackend` | from the service | from the service |
| `AzureBackend` (ADLS)      | yes (`If-Match`)     | yes (`If-None-Match: *`) |

The opendal-backed backends do not hardcode either flag. They read
`capability().write_with_if_match` and `write_with_if_not_exists` from the
operator, so the answer reflects the endpoint actually configured rather than
an assumption about the provider. `MemoryBackend` keys its validator off a
per-node revision counter rather than a timestamp, so two writes in the same
clock tick still produce different versions.

`AzureBackend` (ADLS Gen2, the native SDK) writes a file as create, append,
flush, and carries the precondition on the **create** (`PUT ?resource=file`),
not on the flush. The create is the request that truncates an occupied path,
so it is the only one where the comparison and the destructive write are the
same service operation: a condition on the flush would arbitrate after the
previous content was already gone, and against an ETag the create had just
replaced. The SDK expresses both forms as `match_condition` plus `etag`
(`MatchConditions.IfNotModified` emits `If-Match`,
`MatchConditions.IfMissing` emits `If-None-Match: *`), and reports a refusal
as `ResourceModifiedError` or `ResourceExistsError`, which the backend
translates to `PreconditionFailedError` only when it actually sent a
condition. `RawStat.version` is the ETag already present on the properties
response `stat` parses.

## Performance

The feature is free when unused and cheap when used:

- `version` rides along in a response already being parsed. No new request.
- A precondition is a request header. No new request, no extra round trip.
  Verified against opendal 0.47: both `write` and `open` accept the
  precondition arguments, so the streaming write path stays streaming and
  nothing has to be buffered to make a write conditional.
- `if_match=None` is the default on every path, so existing writes are
  byte-for-byte the same requests they are today.
- Nothing is added to the read path, the listing path, or the transfer path.

The one cost is a failed precondition, which is a rejected write the caller
must handle, and that cost is the point: it replaces a silent overwrite.

## Consequences

`sx edit` can detect a concurrent change and refuse rather than clobber,
on the backends whose stores support it. Read-modify-write over metadata
becomes expressible. `MemoryBackend` gains it too, which makes concurrency
behavior testable offline instead of only against a real account.

Not every backend answers: on local disk, and on any third-party backend that
has not opted in, requesting a precondition raises rather than pretending. A
CLI built on this has to present two paths, which is honest about what the
underlying store guarantees.

The validator is opaque, so storix cannot offer "has this changed since?"
without a stored token to compare, and cannot order two versions. Callers that
want change detection keep the `version` they read.
