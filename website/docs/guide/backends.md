# Backends

A backend is what a session actually reads and writes. Storix ships three, and
the same session code runs over any of them.

| Backend | Import | Use it for |
| --- | --- | --- |
| `LocalBackend` | `storix.backends.LocalBackend` | real files on disk, anchored at a base directory |
| `MemoryBackend` | `storix.backends.MemoryBackend` | tests and scratch work; nothing touches disk |
| `AzureBackend` | `storix.backends.AzureBackend` | Azure Data Lake Gen2 (hierarchical namespace accounts) |

```python
from storix import Storix
from storix.backends import LocalBackend, MemoryBackend

Storix(LocalBackend("~/storix-data"))   # '/' is ~/storix-data
Storix(MemoryBackend())          # in-process, disposable
```

## The port

Every backend implements one small interface, the 17-method `StorageBackend`
port (read, write, list, stat, and friends). The core `Storix` engine owns
all the unix behavior (cwd, path resolution, `mv` as copy-plus-delete, and so on)
and calls only that port. Backends do no path logic and raise only
`storix.errors`.

That boundary is why swapping backends changes nothing above it, and why a new
provider is just a new class that implements the port. You can register your own:

```python
from storix import register_backend

register_backend("myprovider", MyBackend)
```

See [Write a custom backend](../recipes/custom-backend.md) for a runnable
implementation and the whole-object/streaming fallback contract.

## Configuration and the factory

`get_storage` builds a session from the environment, so application code does not
hard-code a provider:

```python
from storix import get_storage

fs = get_storage()              # provider from STORIX_PROVIDER (default: local)
fs = get_storage("local", base="~/storix-data")  # explicit typed override
fs = get_storage("azure")       # reads STORIX_AZURE_* from the environment

fs = get_storage(
    "azure",
    container="raw",
    account_name="myaccount",
    credential="<account key or SAS token>",
)
```

Configuration is namespaced under `STORIX_`:

```bash
STORIX_PROVIDER=azure
STORIX_AZURE_CONTAINER=raw
STORIX_AZURE_ACCOUNT_NAME=myaccount
STORIX_AZURE_CREDENTIAL=...
# optional transfer tuning (bytes):
STORIX_AZURE_READ_CHUNK_SIZE=4194304
STORIX_AZURE_WRITE_CHUNK_SIZE=4194304
STORIX_AZURE_READ_PREFETCH_SIZE=33554432
# for local:
STORIX_LOCAL_BASE=~/storix-data
```

Settings are read from the process environment and a `.env` file in the current
working directory. Overrides passed to `get_storage` win over both, and every
backend config field mirrors its constructor keyword, so the env key always
matches the argument name.

!!! note "Azure validates on first I/O"

    Constructing an Azure session does not make a network request. Azure alone
    can validate the account and credential, so that happens on the first I/O
    operation. Invalid authentication configuration raises `ConfigurationError`
    with a hint to check `account_name` and `credential`. An authenticated
    identity that lacks permission raises `PermissionDeniedError`. The original
    Azure SDK exception remains chained for diagnosis.

Azure defaults to 4 MiB range reads and write batches, with a 32 MiB initial
download request. These SDK buffers live in the application's memory. Tune them
at provider construction when your host or workload needs different bounds;
use per-call `stream(chunk_size=...)` and `echo(chunk_size=...)` for consumer and
write-batch control.

## Capabilities

Backends differ in what they can do. Azure can mint presigned URLs and store
custom metadata; local disk cannot. Storix makes those differences explicit
rather than silent: a backend advertises `capabilities`, and asking for one it
lacks raises `UnsupportedOperationError` naming the missing capability instead of
quietly dropping your argument.

```python
azure = get_storage("azure")
azure.url("/f.png", expires_in=600)  # presigned SAS URL

local = get_storage("local", base="~/storix-data")
local.echo("hello from storix", "/hello.txt")
durl = local.data_url("/hello.txt")  # works on every backend
print(durl)
```

Paste the printed `data:` URL into a browser to open the file without hosting
it. Calling `local.url(...)` directly raises `UnsupportedOperationError` because
local storage cannot mint a presigned URL. A
[capability layer](layers.md#portable-capabilities) can backfill `url()` when one
code path must work across providers.
