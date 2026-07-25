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

## From a config file

Non-secret settings can live in a file instead, which is how a project
carries its own storage configuration without every developer exporting the
same variables:

```toml
# storix.toml at the project root
provider = "s3"
max_transfer_ranges = 4

[s3]
bucket = "media"
region = "auto"
root = "/"

[local]
base = "./data"
```

[`storix.toml.example`](https://github.com/mghalix/storix/blob/main/storix.toml.example)
in the repository is the complete reference: every provider, every setting,
profiles, and the `[cli]` table, with a comment on each. It is validated
against the real settings models by the test suite, so it cannot drift out
of date without failing the build.

storix looks for `storix.toml`, then `.storix.toml`, then a
`pyproject.toml` carrying `[tool.storix]`, walking upward from the current
directory ruff-style; the first directory holding any of the three anchors
the project and stops the walk. Personal defaults live in `~/.config/storix/config.toml` on Linux and macOS,
and `%APPDATA%\storix\config.toml` on Windows. `XDG_CONFIG_HOME` overrides
that on any platform.

An unknown key or table is an error naming the file, the key, and the known
set - a setting that silently does nothing is worse than one that refuses to
load. Relative paths in a project file resolve against that file; in the
user file they must be absolute or `~`-prefixed, because a relative
machine-global path means nothing.

### Precedence

Strongest first, verified in that order:

| source | example |
| --- | --- |
| explicit keywords (and `sx` flags / `--set`) | `get_storage("local", base="./data")` |
| a selected profile and its stage overlay | `get_storage(profile="media")` |
| the process environment | `STORIX_LOCAL_BASE=/data` |
| the project `.env` | `STORIX_LOCAL_BASE=/data` in `.env` |
| the nearest project config file | `storix.toml` |
| the XDG user config file | `~/.config/storix/config.toml` |
| built-in defaults | `~/.storix` |

A profile sits above the process environment on purpose: selecting one is an
explicit act, and a stale exported variable must not quietly redirect it.

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

`STORIX_PROFILE`, `STORIX_ENVIRONMENT`, and a `profile = "media"` key pinned
in a config file are honored by `sx` only. In library code the selection is
always explicit, so `get_storage("s3")` beside `get_storage("azure")` means
what it says on every machine.

Profiles have their own page: [Profiles and stages](../guide/profiles.md).
