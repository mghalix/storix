# Configure from settings

`get_storage` is already settings-driven: it reads `STORIX_PROVIDER` and the
`STORIX_<PROVIDER>_*` variables (or a `.env` file) through pydantic-settings. So
the simplest configuration is environment variables plus a bare `get_storage()`.

## From the environment

```bash
STORIX_PROVIDER=azure
STORIX_AZURE_CONTAINER=raw
STORIX_AZURE_ACCOUNT_NAME=myaccount
STORIX_AZURE_CREDENTIAL=...
# Optional, in bytes:
STORIX_AZURE_READ_CHUNK_SIZE=4194304
STORIX_AZURE_WRITE_CHUNK_SIZE=4194304
STORIX_AZURE_READ_PREFETCH_SIZE=8388608
```

```python
from storix import get_storage

fs = get_storage()   # provider and credentials come from the environment
```

## From your app's settings

To keep storage config next to the rest of your configuration, use the common
cached `get_settings()` pattern and derive one shared storage session from it.
Explicit overrides win over the environment:

```python
--8<-- "samples/recipes/settings.py"
```

Overrides map one-to-one onto a backend's constructor keywords, so `base=` is a
`LocalBackend` option, `container=` an `AzureBackend` option, and so on. Azure's
transfer sizes must be positive; its defaults are 4 MiB for range reads and
write batches, plus an 8 MiB initial download request. What those sizes trade
against each other is in [Tune transfers](transfers.md).

The cached `get_fs()` is a process-level resource. Close it from your
application's shutdown hook. The [FastAPI recipe](fastapi.md) shows the same
lifetime explicitly with `lifespan`.
