# S3 and GCS

`S3Backend` and `GcsBackend` run the whole storix surface (sessions, layers,
capabilities, the conformance-tested port semantics) over the two big object
stores. Explicit, typed constructors; no provider SDK vocabulary to learn.

```bash
uv add "storix[s3]"    # or "storix[gcs]"
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
