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

## Update (0.2.0): pluggable codec and the locate() primitive

- MetadataLayer takes `serialize`/`deserialize` *callables* (object<->
  bytes), not a shaped Serializer protocol: any codec plugs in
  regardless of method names or str-vs-bytes convention (orjson.dumps,
  a custom .dumpb, ...). A protocol was rejected because it forced one
  method-name/return-type contract that real serializers (e.g. one whose
  `dumps` returns str with `dumpb` for bytes) do not share. The params
  are named serialize/deserialize, not dumps/loads, so the names do not
  invite `json.dumps` (which returns str, not the required bytes).
- `fs.locate(path)` returns a fully-qualified physical URI (file://,
  abfss://; opaque storix:// default) - the EXTERNAL reference primitive
  (audit logs, Storage Explorer, dedup keys), resolved through any
  sandbox to the real path. It is deliberately NOT navigable: `resolve()`
  is the in-program bookmark (a port path that round-trips through cd);
  parsing a locator back into a session is the URI factory (0.3.0). The
  in-program save/reopen pattern is (provider, config, resolve()) which
  the caller owns.