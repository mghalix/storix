# The sx CLI

`sx` is the storix core behind a command line: the same session, cwd, layers,
and typed errors, driven from your terminal. It ships in the `cli` extra, and
installs standalone with `uv tool`:

```bash
uv tool install "storix[cli]"          # + provider extras: [cli,s3], [cli,azure], [all]
```

=== "uv (in a project)"

    ```bash
    uv add "storix[cli]"
    ```

=== "pip"

    ```bash
    pip install "storix[cli]"
    ```

Run it one-shot, or with no command to enter the interactive shell:

```bash
sx --version       # print the installed version and exit
sx                 # interactive shell, anchored where you ran it
sx ls /            # or run a single command
sx -p azure ls /   # point it at a configured provider
```

Connection settings come from the same sources the library reads: the
`STORIX_*` environment variables, and now the provider sections of a config
file (`[s3]`, `[azure]`, ...). So `sx -p azure` talks to the account your code
already talks to. See [Configure from settings](../recipes/settings.md).

You should not have to come back here to use it. `sx --help` groups its
commands by what they do (navigate, read, write, transfer, and the ones about
sx itself) and its options by what they configure (connection, profile,
session), and three commands answer the questions this page otherwise would:

```bash
sx config show --effective   # what this session will do, and where each value came from
sx config sources            # which files are read, in which order they win
sx doctor                    # installation, config, and what it can reach
```

!!! info "`sx` with no configuration lists where you stand"

    With nothing configured - no flag, no profile, no environment variable,
    no config file - a `local` session anchors at the directory you ran `sx`
    from, the way `ls` does. Any configured base still wins.

    The **library** default is unchanged: `get_storage()` with zero config
    is still `~/.storix`. Library code writing to an application's working
    directory is a hazard; a human at a prompt is the one case where the cwd
    is the honest default.

## Unix commands, any backend

```
navigate   ls  pwd  cd  tree
read       cat  stat  du  url
search     find
write      touch  echo  mkdir
remove     rm  rmdir
move       mv  cp
transfer   push  pull
session    provider  provision  exists
```

Every command supports `--help`. Familiar flags behave as they do in unix:
`ls -l` (long), `-a` (hidden), `-t` (newest first), `-r` (reverse); `du -h`
and `ls -l` humanize sizes in binary units like coreutils (`165M`); `tree`
closes with the usual `N directories, M files`.

### Search, `du`, and `tree`

`find` searches recursively, the power-user (and agent) tool:

```bash
sx find /media --name '*.mp4' --type f   # every mp4 under /media
sx find --type d                         # all directories from cwd
```

`du` is 1:1 with unix: a cumulative size per **directory**, bottom-up, ending
with the total. Files are aggregated but not listed by default (like coreutils);
`-a` lists them, `-s` prints only the grand total, `-d N` caps the reported
depth, `-h` humanizes.

```bash
sx du /data          # per-directory sizes + total
sx du -a /data       # include every file
sx du -sh /data      # one human-readable total
```

For an itemized view - every file and directory with its size - use `tree -l`
(eza-style), which is the "show me everything and how big it is" companion to
`du`'s aggregate:

```bash
sx tree -l                 # kind + size columns on every entry
sx tree -L 2               # cap the depth at 2 levels
sx tree --sort size        # largest first (also: name, time)
```

### Provisioning the storage root

`sx provision` creates the backend's storage root if it is missing, and is
idempotent (safe to run in CI or a setup script):

```bash
sx -p azure provision   # provisioned: abfss://raw@acct.dfs.core.windows.net/
```

What it does depends on the backend, and the honest picture is narrow:

- **ADLS Gen2** (`azure`): creates the missing filesystem (container). This is
  the one real cloud provisioner. Already there: `already present: <uri>`.
- **local** and **memory**: report `already present` - the local base directory
  is created when the session opens, and the in-memory root always exists.
