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

`sx` is a small shell over the same core. It is standalone: install it once
with `uv tool` and it works from any directory, no project checkout or virtual
environment needed.

### One line

```bash
curl -LsSf https://storix.mghalix.com/install.sh | sh
```

```bash
curl -LsSf https://storix.mghalix.com/install.sh | sh -s -- --with azure,s3
curl -LsSf https://storix.mghalix.com/install.sh | sh -s -- --all
curl -LsSf https://storix.mghalix.com/install.sh | sh -s -- --version 0.5.0
curl -LsSf https://storix.mghalix.com/install.sh | sh -s -- --help
```

The script is a thin wrapper over `uv tool install`: it installs one tool for
your user, and it does **not** need root, ask for credentials, write any
configuration, or edit your shell startup files. If `uv` is missing it says so
and runs the official uv installer first. Re-running it upgrades in place.

Piping a stranger's script into a shell deserves a look first, so read it
before you run it:

```bash
curl -LsSf https://storix.mghalix.com/install.sh -o install.sh
less install.sh
sh install.sh --with azure
```

On Windows, the same thing in PowerShell:

```powershell
powershell -c "irm https://storix.mghalix.com/install.ps1 | iex"
```

```powershell
# with options, PowerShell needs the script as a block:
& ([scriptblock]::Create((irm https://storix.mghalix.com/install.ps1))) -With azure,s3
```

Both scripts take the same options (`--with`/`-With`, `--all`/`-All`,
`--version`/`-Version`, `--help`/`-Help`) and are exercised on every change by
a CI job that installs storix from them on Linux and Windows and runs the
result.

### Uninstall

```bash
uv tool uninstall storix
```

### With uv or pip directly

```bash
uv tool install "storix[cli]"                 # sx, local backend only
uv tool install "storix[cli,azure]"           # + both Azure backends
uv tool install "storix[cli,s3]"              # + S3/R2/MinIO
uv tool install "storix[cli,gcs]"             # + Google Cloud Storage
uv tool install "storix[cli,azure,s3,gcs]"    # a mix
uv tool install "storix[all]"                 # everything
```

Inside a project you can instead add it as a dependency:

=== "uv"

    ```bash
    uv add "storix[cli]"
    ```

=== "pip"

    ```bash
    pip install "storix[cli]"
    ```

```bash
sx --version       # print the installed version
sx                 # start the interactive shell, anchored where you ran it
sx ls /            # or run a single command
sx -p azure ls /   # point it at a configured provider
```

A globally installed `sx` discovers its configuration from three canonical
files (a project `storix.toml`, `pyproject.toml`'s `[tool.storix]`, and the
user file `~/.config/storix/config.toml`) plus the `STORIX_*` environment, so
it does not need a cwd-local `.env`. See [The sx CLI](../cli/index.md) for the
flags, the precedence chain, and the secret policy.

If you run the launcher without the `cli` extra, or name a provider whose extra
is missing, it exits with the exact install command instead of an
optional-dependency traceback. On a uv tool install that command is `sx install
s3`: extras can be added after the fact, without rerunning the installer. See
[doctor, install and update](../cli/maintenance.md).

Tab completion, icons, transfer progress bars, and the persistent config file
are covered in [The sx CLI](../cli/index.md).

Next: the [Quickstart](quickstart.md).
