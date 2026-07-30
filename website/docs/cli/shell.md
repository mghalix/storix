# The interactive shell

Run `sx` with no command, and you get a prompt instead of a single answer:

```console
/ ❯ cd /docs
/docs ❯ ls
```

The shell keeps one live session, so `cd` persists between commands. That is
the whole reason it exists: a one-shot `sx cd /docs` would change directory and
then exit, which is not a useful thing to do.

The prompt is only the cwd. Who you are connected to and what wraps the session
are stable facts, so the banner states them once and `whereami` reprints them on
demand, rather than prefixing every line with a label that grows with each
layer.

`sx --interactive` (or `-i`, or `sx shell`) does the same thing explicitly,
which is what you want when you also pass connection flags:

```bash
sx -p azure --cache -i
```

## Tab completion

Tab completes command names and remote paths. Directories complete with a
trailing slash, so you can walk straight down a tree without a `ls` between
each step.

Completion sources a live listing, so an active
[cache layer](preferences.md#layers) makes repeats instant. On a cloud backend
that is the difference between a prompt that feels local and one that pauses on
every Tab.

## Glob expansion

Patterns typed at the prompt are expanded against the session before the
command runs, so they work the way they do in a shell:

```console
/ ❯ ls *.txt
/ ❯ cat sub/*.md
/ ❯ rm *.tmp
```

The outer shell cannot do this for you: the paths are in the backend, so
without expansion `ls *.txt` reports a path named `*.txt` that never existed.

`*` (a run of non-separator characters), `?` (one such character), and `**`
(any number of directory levels) are the wildcards, the same set the core
[`glob`](../recipes/listing-and-searching.md#find-vs-glob) matches. Character
classes such as `[abc]` are not
supported, and a trailing slash is part of the pattern rather than a
directories-only filter, so write `sub*`, not `sub*/`.

Expansion yields absolute paths, sorted, one argument per match, so a pattern
with several matches needs a command that accepts several paths.

A pattern that matches nothing is reported and nothing runs:

```console
/ ❯ rm *.tmp
no matches: *.tmp
```

That is zsh's behavior rather than bash's, which leaves the pattern in place
for the command to fail on. The command here may be `rm` or `mv`, and a store
that accepts `*` in a key would take the unexpanded pattern as a literal path
and act on it.

A leading dot has to be explicit, as in `pathlib` and in a shell: `*` skips
hidden entries and `.e*` reaches `.env`.

Quote or escape a wildcard to keep it a plain character:

```console
/ ❯ echo '*' -f /star.txt
/ ❯ ls \*.txt
```

Two positions are never expanded. An option is one, because a leading `-` is
an option however it is spelled, and a redirect target is the other, because it
names a file being written rather than one to be found:

```console
/ ❯ ls -l > /listing*.txt      # writes /listing*.txt
```

!!! warning "A pattern costs a recursive listing"

    Matching walks the whole subtree below the pattern's fixed leading
    directories and tests every entry, so a shallow `*.txt` still visits every
    descendant. Naming a directory bounds it, so `sub/*.md` walks `sub` and
    not the rest of the tree, and on a cloud backend that is the difference
    between listing one prefix and listing the store. A
    [cache layer](preferences.md#layers) also absorbs the repeats.

## Built-ins

Five names are handled by the shell itself rather than dispatched to a storage
command:

| Built-in | What it does |
| --- | --- |
| `help` | show the commands |
| `clear` | clear the screen |
| `refresh` | clear the cache layer |
| `exit`, `quit` | leave the shell |

## Knowing what you are connected to

The banner names what the session opened, including the profile and stage when
one is selected:

```console
storix shell
connected to AzureBackend as media (stage: prod)
cache ls/stat/du/cat via InMemoryCacheStore · type refresh to clear
type 'help' for commands, 'whereami' for this session, 'exit' to quit
```

`whereami` reprints it at any point, with more detail:

```console
/ ❯ whereami
backend:  AzureBackend
profile:  media (stage: prod)
root uri: abfss://media-prod@mediaaccount.dfs.core.windows.net/
cwd:      /
home:     /
layers:   cache ls/stat/du/cat via InMemoryCacheStore
```

## Aliases at the prompt

Aliases work in the shell exactly as they do one-shot, and completion lists
them alongside the real commands with their target as the description. They are
configured once in a config file; see
[Preferences and layers](preferences.md#aliases).

!!! tip "Turn on the cache for interactive sessions"

    In the shell you navigate the same tree repeatedly, so a read-through cache
    pays off immediately: `du`, `ls`, `stat`, and the emptiness lookups behind
    the folder icons are all served from memory on repeat, and you stop
    thinking about per-listing cost.

    ```bash
    sx --cache            # this session
    ```

    ```toml
    [tool.storix.cli]
    layers = [{ name = "cache", ttl = 300 }]   # every session
    ```

    Your own writes self-evict, so the cache never shows you stale results for
    changes you made; only other writers' changes wait for the TTL.
