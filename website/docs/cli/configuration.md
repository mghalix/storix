# Configuration

You should not have to retype a flag you have already decided on. CLI
preferences (icons, aliases, the layer stack) and non-secret provider settings
(bucket, base, region, ...) live in the same config files the library reads, so
`sx` and your code load them through one loader and cannot drift.

Start here:

```bash
sx config init              # a commented starter file
sx config show --effective  # what a session would actually use, and from where
```

## Which source wins

Three canonical files are read. For any value, the strongest source wins:

1. command-line flags and `--set`
2. the selected profile's stage overlay (`--env`)
3. the selected profile (`--profile`)
4. `STORIX_*` (provider settings) / `STORIX_CLI_*` (preferences) environment
   variables
5. a project `.env` (provider settings)
6. the nearest project config, searching upward from the current directory:
   `storix.toml` > `.storix.toml` (a compatibility alias) > `pyproject.toml`
   (`[tool.storix]`)
7. your personal defaults: `~/.config/storix/config.toml`
8. built-in defaults

A profile sits above the environment on purpose: selecting one is an explicit
act, and a stale exported variable must not quietly redirect it. The same chain
applies to the library, with `get_storage()` keywords in place of flags; see
[Configure from settings](../recipes/settings.md).

## The three files

```
~/.config/storix/config.toml      # user scope on Linux and macOS
%APPDATA%\storix\config.toml      # user scope on Windows
storix.toml                       # project scope, standalone
pyproject.toml -> [tool.storix]   # project scope, namespaced
```

`XDG_CONFIG_HOME` overrides the user location on every platform, including
Windows: a user who exports it means it.

=== "storix.toml"

    ```toml
    icons = true
    provider = 'azure'    # which backend sx opens by default
    # every sx session gets the read-through cache - handy against cloud
    # providers, where a repeated ls or du is a real round trip
    layers = [{ name = "cache", ttl = 300 }]

    [azure]               # non-secret connection coordinates live here too
    account_name = "myaccount"
    container = "media"
    credential = "env:AZURE_CREDENTIAL"   # secrets via env: refs, not literals
                                          # (resolved from the environment,
                                          #  then the project .env)

    [alias]
    lt = "tree"
    la = "ls -a"
    ```

=== "pyproject.toml"

    ```toml
    [tool.storix.cli]
    icons = true
    provider = 'azure'
    layers = [{ name = "cache", ttl = 300 }]
    ```

=== "one table per layer"

    ```toml
    # the same stack, if you prefer a table per layer over inline tables;
    # TOML treats the two forms as identical
    [cli]
    icons = true
    provider = 'azure'

    [[cli.layers]]
    name = "cache"
    ttl = 300
    ```

Non-secret connection coordinates (bucket, container, account name, region,
endpoint, base) are project facts, so the same provider sections the library
reads live here too. Only secrets stay out of a committed file.

`provider` picks the default backend for `sx`. Setting `STORIX_PROVIDER` would
drag your application's library sessions onto the same backend, so it is a CLI
habit here, not a shared one. The library also never auto-applies a layer
stack: in code you opt in explicitly with `with_layer()`.

