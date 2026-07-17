# S3, GCS, and Azure

`S3Backend`, `GcsBackend`, and the two Azure backends run the whole storix
surface (sessions, layers, capabilities, the conformance-tested port semantics)
over the big object stores. Explicit, typed constructors; no provider SDK
vocabulary to learn.

Azure has two backends because the account kind matters: `AzureBackend` speaks
the Data Lake Gen2 endpoint (hierarchical-namespace accounts, with atomic
renames and true appends), `AzureBlobBackend` speaks the plain blob endpoint
(any account, flat included). The `azure` provider detects which you have and
builds the right one, so the recipe below is the same for both - see the
[backends guide](../guide/backends.md) for the per-kind differences.

```bash
uv add "storix[s3]"    # or "storix[gcs]", "storix[azure]"
```

## S3

```python
from storix import get_storage

fs = get_storage(
    "s3",
    bucket="my-bucket",
    region="us-east-1",
    access_key_id="...",
    secret_access_key="...",
)

fs.echo("hello from s3", "/hello.txt")
print(fs.cat("/hello.txt"))                  # b'hello from s3'
print(fs.url("/hello.txt", expires_in=600))  # presigned GET URL
```

Credentials and region are optional: omitted values resolve through the
standard AWS chain (environment variables, profile, IAM role), so on EC2/EKS
`get_storage("s3", bucket="my-bucket")` is usually the whole configuration.

## MinIO, R2, and other S3-compatible stores

The same recipe plus `endpoint`:

```python
fs = get_storage(
    "s3",
    bucket="my-bucket",
    endpoint="http://localhost:9000",
    region="us-east-1",
    access_key_id="minioadmin",
    secret_access_key="minioadmin",
)
```

A throwaway MinIO for local development:

```bash
docker run --rm -p 9000:9000 minio/minio server /data
```

## GCS

```python
fs = get_storage(
    "gcs",
    bucket="my-bucket",
    credential_path="/path/to/service-account.json",
)
```

Omitting the credential resolves through Google's application default
credentials, so on GCE/GKE the bucket alone is usually enough.

## Azure

One `azure` provider covers both account kinds: it detects whether the
account has hierarchical namespaces and builds `AzureBackend` (Data Lake Gen2)
or `AzureBlobBackend` (flat blob) accordingly. You never have to know which one
you have:

```python
fs = get_storage(
    "azure",
    container="raw",
    account_name="myaccount",
    credential="<SAS token or account key>",
)
```

On the blob side, use a SAS token as the credential when you need `url()`: a
bare account key cannot mint presigned URLs there. Pass `kind="blob"` (or
`"adls"`) explicitly when detection cannot run - container-scoped SAS,
anonymous public containers, or emulators like
[Azurite](https://learn.microsoft.com/azure/storage/common/storage-use-azurite)
via `endpoint="http://127.0.0.1:10000/devstoreaccount1"`.

## Scoping a session to a prefix

Both backends accept `root`, which anchors the session's `/` at a key prefix,
the object-store analogue of `LocalBackend`'s base directory:

```python
fs = get_storage("s3", bucket="my-bucket", root="/tenants/a")
```

## Environment-driven configuration

Every constructor argument mirrors a `STORIX_S3_*` / `STORIX_GCS_*` environment
key, so production configuration needs no code:

```bash
STORIX_PROVIDER=s3
STORIX_S3_BUCKET=my-bucket
STORIX_S3_REGION=us-east-1
```

Both backends advertise the `presigned_urls`, `custom_metadata`, and
`content_type` capabilities, so `url()`, metadata round-trips, and content
types work natively on either.
