# Installation

Storix requires Python 3.12 or newer.

## Install

=== "uv"

    ```bash
    uv add storix             # local filesystem + in-memory
    uv add "storix[azure]"    # + all of Azure Storage (ADLS Gen2 + Blob)
    uv add "storix[s3]"       # + Amazon S3
    uv add "storix[r2]"       # + Cloudflare R2
    uv add "storix[minio]"    # + MinIO
    uv add "storix[gcs]"      # + Google Cloud Storage
    uv add "storix[cli]"      # + the sx command-line interface
    uv add "storix[all]"      # all optional features
    ```

=== "pip"

    ```bash
    pip install storix
    pip install "storix[azure]"
    pip install "storix[s3]"
    pip install "storix[r2]"
    pip install "storix[minio]"
    pip install "storix[gcs]"
    pip install "storix[cli]"
    pip install "storix[all]"
    ```

??? note "Why `r2` and `minio` install the same thing as `s3`"

    Cloudflare R2 and MinIO both speak the S3 API, so `S3Backend` drives
    them: point it at their endpoint and everything works. The extras are
    aliases for `storix[s3]`, so you can install the store you actually use
    without first having to know it is S3 underneath. See
    [S3, GCS, and Azure Blob](../recipes/object-stores.md) for endpoint
    settings.

The base install gives you the `LocalBackend` (real disk) and the
`MemoryBackend` (an in-process store, ideal for tests). Cloud backends are
optional extras so you only pull in a provider SDK when you need it.

| Extra | Adds |
| --- | --- |
| (none) | `LocalBackend`, `MemoryBackend` |
| `azure` | `AzureBackend` + `AzureBlobBackend`: all of Azure Storage, any account kind, with auto-detection |
| `azadls` | `AzureBackend` only: lean ADLS Gen2 install (pass `kind="adls"` explicitly) |
| `azblob` | `AzureBlobBackend` only: lean blob-only install (pass `kind="blob"` explicitly) |
| `s3` | `S3Backend` (Amazon S3, plus S3-compatible stores) |
| `r2` | Cloudflare R2: an alias for `s3`, which speaks its API |
| `minio` | MinIO: an alias for `s3`, which speaks its API |
| `gcs` | `GcsBackend` (Google Cloud Storage) |
| `cli` | the `sx` command-line interface and interactive shell |
| `all` | every backend and tool above |

## Verify

```python
from storix import Storix
from storix.backends import MemoryBackend

fs = Storix(MemoryBackend())
fs.echo("it works", "/hello.txt")
print(fs.ls())                # [StorixPath('hello.txt')]
print(fs.cat("/hello.txt"))   # b'it works'
```

If that prints `b'it works'`, you are ready. The `MemoryBackend` needs no
configuration and touches nothing on disk, which makes it the quickest way to
try things out.

## The CLI

The CLI dependencies are optional. Install `storix[cli]` (or `storix[all]`)
before using `sx`, a small shell over the same core:

=== "uv"

    ```bash
    uv add "storix[cli]"
    ```

=== "pip"

    ```bash
    pip install "storix[cli]"
    ```

```bash
sx                 # start the interactive shell (defaults to ~/.storix)
sx ls /            # or run a single command
sx -p azure ls /   # point it at a configured provider
```

If you run the launcher without the extra, it exits with the install command
instead of an optional-dependency traceback.

Tab completion, icons, transfer progress bars, and the persistent config file
are covered in [The sx CLI](../guide/cli.md).

Next: the [Quickstart](quickstart.md).