A complete annotated example of every key lives in the repository as
[`storix.toml.example`](https://github.com/mghalix/storix/blob/main/storix.toml.example).

## Seeing and editing it: `sx config`

```bash
sx config path              # which files are read, and whether they exist
sx config sources           # what was found, and the precedence order
sx config show              # everything as storix reads it, secrets redacted
sx config show --effective  # what a session would actually use, and from where
sx config get s3.bucket     # one value, and the file that supplies it
sx config get --effective azure.read_prefetch_size
                            # the value actually in force, and where it came
                            # from - defaults included
sx config profiles          # every profile as a table, stages as rows

sx config set s3.bucket media             # writes the project file
sx config set azure.credential X --user   # --user == --scope user
sx config unset s3.region
sx config init              # a commented starter file; --force to overwrite
sx config validate          # load every file the way storix does
sx config edit              # $VISUAL, else $EDITOR
```

`get` without `--effective` answers "what does a file say", and says so when no
file says anything. `get --effective` answers "what will storix do", which is
usually the real question:

```console
$ sx config get azure.read_prefetch_size
sx: azure.read_prefetch_size is not set in any config file; try
`sx config get --effective azure.read_prefetch_size` for the value in force

$ sx config get --effective azure.read_prefetch_size
8388608 (8.0MiB) <- default
```

Profiles print as a table rather than as dotted keys, so a stage is a row under
its profile and `*` marks what this invocation would use:

```console
$ sx --profile media --env prod config profiles
profiles /home/you/.config/storix/config.toml
profile  provider  stage   settings
media *  azure             container = 'raw'
                   dev     account_name = 'acctdev'
                           credential = '***'
                   prod *  account_name = 'acctprod'
                           credential = '***'
* what this invocation would use
```

Every view follows the selection. `sx --profile media config show` shows
`media` and names the others rather than printing them, because they are not
what that command would use. Listing and explaining never resolve a credential,
so `sx config profiles` and `sx doctor` still work when an `env:` reference
points at a variable you have not exported - which is exactly when you reach
for them.

### How writes behave

Writes go through a round-trip TOML editor, so **your comments and layout
survive**; they are validated against the same models a loaded file gets, so an
invalid edit is refused before the file changes; and they land atomically (temp
file, then rename), so an interrupted write cannot leave a half-file.

Project scope writes the nearest existing `storix.toml`, else a `pyproject.toml`
already carrying `[tool.storix]`, else it creates `./storix.toml`. The target is
always printed. `--user` is shorthand for `--scope user` on every write,
including `sx config edit --user` to open your global config.

## Settings for one invocation

Non-secret provider coordinates can be set for one command, without touching
the environment or a file. Direct flags cover the common ones:

```bash
sx -p local --base .                       # local base at the current directory
sx -p s3 --bucket media --region auto ls   # bucket + region
sx -p azure --account-name acct --container media --kind adls ls
sx -p s3 --endpoint https://ACCOUNT.r2.cloudflarestorage.com --bucket media ls
```

`--base` (local), `--bucket`, `--container`, `--account-name`, `--region`,
`--endpoint`, `--root`, and `--kind` are validated against the effective
provider: a flag that does not belong to it exits naming the provider and the
flags it does accept, so `-p local --bucket x` never silently does nothing.

For any other field, `--set provider.field=value` is the repeatable escape
hatch (values are parsed type-aware through the same models):

```bash
sx -p azure --set azure.read_chunk_size=1048576 cat /big.bin
sx -p s3 --set s3.root=/tenants/a ls
```

A relative `--base` (or `--set`) path resolves against the directory you run
`sx` from, exactly like `ls`.

## Secrets

Secrets are refused on the command line (`--set s3.access_key_id=...` exits
pointing at the environment), because a flag lands in shell history. They are
redacted in every read command, including inside profiles. Setting one in
project scope is refused, naming the environment variable and the `env:` form
instead; user-scope files are created mode 600.

That contract is enforced, not assumed. An unknown key or table, or a literal
secret, exits with the fix named rather than being silently ignored:

```console
$ sx ls
sx: /home/you/proj/storix.toml: unknown table 'databse'; known: alias,
aliases, azure, cli, gcs, local, provider, s3

$ sx ls
sx: /home/you/proj/storix.toml: credential is a secret and project files are
committed; use env:VAR, the STORIX_* environment, or the user config
(~/.config/storix/config.toml)
```

## Profiles

A profile is a named connection, selected by name instead of spelled out:

```bash
sx --profile media ls /                  # the profile's own settings
sx --profile media --env prod ls /       # with the prod overlay on top
STORIX_PROFILE=media sx ls /             # the same, for a whole shell session
```

Pin one in a config file and no flag is needed at all. The same profiles drive
`get_storage(profile=..., environment=...)`, so a profile a pipeline runs on is
one you can stand inside and inspect. Written up in full, with the selection
order and the stage rules, in [Profiles and stages](../guide/profiles.md).