- **S3 / R2 / GCS / Azure Blob** (`s3`, `gcs`, `azblob`): **not supported**.
  These run on the opendal engine, which is data-plane only and has no
  create-bucket / create-container operation. `sx provision` exits non-zero with
  a message pointing you at your provider's own tooling (`aws s3 mb`,
  `gcloud storage buckets create`, `az storage container create`), rather than
  pretending it can create the bucket.

`sx mkdir` never creates a bucket or container - it operates *inside* an
existing root and creates a directory (or a directory marker on object stores).
Creating the root itself is a control-plane operation, which is exactly what
`provision` is for.

## The interactive shell

The shell keeps one live session, so `cd` persists between commands:

```
MemoryBackend / ❯ cd /docs
MemoryBackend /docs ❯ ls
```

Tab completes command names and remote paths; directories complete with a
trailing slash so you can walk straight down a tree. Completion sources a
live listing, so an active cache layer makes repeats instant. `help`,
`clear`, `refresh` (clear the cache), and `exit` are shell built-ins.

## Icons

Listings decorate entries with Nerd Font glyphs, the icon set
[eza](https://eza.rocks) and nvim-web-devicons draw from, which needs a
Nerd-Font-patched terminal font. Icons disable automatically when output is
not a terminal (`sx ls | grep ...` stays plain). Turn them off with
`--no-icons`, or persist the choice in a [config file](#configuration).

## Transfers with progress

`push` and `pull` move files between the local host and the provider,
rendering a live bar driven by the
[`ObservabilityLayer`](../recipes/progress.md):

```bash
sx push ./video.mp4 /media/video.mp4     # host -> provider
sx pull /media/video.mp4 ./video.mp4   # provider -> host
```

Both stream, so a file larger than memory moves fine. Uploads detect a
content type (from the extension, else by sniffing the head) and set it on
backends that support it.

### Profiles and stages

A profile is a named connection: the provider plus its settings, written
once in a config file and selected by name.

```toml
# storix.toml
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

The provider is named once and its settings sit directly in the profile;
each stage lists only what it changes. A key that is not a setting of that
provider is an error naming the provider and its fields, so a block meant
for another backend cannot sit there unread.

```bash
sx --profile media ls /                  # the profile's own settings
sx --profile media --env prod ls /       # with the prod overlay on top
STORIX_PROFILE=media sx ls /             # the same, for a whole shell session
```

A profile names its own provider, so `-p` naming a different one is an
error rather than a silent override, and an overlay can change settings but
never the provider - stages of one profile share a backend by definition.
`--env` without a profile, an unknown profile, and an unknown stage each
exit naming what is available.

#### A default profile

Typing `--profile` every time is not the intended workflow. Pin one, and
every `sx` invocation uses it with no flag:

```toml
# ~/.config/storix/config.toml - your personal default
profile = "media"

[profiles.media]
provider = "azure"
account_name = "mediaaccount"
container = "media"
credential = "env:MEDIA_AZURE_CREDENTIAL"
```

```toml
# storix.toml in a project - that project's default, for anyone who works on it
profile = "media"
```

Selection order is flag, then `STORIX_PROFILE`, then the pinned key: a
project's pin beats your personal one, `--profile` beats both for one
command, and `STORIX_PROFILE=other sx ...` beats both for one shell. A
profile can pin its own usual stage with `default_environment`, so `--env`
is only needed to step off it.

`STORIX_PROFILE` and `STORIX_ENVIRONMENT` are read by `sx` and deliberately
not by the library: an operator's shell habit should not redirect a
service's sessions. A pinned `profile` key in a config file *is* honored by
both, because that is a property of the project rather than of the shell.
In code the selection is explicit:

```python
fs = get_storage(profile="media", environment="prod")
```

### Tuning a transfer

`sx` reads the same `STORIX_*` environment your application does, so the
transfer knobs apply to the CLI without a separate config surface:

```bash
STORIX_MAX_TRANSFER_RANGES=1 sx pull /media/movie.mkv   # one stream per file
STORIX_AZURE_READ_PREFETCH_SIZE=4194304 sx pull /media  # less memory per stream
STORIX_S3_READ_CHUNK_SIZE=8388608 sx -p s3 pull /media  # fewer, larger requests
```

What each one trades away - memory per in-flight transfer against requests
per byte, and speed against transaction count - is in
[Tune transfers](../recipes/transfers.md).

### Stopping a transfer

Ctrl+C asks a running `push` or `pull` to stop, and it actually stops: every
stream unwinds at its next chunk boundary, the files that had not started
never start, and no worker keeps running behind your prompt. A half-written
local file is removed rather than left looking complete, so `pull` never
leaves a truncated file where a whole one belongs. The command reports it and
exits `130`, the shell's usual code for an interrupt:

```console
/ > pull /media/season-1
stopping...
pull: stopped
```

A second Ctrl+C skips the graceful path and interrupts immediately.

One asymmetry to know: a stopped `pull` removes the destination it was
writing, a stopped `push` does not. What it leaves depends on the backend,
because each one commits a write differently (measured, mid-upload stop):

| backend | destination after a stopped push |
| --- | --- |
| Azure ADLS Gen2 | the path exists, **length 0** - appended bytes are staged and never flushed |
| S3, GCS, Azure Blob | whatever the engine committed; an object store publishes on completion, so an interrupted upload may also leave an incomplete multipart upload behind |
| Local | the bytes written so far |

In every case the previous contents of that path are already gone: a `push`
truncates its destination when it opens it, so stopping does not preserve
what was there. storix does not then delete the path, for two reasons. The
first is that deleting cannot restore what the truncate destroyed, so it
would trade a wrong file for a missing one while the user is asking storix
to *stop* doing things. The second is that on an object store there may be
nothing to delete and the real leftover is an incomplete multipart upload,
which the storage port has no way to address.

Re-running the same `push` overwrites the destination. If you need a stop
(or a crash, or a dropped connection) to leave the destination untouched,
that is atomic writes - `echo(atomic=True)`, write-temp-then-move - which is
on the roadmap and not implemented today.

Both ends scaffold their destination: `push` creates missing destination
parents inside the storage root (directories, or key prefixes on an object
store), and `pull` creates missing local ones, so this works with no prior
`mkdir`:

```bash
sx -p s3 push ./video.mp4 /storix/demos/video.mp4
```

What neither does is create the storage root itself - the configured S3/R2
bucket, Azure container, or ADLS filesystem must already exist. Creating one
is a provider control-plane operation (`aws s3 mb`, `az storage container
create`, the R2 dashboard), not a filesystem operation, and `sx mkdir` only
ever creates directories *inside* the root. When the root is missing, every
command says so in one line:

```console
$ sx -p s3 ls
ls: configured s3 bucket 'media' does not exist
```

Pass `--debug` to any invocation to get the full provider traceback
(request IDs, HTTP context) behind that one line:

```bash
sx --debug -p s3 ls
```

## Provider settings on the command line

Non-secret provider coordinates can be set for one invocation, without touching
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
`sx` from, exactly like `ls`. Secrets are refused on the command line
(`--set s3.access_key_id=...` exits pointing at the environment), because a
flag lands in shell history.

## Layers

Two flags wrap the session for one invocation:

```bash
sx --sandbox /tmp/jail          # jail the session; it cannot escape
sx --cache --cache-ttl 300 du / # read-through cache: du/ls/stat/cat
```

The cache is where a long shell session pays off: `du` on a cloud tree costs
one full walk, and every repeat is free until you `refresh`. It is opt-in
because silently caching a live bucket hides other writers' uploads.

The sandbox root must already exist. `sx` checks it before jailing the
session, because afterwards the jail cannot say otherwise: inside it, the
missing root *is* `/`, and every command would fail with the unreadable
`path '/' does not exist`.

```console
$ sx --sandbox /videos ls
sx: sandbox root /videos does not exist on AzureBlobBackend (create it
first, or point --sandbox / the config layer elsewhere)
```

## Configuration

CLI preferences (icons, aliases, the layer stack) and non-secret provider
settings (bucket, base, region, ...) live in the same config files, so you do
not retype flags. Three canonical files are read; for any value, the strongest
source wins:

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

A profile sits above the environment on purpose: selecting one is an
explicit act, and a stale exported variable must not quietly redirect it.
The same chain applies to the library, with `get_storage()` keywords in
place of flags; see [Configure from settings](../recipes/settings.md).

### Keeping it working: `sx doctor` and `sx update`

```bash
sx doctor              # how storix is installed, configured, and what it reaches
sx doctor --updates    # the same, plus one question to PyPI
sx update              # upgrade through the package manager that installed it
sx update --check      # report installed and latest, change nothing
```

`sx doctor` reports the version and how it was installed, the Python it runs
on, which provider extras are importable, the config files it found, the
profile and stage in force, the effective provider with **where each value
came from**, and whether `$VISUAL`/`$EDITOR` is set for `config edit`. It
asks the network nothing unless you pass `--updates`.

`sx update` drives the package manager that installed storix and never
rewrites its own files. On a `uv tool` install it runs `uv tool upgrade
storix`, printing the command first - uv's receipt already remembers the
extras you asked for, so they survive the upgrade. Anywhere else (a
virtualenv, an editable checkout, a system install) it refuses and prints
the exact command for that context:

```console
$ sx update
sx: storix runs from a virtualenv install, which sx will not modify.
Upgrade it the way you installed it:
  /path/to/python -m pip install --upgrade storix
```

### Seeing and editing it: `sx config`

```bash
sx config path              # which files are read, and whether they exist
sx config sources           # what was found, and the precedence order
sx config show              # everything as storix reads it, secrets redacted
sx config show --effective  # what a session would actually use, and from where
sx config get s3.bucket     # one value, and the file that supplies it
sx config get --effective azure.read_prefetch_size
                            # the value actually in force, and where it came
                            # from - defaults included
sx config profiles          # profiles, their stages, and the default (marked *)

sx config set s3.bucket media           # writes the project file
sx config set azure.credential X --user   # --user == --scope user
sx config unset s3.region
sx config init              # a commented starter file; --force to overwrite
sx config validate          # load every file the way storix does
sx config edit              # $VISUAL, else $EDITOR
```

Writes go through a round-trip TOML editor, so **your comments and layout
survive**; they are validated against the same models a loaded file gets, so
an invalid edit is refused before the file changes; and they land atomically
(temp file, then rename), so an interrupted write cannot leave a half-file.

Project scope writes the nearest existing `storix.toml`, else a
`pyproject.toml` already carrying `[tool.storix]`, else it creates
`./storix.toml`. The target is always printed. `--user` is shorthand for
`--scope user` on every write, including `sx config edit --user` to open
your global config.

`get` without `--effective` answers "what does a file say", and says so when
no file says anything. `get --effective` answers "what will storix do",
which is usually the real question:

```console
$ sx config get azure.read_prefetch_size
sx: azure.read_prefetch_size is not set in any config file; try
`sx config get --effective azure.read_prefetch_size` for the value in force

$ sx config get --effective azure.read_prefetch_size
8388608 (8.0MiB) <- default
```

Secrets are redacted in every read command, including inside profiles.
Setting one in project scope is refused, naming the environment variable and
the `env:` form instead; user-scope files are created mode 600.

A complete annotated example of every key lives in the repository as
[`storix.toml.example`](https://github.com/mghalix/storix/blob/main/storix.toml.example).

The three canonical files:

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

Layers apply in listed order, each wrapping the previous, so the last entry
is outermost. Every built-in layer a config file can express has a name:

| Name | Layer | Options |
| --- | --- | --- |
| `cache` | `CacheLayer` (read-through: `du`/`ls`/`stat`/`cat`) | `ttl`, `max_bytes` |
| `sandbox` | `SandboxLayer` (escape-proof chroot) | `root` |
| `url` | `DataUrlLayer` (`url` on any backend) | none |
| `metadata` | `MetadataLayer` (custom metadata on any backend) | none |

`url` and `metadata` backfill a capability, so they are skipped when the
backend already has it natively: configure `url` and you get Azure's real SAS
link where one is available and a `data:` URL where it is not, from the same
config. `ObservabilityLayer` has no name here on purpose - its only argument
is a sink callable, which TOML cannot express, and `sx` attaches it itself
around `upload`/`download` to draw the progress bar.

Passing a layer flag replaces the configured stack for that invocation rather
than merging with it, so the effective stack is always readable from one
source. `sx provider` prints the active stack:

```
$ sx provider
backend: AzureBlobBackend
cwd:     /
layers:  cache ls/stat/du/cat via InMemoryCacheStore
```

Non-secret connection coordinates (bucket, container, account name, region,
endpoint, base) are project facts, so the same provider sections the library
reads live here too: `sx` and your code load them through one loader and
cannot drift. Only secrets stay out of a committed file. `provider` picks the
default backend for `sx`; setting `STORIX_PROVIDER` would drag your
application's library sessions onto the same backend, so it is a CLI habit
here, not a shared one. The library still never auto-applies a layer stack: in
code you opt in explicitly with `with_layer()`.

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

### Preferences

| Key | Default | Meaning |
| --- | --- | --- |
| `icons` | `true` | Nerd Font glyphs in listings (`--icons/--no-icons`) |
| `provider` | unset | Backend `sx` opens by default (`-p` still wins) |
| `dir_contents` | `true` | Show whether a directory is empty in flat listings |
| `layers` | `[]` | The always-on layer stack, innermost first |
| `alias` | `{}` | Command shortcuts (e.g. `{ la = "ls -a", lt = "tree -L 2" }`) |


#### `dir_contents`: the empty-folder icon, and what it costs

A directory listing tells you an entry *is* a directory. It does not tell you
whether that directory is empty - that answer is a second look, listing the
directory itself to see if anything comes back. Ordinary `ls` never takes that
look, which is why it does not distinguish empty from non-empty at all.
`dir_contents` controls whether `sx ls` does, so it can show an **open** folder
for an empty directory (nothing there, `rmdir` if you like) and a **closed**
folder for one that holds something (worth a `cd`).

The look is one extra listing per subdirectory, and the price depends on the
backend. On local disk it is a cheap directory read. On an object store it is
a network round trip, so listing a directory of fifty subdirectories with
`dir_contents` on is fifty-one requests instead of one. That is why it is a
setting rather than always-on: storix reaches cloud storage, where the cost is
real.

- Leave it `true` (the default) for the accurate empty/full distinction. With
  a `cache` layer active - which is worth having in the shell anyway (see
  below) - the repeat lookups are served from cache, so an interactive session
  pays the cost once.
- Set it `false` to make `ls` a single request again - every directory then
  shows the closed folder, empty or not. Also the right setting if you do not
  use icons and just want `ls` fast.

`tree` ignores this preference: it descends into every directory anyway, so it
already knows which are empty at no extra cost.

!!! tip "Turn on the cache for interactive sessions"

    In the shell you navigate the same tree repeatedly, so a read-through
    cache pays off immediately: `du`, `ls`, `stat`, and the `dir_contents`
    emptiness lookups are all served from memory on repeat, and you stop
    thinking about per-listing cost. Add it once, for the session or in your
    config:

    ```bash
    sx --cache            # this session
    ```

    ```toml
    [tool.storix.cli]
    layers = [{ name = "cache", ttl = 300 }]   # every session
    ```

    Your own writes self-evict, so the cache never shows you stale results for
    changes you made; only other writers' changes wait for the TTL.
