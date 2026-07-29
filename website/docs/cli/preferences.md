# Preferences and layers

Preferences are the parts of `sx` you set once and stop thinking about. They
live in the same [config files](configuration.md#the-three-files) as everything
else.

| Key | Default | Meaning |
| --- | --- | --- |
| `icons` | `true` | Nerd Font glyphs in listings (`--icons`/`--no-icons`) |
| `provider` | unset | Backend `sx` opens by default (`-p` still wins) |
| `dir_contents` | `true` | Show whether a directory is empty in flat listings |
| `layers` | `[]` | The always-on layer stack, innermost first |
| `alias` | `{}` | Command shortcuts (e.g. `{ la = "ls -a", lt = "tree -L 2" }`) |

## Aliases

An alias is a command shortcut, the same idea as a shell alias:

```toml
[alias]
la = "ls -a"
lt = "tree -L 2"
mp4 = "find --name '*.mp4' --type f"
```

```bash
sx la /media          # -> sx ls -a /media
sx mp4 /media         # -> sx find --name '*.mp4' --type f /media
```

They work identically one-shot and in the [interactive shell](shell.md), where
tab completion lists them next to the real commands with their target as the
description.

A few rules worth knowing, all of them what a shell alias would do:

- **Only the command position expands.** `sx touch la` creates a file called
  `la`; an alias never rewrites an argument.
- **Arguments you type are appended.** `la /media` becomes `ls -a /media`, so
  an alias is a prefix, not a whole command line.
- **Targets are parsed like a shell parses them**, so quoting holds:
  `find --name '*.mp4'` keeps the glob as one argument.
- **Aliases can point at aliases.** `ll = "la -l"` with `la = "ls -a"` gives
  `ls -a -l`. A cycle stops rather than looping.
- **Aliasing a real command is allowed**, and expands once:
  `ls = "ls -a"` makes plain `sx ls` include hidden entries.

`[aliases]` is accepted as a spelling of `[alias]`. Aliases cannot be set
through the environment, because `STORIX_CLI_*` variables carry single values
and a table is not one; put them in a file.

!!! warning "Known limitation: aliases after `--profile` or `--env`"

    Alias expansion currently scans past global options to find the command,
    but it does not know that `--profile` and `--environment`/`--env` take a
    value. So `sx --profile media la /` runs `la` unexpanded instead of
    `ls -a`. Use `STORIX_PROFILE=media sx la /`, or pin the profile in a config
    file, until this is fixed. `-p`/`--provider` and the connection flags are
    unaffected.

## Icons

Listings decorate entries with Nerd Font glyphs, the icon set
[eza](https://eza.rocks) and nvim-web-devicons draw from, which needs a
Nerd-Font-patched terminal font.

Icons disable automatically when output is not a terminal, so `sx ls | grep ...`
stays plain. Turn them off with `--no-icons`, or persist the choice:

```toml
icons = false
```

### `dir_contents`: the empty-folder icon, and what it costs

A directory listing tells you an entry *is* a directory. It does not tell you
whether that directory is empty - that answer is a second look, listing the
directory itself to see if anything comes back. Ordinary `ls` never takes that
look, which is why it does not distinguish empty from non-empty at all.

`dir_contents` controls whether `sx ls` does, so it can show an **open** folder
for an empty directory (nothing there, `rmdir` if you like) and a **closed**
folder for one that holds something (worth a `cd`).

The look is one extra listing per subdirectory, and the price depends on the
backend. On local disk it is a cheap directory read. On an object store it is a
network round trip, so listing a directory of fifty subdirectories with
`dir_contents` on is fifty-one requests instead of one. That is why it is a
setting rather than always-on: storix reaches cloud storage, where the cost is
real.

- Leave it `true` (the default) for the accurate empty/full distinction. With a
  `cache` layer active the repeat lookups are served from cache, so an
  interactive session pays the cost once.
- Set it `false` to make `ls` a single request again - every directory then
  shows the closed folder, empty or not. Also the right setting if you do not
  use icons and just want `ls` fast.

`tree` ignores this preference: it descends into every directory anyway, so it
already knows which are empty at no extra cost.

## Layers

Two flags wrap the session for one invocation:

```bash
sx --sandbox /tmp/jail          # jail the session; it cannot escape
sx --cache --cache-ttl 300 du / # read-through cache: du/ls/stat/cat
```

Or configure a stack that every session gets:

```toml
layers = [{ name = "cache", ttl = 300 }]
```

Layers apply in listed order, each wrapping the previous, so the last entry is
outermost. Every built-in layer a config file can express has a name:

| Name | Layer | Options |
| --- | --- | --- |
| `cache` | `CacheLayer` (read-through: `du`/`ls`/`stat`/`cat`) | `ttl`, `max_bytes` |
| `sandbox` | `SandboxLayer` (escape-proof chroot) | `root` |
| `url` | `DataUrlLayer` (`url` on any backend) | none |
| `metadata` | `MetadataLayer` (custom metadata on any backend) | none |

`url` and `metadata` backfill a capability, so they are skipped when the backend
already has it natively: configure `url` and you get Azure's real SAS link where
one is available and a `data:` URL where it is not, from the same config.
`ObservabilityLayer` has no name here on purpose - its only argument is a sink
callable, which TOML cannot express, and `sx` attaches it itself around
`upload`/`download` to draw the progress bar.

Passing a layer flag replaces the configured stack for that invocation rather
than merging with it, so the effective stack is always readable from one source.
`sx whereami` prints the active stack:

```console
$ sx whereami
backend:  AzureBlobBackend
root uri: https://acct.blob.core.windows.net/media/
cwd:      /
home:     /
layers:   cache ls/stat/du/cat via InMemoryCacheStore
```

### The cache

The cache is where a long shell session pays off: `du` on a cloud tree costs one
full walk, and every repeat is free until you `refresh`. It is opt-in because
silently caching a live bucket hides other writers' uploads.

### The sandbox

The sandbox root must already exist. `sx` checks it before jailing the session,
because afterwards the jail cannot say otherwise: inside it, the missing root
*is* `/`, and every command would fail with the unreadable
`path '/' does not exist`.

```console
$ sx --sandbox /videos ls
sx: sandbox root /videos does not exist on AzureBlobBackend (create it
first, or point --sandbox / the config layer elsewhere)
```
