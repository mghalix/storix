# 24. AzureBlobBackend.url() with an account key: 1:1 with ADLS

Status: accepted

## Context

storix's Azure convenience is that the account kind does not matter: the
`azure` provider detects hierarchical namespaces and builds `AzureBackend`
(ADLS Gen2) or `AzureBlobBackend` (flat blob), and the user writes the same
code either way. One operation breaks that promise.

`AzureBackend.url()` mints a read SAS from an account key with
`generate_file_sas` - local HMAC crypto, no request. `AzureBlobBackend`
inherits `make_url` from `OpendalBackend`, which gates on opendal's
`presign_read` capability. opendal reports that capability as `False` for an
account-key credential and `True` only for a SAS-token credential (verified:
with an account key `op.capability().presign_read is False`; opendal's blob
"presign" is really just appending a SAS token you already hold). So:

```
same account, same account key:
  AzureBackend.url()      -> a working SAS URL
  AzureBlobBackend.url()  -> UnsupportedOperationError('presigned_urls')
```

That is storix's inconsistency, not Azure's - the blob SDK signs an account key
locally exactly as the datalake SDK does. There is no opendal knob to fix it;
opendal simply does not do account-key SAS minting for blob.

## Decision

Override `make_url` in `AzureBlobBackend` to mint a blob SAS locally with
`azure.storage.blob.generate_blob_sas` (pure HMAC, no request), mirroring
`AzureBackend`'s `generate_file_sas` path, and advertise `presigned_urls`
whenever the credential can actually sign.

- **Signing.** When the credential is an account key, `make_url` builds the SAS
  with `generate_blob_sas(account_name, container_name, blob_name, account_key,
  permission=BlobSasPermissions(read=True), expiry=now+expires_in)` and returns
  `{endpoint}/{container}/{root+path}?{sas}`. It uses the configured `endpoint`
  (not a hardcoded `blob.core.windows.net`) so Azurite and sovereign clouds
  work, and honors `root`. A directory raises `IsADirectoryError`, like ADLS.
- **SAS-token credential.** Falls through to `super().make_url()` (opendal's
  presign already works there).
- **Capability.** `presigned_urls` is advertised when opendal reports it
  (SAS-token creds) OR the blob SDK is importable and the credential is an
  account key. Honest per credential and per install.
- **Packaging.** Add `azure-storage-blob` to the `azblob` extra. It already
  ships transitively on `storix[azure]` (via `azure-storage-file-datalake`),
  but the lean `azblob` (opendal-only) install lacked it, which would make the
  capability silently install-dependent. Adding it makes `url()` work with an
  account key on *any* Azure account kind, on *any* Azure install - the 1:1
  promise, honored. The cost is one dependency on the lean profile, accepted
  deliberately: 1:1 behavior is the product value, and the blob SDK is lighter
  than the datalake SDK the full extra already pulls.

`make_url` lives in `_async/backends/azblob.py` (codegen source; `azblob.py` is
generated, unlike the hand-written `azure.py`). `generate_blob_sas` is a pure
function, identical in both flavors, so the override transliterates cleanly.

Rejected: leaving it a runtime `UnsupportedOperationError` and documenting "use
a SAS token for blob url()" - it breaks the account-kind-agnostic promise that
is the whole point of the `azure` provider. Rejected: a user-facing
config reshape - the fix is internal; the user's credential does not change.

## Consequences

`sx url` and `fs.url()` work on a flat blob account with an account key,
matching ADLS behavior, so "same code regardless of account kind" holds for
URLs too. The `presigned_urls` capability is now credential- and
install-accurate rather than always-false on blob. Cost: `azblob` carries
`azure-storage-blob`, and there are two SAS code paths in the Azure family
(datalake and blob) that must stay in step - acceptable, they are small and
each mirrors its SDK. A unit test signs with a throwaway key offline (SAS
generation is local), so coverage needs no live account.

0.4.5 (backward-compatible feature -> patch; ADR 0021). Ships after 0.4.4
(scandir); independent of it.
