# 22. CLI config file: preferences and the [[layers]] stack

Status: accepted

## Context

ADR 0015 pinned the config scoping rule (connection config shared at
`STORIX_*` / `[tool.storix]`; the layer stack CLI-scoped under
`[tool.storix.cli]`) and deliberately deferred the loader so `--cache` /
`--sandbox` never competed with a half-built file. Two things changed:

- `sx` grew display preferences (Nerd Font icons) that need to persist
  per user, not per invocation - a flag alone cannot express "my terminal
  has no Nerd Font, ever".
- The cache story proved itself in daily use against cloud providers,
  where "always wrap my session in the read-through cache" is a personal
  default, not a per-command decision.

## Decision

Land the config file now, scoped exactly as ADR 0015 designed it, in two
slices: flat preferences and the ordered `[[layers]]` stack.

**Sources and precedence** (strongest first): command-line flags; the
nearest project config, found by walking upward from cwd ruff-style
(`storix.toml` > `.storix.toml` > `pyproject.toml [tool.storix.cli]`,
the first file found anchors the project and stops the walk);
`STORIX_CLI_*` environment variables; the XDG user file
(`~/.config/storix/config.toml`); defaults. Standalone files use a
`[cli]` table (a `storix.toml` maps to `[tool.storix]`).

**Preferences** are a flat pydantic model (`CliPrefs`): `icons`, `provider`,
`dir_contents`, `layers`. The model forbids extras, so a typo or a
wrong-place key exits naming the known set instead of silently doing
nothing. Credentials and anchors reached for here (`account_name`, `base`,
...) get a targeted error naming their real home, because ADR 0015's
scoping rule only helps if a misplaced key is *told* it is misplaced -
silently ignoring a key looks exactly like it worked.

**`provider` is CLI-scoped, amending ADR 0015.** That ADR filed "which
backend" under connection config, shared at `STORIX_*`. Practice showed
the split is finer than "connection vs UX": *how* to connect (credentials,
account names, base directories) is genuinely shared, but *which provider
I explore by default* is a habit of the operator, not of the code. Forcing
it through the shared `STORIX_PROVIDER` drags a service's library sessions
onto whatever the human likes to browse - the exact coupling ADR 0015
wanted to avoid, pointed the other way. So `provider` lives in
`[tool.storix.cli]`, overriding `STORIX_PROVIDER` for the CLI only, with
`-p/--provider` still winning. Credentials stay shared: the rule becomes
"how to connect is shared, which one sx opens is the CLI's".

**`dir_contents`** exists because a flat listing cannot know whether a
directory is empty, and an icon that implies either way is a lie. Looking
costs one listing per subdirectory (a round trip each on object stores;
measured at 21 listings for a 20-directory `ls`, versus 1). Default on -
accuracy is the point of the icons, and a cache layer absorbs repeats -
with the knob for anyone who would rather have the single request.

**The `[[cli.layers]]` stack** is an ordered array of
`{name = ..., **options}` entries, innermost first (the last entry is
outermost). Names resolve through a curated builder table - `cache`
(options: `ttl`, `max_bytes`; same metadata+du+bounded-read stack as
`--cache`) and `sandbox` (`root`) - not arbitrary import paths: the CLI
stays a curated surface (ADR 0015), and a config file that can import
anything is an execution vector. An unknown name or bad option exits
with the known set named.

**Flags replace, never merge.** An invocation passing `--cache` or
`--sandbox` gets exactly the flag stack; the configured stack applies
otherwise. Merging the two would make the effective stack unknowable
from either source alone.

Rejected: registering config layers through a public registry mirroring
`register_backend` (no third-party CLI layers exist to register; add the
registry when one does), and layer config in the library path
(`get_storage` stays explicit and surprise-free, per ADR 0015).

## Consequences

`sx` sessions can carry a personal always-on cache against cloud
providers and per-user display preferences, with one predictable
precedence chain; the ADR 0015 anti-confusion rule survives intact
(backend config shared, layer stack CLI-scoped). The curated builder
table means new configurable layers are a deliberate decision, not a
side effect. Remaining from ADR 0015's deferral, still open: persistent
cache stores (`store=` a cashews URL / disk-backed `CacheStore`) so
one-shot invocations benefit across processes - that needs the
cross-process staleness answer first (ADR 0014).

0.4.3 (backward-compatible feature -> patch).
