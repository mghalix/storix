# The sx CLI

`sx` is the storix core behind a command line: the same session, cwd, layers,
and typed errors, driven from your terminal. It ships in the `cli` extra.

=== "uv"

    ```bash
    uv add "storix[cli]"
    ```

=== "pip"

    ```bash
    pip install "storix[cli]"
    ```

Run it one-shot, or with no command to enter the interactive shell:

```bash
sx                 # interactive shell (defaults to ~/.storix)
sx ls /            # or run a single command
sx -p azure ls /   # point it at a configured provider
```

Connection settings are the same `STORIX_*` environment variables the library
reads, so `sx -p azure` talks to the account your code already talks to. See
[Configure from settings](../recipes/settings.md).

## Unix commands, any backend

```
navigate   ls  pwd  cd  tree
read       cat  stat  du  url
search     find
write      touch  echo  mkdir
remove     rm  rmdir
move       mv  cp
transfer   push  pull
session    provider  exists
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

Preferences and an always-on layer stack persist in a config file, so you do
not retype flags. Sources, strongest first:

1. command-line flags
2. the nearest project config, searching upward from the current directory:
   `storix.toml` > `.storix.toml` (a `[cli]` table) > `pyproject.toml`
   (`[tool.storix.cli]`)
3. `STORIX_CLI_*` environment variables
4. your personal defaults: `~/.config/storix/config.toml`
5. built-in defaults

=== "storix.toml"

    ```toml
    [cli]
    icons = true
    provider = 'azure'    # which backend sx opens by default
    # every sx session gets the read-through cache - handy against cloud
    # providers, where a repeated ls or du is a real round trip
    layers = [{ name = "cache", ttl = 300 }]
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

`provider` is the one connection key that lives here, because "which
backend do I explore by default" is a habit of yours, not of your code:
setting `STORIX_PROVIDER` would drag your application's library sessions
onto the same backend. *How* to connect (credentials, account names, base
directories) stays shared with the library at `STORIX_*` / `[tool.storix]`,
and the library never auto-applies a layer stack: in code you opt in
explicitly with `with_layer()`.

That split is enforced, not assumed. An unknown key, or a credential put
here by mistake, exits with the fix named rather than being silently
ignored:

```console
$ sx ls
sx: 'account_name' is not a CLI preference - it is connection config,
shared with the library. Set it via STORIX_AZURE_* (env or .env).
```

### Preferences

| Key | Default | Meaning |
| --- | --- | --- |
| `icons` | `true` | Nerd Font glyphs in listings (`--icons/--no-icons`) |
| `provider` | unset | Backend `sx` opens by default (`-p` still wins) |
| `dir_contents` | `true` | Show whether a directory is empty in flat listings |
| `layers` | `[]` | The always-on layer stack, innermost first |

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
