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
write      touch  echo  mkdir
remove     rm  rmdir
move       mv  cp
transfer   upload  download
session    provider  exists
```

Every command supports `--help`. Familiar flags behave as they do in unix:
`ls -l` (long), `-a` (hidden), `-t` (newest first), `-r` (reverse); `du -h`
and `ls -l` humanize sizes in binary units like coreutils (`165M`); `tree`
closes with the usual `N directories, M files`.

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

`upload` and `download` move files between the local host and the provider,
rendering a live bar driven by the
[`ObservabilityLayer`](../recipes/progress.md):

```bash
sx upload ./video.mp4 /media/video.mp4     # host -> provider
sx download /media/video.mp4 ./video.mp4   # provider -> host
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

```toml
# ~/.config/storix/config.toml
[cli]
icons = true

# every sx session gets the read-through cache - handy against cloud
# providers, where a repeated ls or du is a real round trip
[[cli.layers]]
name = "cache"
ttl = 300
```

In `pyproject.toml` the same tables live under `[tool.storix.cli]` and
`[[tool.storix.cli.layers]]`.

Layers apply in listed order, each wrapping the previous, so the last entry
is outermost. The available names mirror the flags: `cache` (options: `ttl`,
`max_bytes`) and `sandbox` (`root`). Passing a layer flag replaces the
configured stack for that invocation rather than merging with it, so the
effective stack is always readable from one source. `sx provider` prints the
active stack:

```
$ sx provider
backend: AzureBlobBackend
cwd:     /
layers:  cache ls/stat/du/cat via InMemoryCacheStore
```

Only CLI preferences and the layer stack live here. Connection config stays
shared with the library at `STORIX_*` / `[tool.storix]`, and the library
never auto-applies a layer stack: in code you opt in explicitly with
`with_layer()`.

That split is enforced, not assumed. An unknown key, or a connection setting
put here by mistake, exits with the fix named rather than being silently
ignored:

```console
$ sx ls
sx: 'provider' is not a CLI preference - it is connection config, shared
with the library. Set it via STORIX_PROVIDER (env or .env).
```

So to point `sx` at a provider by default, set `STORIX_PROVIDER=azure` in
your environment or a `.env` file, which the library reads too. Use
`sx -p azure` for a one-off.
