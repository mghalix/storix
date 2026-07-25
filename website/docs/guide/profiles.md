# Profiles and stages

A profile is a named connection: a provider plus its settings, written once
in a config file and selected by name. One name, in code or at a prompt,
instead of a block of coordinates repeated per script and per shell.

```toml
# storix.toml
[profiles.media]
provider = "azure"
account_name = "mediaaccount"
credential = "env:MEDIA_AZURE_CREDENTIAL"
container = "media"
```

```python
from storix import get_storage

fs = get_storage(profile="media")
```

```bash
sx --profile media ls /
```

The library and the CLI read the same file through the same loader, so a
profile a pipeline uses is a profile you can stand inside and inspect.

## Stages

A stage (an *environment*) overlays the settings that differ between
deployments of the same connection. Name the provider and everything stable
once, then list only what changes.

In practice what changes across deployments is not just the container: dev,
staging and production are usually separate accounts with separate
credentials. A stage carries both, so the layout of your infrastructure is
what the file describes:

```toml
[profiles.ingest]
provider = "azure"
container = "raw"
default_environment = "dev"

[profiles.ingest.environments.dev]
account_name = "acmedevstorage"
credential = "env:ACME_DEV_CREDENTIAL"

[profiles.ingest.environments.stg]
account_name = "acmestgstorage"
credential = "env:ACME_STG_CREDENTIAL"

[profiles.ingest.environments.prod]
account_name = "acmeprdstorage"
credential = "env:ACME_PRD_CREDENTIAL"
```

One name, one flag, three accounts:

```python
fs = get_storage(profile="ingest", environment="prod")
```

```bash
sx --profile ingest ls /                 # dev, the pinned default
sx --profile ingest --env prod ls /      # production
```

A separate credential per stage is the point. Each stage reads its own
variable, so the process running against `dev` never has the production
secret in its environment at all - the file describes which one to reach
for, and an unset variable fails loudly at load rather than silently
falling back to another stage's.

A stage can change settings but never the provider: stages of one profile
share a backend by definition. A key that is not a setting of that provider
is an error naming the provider and its fields, so a block meant for another
backend cannot sit there unread.

`default_environment` pins the stage a profile usually runs on, so `--env`
is only needed to step off it - and pinning `dev` means the dangerous one is
the one you have to type.

A stage can also be as small as one key when that is genuinely all that
differs:

```toml
[profiles.media]
provider = "azure"
account_name = "mediaaccount"
credential = "env:MEDIA_AZURE_CREDENTIAL"

[profiles.media.environments.dev]
container = "media-dev"

[profiles.media.environments.prod]
container = "media-prod"
```

## Why this matters for a pipeline

The alternative to a profile is a function that assembles coordinates from
scattered environment variables, once per entry point, slightly differently
each time. That is where dev credentials reach prod buckets.

A profile makes the connection a name the code passes and the operator
reads:

```python
# one job, three deployments, one line that changes
fs = get_storage(profile="ingest", environment=os.environ["STAGE"])
```

That line is the whole difference between a dev run and a production run:
the account, the credential, and the container come from the stage. A job
scheduled per environment passes its own `STAGE` and nothing else about it
varies, so there is no second place where a deployment can be half-switched.

Everything else about the session - layers, transfer tuning, the typed
errors - is unchanged. The profile decides only which store you are talking
to.

!!! tip "Secrets stay out of the file"

    `credential = "env:MEDIA_AZURE_CREDENTIAL"` reads that variable at load
    time, from the process environment or a `.env` beside the project. A
    literal secret in a *project* file is refused outright, because project
    files get committed. See [Configure from
    settings](../recipes/settings.md#secrets-in-config-files).

## Selecting one

Strongest first:

| what | applies to | scope |
| --- | --- | --- |
| `get_storage(profile=...)` | library | that call |
| `--profile` | `sx` | that command |
| `STORIX_PROFILE` | `sx` | that shell |
| `profile = "..."` in the project file | `sx` | everyone on that project |
| `profile = "..."` in your user file | `sx` | you, everywhere |

```toml
# ~/.config/storix/config.toml - your personal default
profile = "media"
```

```toml
# storix.toml in a project - that project's default
profile = "media"
```

Typing `--profile` every time is not the intended workflow. Pin one.

**A profile reaches the library only when a call asks for one.** Neither
`STORIX_PROFILE` nor a pinned `profile` key steers `get_storage()`. Both are
a person's convenience at a prompt, and a library that honored them would
let a personal file point an application's session at another account - and
would break the shape every migration takes:

```python
src = get_storage("azure", container="raw")
dst = get_storage("s3", bucket="archive")     # neither is redirected by a pin
```

`sx` honors all of it, because there the convenience is the point.

A profile names its own provider, so `sx --profile media -p s3` is an error:
you said two things. A profile that is merely *pinned* is a default, not a
lock, so `sx -p s3` simply steps off it. `--env` without a profile, an
unknown profile, and an unknown stage each exit naming what is available.

## Seeing which one is in force

```console
$ sx --profile media --env prod whereami
backend:  AzureBackend
profile:  media (stage: prod)
root uri: abfss://media-prod@mediaaccount.dfs.core.windows.net/
cwd:      /
home:     /
layers:   cache ls/stat/du/cat via InMemoryCacheStore
```

`sx config profiles` lists every profile as a table, stages as rows, with
`*` on what the invocation would use. `sx config show --effective` goes
further and prints each field with the layer that supplied it, so a value
you did not write is still traceable:

```console
$ sx --profile media --env prod config show --effective
effective
  provider     azure (profile 'media')
  azure.account_name         'mediaaccount' <- profile
  azure.container            'media-prod' <- environment
  azure.credential           '***' <- profile
  azure.read_prefetch_size   8388608 (8.0MiB) <- default
```

Neither command opens a connection or resolves a credential, so both still
answer when the connection is the thing that is broken.

## Sharing settings between profiles

A profile layers on top of that provider's own table, so settings common to
every profile on a backend are written once:

```toml
[s3]
region = "auto"
endpoint = "https://ACCOUNT.r2.cloudflarestorage.com"
access_key_id = "env:R2_ACCESS_KEY_ID"
secret_access_key = "env:R2_SECRET_ACCESS_KEY"

[profiles.media]
provider = "s3"
bucket = "media"

[profiles.archive]
provider = "s3"
bucket = "archive"
```

That is the right shape for *different buckets*: they are different
connections, so they are different profiles. Stages are for one connection
across deployments - `dev`, `stg`, `prod` - where the name carries meaning
about which deployment you are touching. Modelling unrelated buckets as
stages of one profile works mechanically and then reads as a lie:
`default_environment = "storix"` says a bucket is a deployment stage.

## What a profile does not do

- It does not carry layers. Compose those per session
  (`Storix(be, layers=[...])`, `--cache`, `--sandbox`).
- It does not inherit from another profile. Deliberate, until a real case
  for it turns up; repeat the two lines instead.
- It does not switch providers per stage.

The full schema, with every key, is in
[`storix.toml.example`](https://github.com/mghalix/storix/blob/main/storix.toml.example).
