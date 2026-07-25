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
# Optional transfer sizes (every provider takes the first two). A byte count
# or a readable size: 4MiB is 4194304, 4MB is 4000000 - not synonyms.
STORIX_AZURE_READ_CHUNK_SIZE=4MiB
STORIX_AZURE_WRITE_CHUNK_SIZE=4MiB
STORIX_AZURE_READ_PREFETCH_SIZE=8MiB
# Optional, any provider: ceiling on parallel ranges per file (1 disables)
STORIX_MAX_TRANSFER_RANGES=8
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
`LocalBackend` option and `container=` an `AzureBackend` option. The transfer
sizes are the exception: `read_chunk_size` and `write_chunk_size` are understood
by every provider, and `read_prefetch_size` by every provider that fetches over
the network, so the same names work whichever backend you are on. All must be
positive. Defaults and what they trade against each other are in
[Tune transfers](transfers.md).

The cached `get_fs()` is a process-level resource. Close it from your
application's shutdown hook. The [FastAPI recipe](fastapi.md) shows the same
lifetime explicitly with `lifespan`.

## Secrets in config files

A config file may reference a secret instead of holding one:

```toml
[azure]
credential = "env:MEDIA_AZURE_CREDENTIAL"
```

The reference resolves from the process environment first, then from the
project `.env` - the same file `STORIX_*` settings already come from, so a
secret kept there is not invisible to an `env:` reference. A variable set in
neither place is an error naming both. A literal secret in a project file is
refused outright (project files get committed); the XDG user file may hold
one, and warns if it is group- or world-readable.

## Named profiles

A profile bundles a provider and its settings under a name, with optional
stage overlays:

```toml
[profiles.media]
provider = "s3"
default_environment = "dev"
region = "auto"

[profiles.media.environments.dev]
bucket = "media-dev"

[profiles.media.environments.prod]
bucket = "media-prod"
```

```python
fs = get_storage(profile="media")
fs = get_storage(profile="media", environment="prod")
```

The profile supplies the provider, so `get_storage("gcs", profile="media")`
is an error rather than an override; explicit keywords still win over the
profile's values. A project profile shadows a user profile of the same name
whole, so the effective profile is always readable from one file.

`STORIX_PROFILE` and `STORIX_ENVIRONMENT` are honored by `sx` only - naming
a profile in library code is explicit, or pinned per project with a
top-level `profile = "media"` key in the config file.
