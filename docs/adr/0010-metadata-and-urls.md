# 10. Metadata and URLs

Status: accepted

## Context
Cloud objects carry content types, custom metadata and presigned URLs;
local disk does not; semantics must be pinned, not accidental.

## Decision
Metadata is *replace*: a provided mapping replaces entirely, `{}`
clears, `None` preserves on append - what Azure natively does; merge
would be racy read-modify-write in every backend. `write(metadata=)`
rides along with creation (single request on the create path);
`set_metadata` (port, files-only) changes metadata without touching
content; `fs.set_metadata(..., merge=True)` does the two-request
stat+set merge at the core, documented as non-atomic. URLs split:
`fs.url()` -> port `make_url` behind `presigned_urls` (Azure SAS,
minted locally from the account key); `fs.data_url()` is core-generic
base64 for any backend. Local gets metadata later via a sidecar
MetadataLayer (deferred-decisions.md).

## Consequences
One semantics for every backend, conformance-tested (including on the
Azure wire); requests are minimal by construction.

## Update (0.2.0): set_metadata clears with {}, never None

`set_metadata(path, metadata)` takes a required `Mapping` - `{}` clears.
`None` is deliberately rejected (it is not in the type): across the API
`None` means *preserve* (write/append leaves metadata untouched), so
letting it also mean *clear* here would give one value two opposite
meanings. `{}` is the single unambiguous clear signal everywhere.
