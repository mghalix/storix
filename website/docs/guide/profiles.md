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
once, then list only what changes:

```toml
[profiles.media]
provider = "azure"
default_environment = "dev"
account_name = "mediaaccount"
credential = "env:MEDIA_AZURE_CREDENTIAL"

[profiles.media.environments.dev]
container = "media-dev"

[profiles.media.environments.prod]
container = "media-prod"
```

```python
fs = get_storage(profile="media", environment="prod")
```

```bash
sx --profile media --env prod ls /
```

A stage can change settings but never the provider: stages of one profile
share a backend by definition. A key that is not a setting of that provider
is an error naming the provider and its fields, so a block meant for another
backend cannot sit there unread.

`default_environment` pins the stage a profile usually runs on, so `--env`
is only needed to step off it.

## Why this matters for a pipeline

The alternative to a profile is a function that assembles coordinates from
scattered environment variables, once per entry point, slightly differently
each time. That is where dev credentials reach prod buckets.

A profile makes the connection a name the code passes and the operator
reads:

```python
# one job, three deployments, one line that changes
fs = get_storage(profile="warehouse", environment=os.environ["STAGE"])
```

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

| what | scope |
| --- | --- |
| `--profile` / `get_storage(profile=...)` | one command, one call |
| `STORIX_PROFILE` | one shell, `sx` only |
| `profile = "..."` in the project file | everyone working on that project |
| `profile = "..."` in your user file | you, everywhere |

```toml
# ~/.config/storix/config.toml - your personal default
profile = "media"
```

```toml
# storix.toml in a project - that project's default
profile = "media"
```

Typing `--profile` every time is not the intended workflow. Pin one.

`STORIX_PROFILE` and `STORIX_ENVIRONMENT` are read by `sx` and deliberately
not by the library: an operator's shell habit should not redirect a
service's sessions. A pinned `profile` key in a config file *is* honored by
both, because that is a property of the project rather than of the shell. In
code the selection stays explicit.

A profile names its own provider, so `-p` naming a different one is an error
rather than a silent override. `--env` without a profile, an unknown
profile, and an unknown stage each exit naming what is available.

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

## What a profile does not do

- It does not carry layers. Compose those per session
  (`Storix(be, layers=[...])`, `--cache`, `--sandbox`).
- It does not inherit from another profile. Deliberate, until a real case
  for it turns up; repeat the two lines instead.
- It does not switch providers per stage.

The full schema, with every key, is in
[`storix.toml.example`](https://github.com/mghalix/storix/blob/main/storix.toml.example).
