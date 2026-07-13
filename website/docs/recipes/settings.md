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
STORIX_AZURE_READ_PREFETCH_SIZE=33554432
```

```python
from storix import get_storage

fs = get_storage()   # provider and credentials come from the environment
```

## From your app's settings

To keep storage config next to the rest of your configuration, wrap it in your
own `BaseSettings` and pass overrides, which win over the environment:

```python
--8<-- "samples/recipes/settings.py"
```

Overrides map one-to-one onto a backend's constructor keywords, so `base=` is a
`LocalBackend` option, `container=` an `AzureBackend` option, and so on. Azure's
transfer sizes must be positive; its defaults are 4 MiB for range reads and
write batches, plus a 32 MiB initial download request.
