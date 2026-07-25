# 31. Standalone sx: installation, unified configuration, profiles, updates

Status: accepted

## Context

`sx` should be a professional standalone tool: `uv tool install
"storix[cli]"` (plus provider extras), a curl installer at
`https://storix.mghalix.com/install.sh`, and a CLI that discovers its
configuration without a source checkout, an editable install, or a
cwd-local `.env`.

### Reproduced behavior (v0.4.8, commit a56ae6a, clean isolated homes)

Every scenario below ran with a fresh `HOME`, fresh `XDG_CONFIG_HOME`,
isolated `UV_TOOL_DIR`, no `STORIX_*` variables, and `sx` invoked from
directories outside any checkout.

What already works:

- The wheel and sdist are clean: the `storix` package tree plus
  `py.typed` only; no `website/`, `docs/`, or `tests/` leakage.
- `uv tool install` succeeds from the local wheel, from the sdist, and
  from real PyPI, for `[cli]`, `[cli,azure]`, `[cli,s3]`, `[cli,gcs]`,
  and `[all]`. The installed `sx` runs correctly outside the checkout.
- `.env` (`STORIX_LOCAL_BASE=.`), `pyproject.toml [tool.storix.cli]`,
  the XDG user file, and `.storix.toml` are all honored for CLI
  preferences, with the documented precedence.
- `import storix` creates no files; `~/.storix` appears only when a
  local-backend operation actually runs.
- uv's `uv-receipt.toml` records the requested extras and source, so a
  package-manager-driven self-update can preserve extras.

The verdict on `uv tool install`: correct but undocumented, and
incomplete for configuration discovery.

The gaps:

1. `zensical==0.0.50`, the documentation site generator, is an
   unconditional runtime dependency. It and its 9 transitive packages
   are 10 of the 22 packages (roughly 45 percent) of a bare `storix`
   install, pulled from PyPI on every install. It is used only by the
   `just docs` recipes. **Closed ahead of this ADR**: the dependency
   moved to the `dev` group in #44 (merged after 0.4.9, so it reaches
   users in the next release), which also removed the
   unused `mkdocs` and added an automation test pinning
   `[project].dependencies` so the next tool cannot wander in.
2. `sx --version` does not exist (`Error: No such option: --version`).
3. Non-secret provider coordinates cannot come from flags or TOML:
   `sx -p local --base .` fails (`No such option`), and per ADR 0015 /
   0022 a `[local] base = "."` table in `storix.toml` is connection
   config that TOML deliberately does not carry. Users must export
   `STORIX_LOCAL_BASE=.` or write a `.env`.
4. The misplaced-key protection is inconsistent: `base` inside an
   explicit `[cli]` table exits with the documented pointer to
   `STORIX_LOCAL_BASE`, but the same intent expressed as a top-level
   `base` key or a `[local]` table is silently dropped: no error, no
   effect. Silently ignoring a key looks exactly like it worked.
5. Requesting a provider whose extra is missing (`sx -p s3` without
   `storix[s3]`) dumps a full Rich traceback ending in `ImportError: s3
   extra not installed. Install it by running 'uv add storix[s3]'`.
   The remedy assumes a project context; a `uv tool install` user needs
   `uv tool install "storix[cli,s3]"`. The `cli` missing-extra guard
   has the same wrong-context remedy (one line, at least).
6. There are no profiles, no environment overlays, no `sx config`, no
   `sx update`, no installer script, and none of it is documented.
7. `sx -p local .` fails (`No such command '.'`), and the intended
   meaning of a trailing path is ambiguous (local base? initial cwd
   inside the backend?).

### Relation to prior ADRs

- ADR 0009 fixed the factory contract: `STORIX_*` env plus `.env`,
  overrides beat env, zero config lands at `~/.storix`, never silently
  the cwd.
- ADR 0015 and 0022 scoped TOML to CLI preferences and kept "how to
  connect" exclusively in the shared env. This ADR amends that scoping
  rule: practice showed non-secret provider coordinates (bucket,
  container, account name, region, endpoint, base, root) are project
  facts that belong in project files; only secrets stay out.
- ADR 0021 governs the version bumps recorded in the staging plan.

## Decision

The scope splits into fourteen decisions and six staged pull requests.
The unifying rule: configuration loading, profiles, and provenance live
in the library (`storix.config`), because `sx` is a driving adapter and
must not grow core logic; `sx` contributes only flags, presentation,
and the commands themselves.

### D1. Packaging: zensical leaves the runtime dependencies

`zensical==0.0.50` moves from `[project].dependencies` to the `dev`
dependency group, where the `just docs` recipes
(`uv run --project .. --no-sync zensical ...`) still find it. A bare
`storix` install drops from 22 packages to 12. No public API changes;
published versions are immutable, so every release up to 0.4.9 keeps
the bloat.

Shipped in #44 ahead of the rest of this ADR, together with the removal
of `mkdocs` (referenced nowhere) and an automation test that pins
`[project].dependencies` to the library's own extras.

### D2. Supported installation methods

The documented installation matrix:

```
uv tool install "storix[cli]"                 # sx, local backend only
uv tool install "storix[cli,azure]"           # + both Azure backends
uv tool install "storix[cli,s3]"              # + S3/R2/MinIO
uv tool install "storix[cli,gcs]"             # + GCS
uv tool install "storix[cli,azure,s3,gcs]"
uv tool install "storix[all]"                 # everything
curl -LsSf https://storix.mghalix.com/install.sh | sh
pip install "storix[cli]"                     # library-context install
```

Extras stay as defined in `pyproject.toml` (`core` and `local` compose
the base; `azure` composes `azadls`+`azblob`; `r2`/`minio` alias `s3`;
`all` composes everything including `cli`). The `sx` entry point stays
unconditional; its runtime guard for a missing `cli` extra is the
correct design (an entry point cannot be conditional on an extra) and
its remedy text becomes context-aware per D7. The curl installer (D13)
is a thin wrapper over `uv tool install`.

### D3. One configuration loader, shared by library and CLI

Non-secret provider settings become legal in TOML. One loader in
`storix.config` discovers files, merges sources, validates through the
existing per-provider pydantic-settings models (no schema duplication),
and records provenance (which source supplied each effective field) so
diagnostics can explain themselves.

Canonical files:

```
~/.config/storix/config.toml      # user scope (XDG_CONFIG_HOME honored)
%APPDATA%\storix\config.toml      # user scope on Windows
storix.toml                       # project scope, standalone
pyproject.toml -> [tool.storix]   # project scope, namespaced
```

The user scope follows the platform: `%APPDATA%` on Windows (falling
back to `~/AppData/Roaming` when it is unset), `~/.config` elsewhere.
`XDG_CONFIG_HOME` overrides both, including on Windows, because a user
who exports it means it.

`.storix.toml` is retained as a compatibility-only read alias of
`storix.toml` (same directory: `storix.toml` wins, as today). It is
documented as compatibility-only; `sx config` write operations never
target it. Project discovery keeps the ruff-style upward walk from cwd;
the first directory holding any of the three files anchors the project
and stops the walk.

Top-level schema of a project `storix.toml` (identical under
`[tool.storix]` in `pyproject.toml`, and in the XDG user file):

```toml
provider = "s3"          # default provider
profile = "media"        # optional default profile (D8)

[local]
base = "."

[s3]
bucket = "media"
region = "auto"
endpoint = "https://ACCOUNT_ID.r2.cloudflarestorage.com"
root = "/"

[azure]
kind = "auto"
account_name = "example"
container = "media"

[gcs]
bucket = "media"

[cli]                    # CLI-only preferences, unchanged model
icons = true

[cli.alias]
l = "ls -l"

[profiles.NAME]          # D8
```

Provider tables validate against the canonical models with unknown
fields forbidden: an unknown key or unknown top-level table exits
naming the file, the key, and the known set. This replaces gap 4's
silent drop; the `_MISPLACED` redirect inside `[cli]` is retired
because the keys it redirected now have a legal home in the provider
tables. Canonical alias spelling is `[cli.alias]`; top-level `[alias]`
and `[aliases]` remain accepted compatibility spellings.

Precedence, strongest first (`sx`; the library substitutes explicit
`get_storage()` keyword arguments for row 1 and ignores rows marked
CLI-only):

```
1. CLI flags and --set                (CLI-only)
2. Selected environment overlay      (D9)
3. Selected profile                  (D8)
4. Process environment STORIX_*
5. Project .env (cwd, via pydantic-settings, unchanged)
6. Nearest project TOML (storix.toml > .storix.toml > pyproject [tool.storix])
7. XDG user config.toml
8. Built-in defaults
```

Profile values beat the process environment deliberately: a profile is
an explicit per-invocation selection, and a leftover exported
`STORIX_AZURE_CONTAINER` must not silently corrupt `sx --profile media`.
Explicit beats ambient; ambient env still beats files, as today.

Relative path rules (for `local.base`, `gcs.credential_path`, and any
future path field):

- CLI flag or `--set`: resolved against the invocation cwd.
- Project TOML: resolved against the directory containing the file,
  so `base = "."` means "this project", not "whichever subdirectory
  ran sx".
- Environment and `.env`: resolved against the process cwd (unchanged
  current behavior); `~` expands everywhere.
- XDG user file: relative paths are rejected with an error; a
  user-global default of `"."` is meaningless. Absolute and
  `~`-prefixed paths only.

### D4. Secrets policy

Secret fields are marked in the canonical models: `azure.credential`,
`s3.access_key_id`, `s3.secret_access_key`, `gcs.credential`. The
policy:

- Literal secrets in project-scope files (`storix.toml`,
  `.storix.toml`, `pyproject.toml`) are rejected with an error naming
  the field and the safe alternatives. Project files get committed.
- Secret fields in any TOML scope may hold an environment reference:
  `credential = "env:MEDIA_AZURE_CREDENTIAL"` resolves from the process
  environment at load time; a missing variable is an error naming the
  variable and the file. This is the mechanism that lets two profiles
  on the same backend carry different credentials.
- The XDG user file may hold literal secrets; the loader warns when
  the file is group- or world-readable, and files created by `sx
  config` get mode 600.
- Standard provider chains (AWS credential chain, Azure identity, GCP
  application default credentials) remain first-class: every secret
  field stays optional exactly as today.
- Redaction: secret fields render as `***` in `sx config show`,
  provenance output, error messages, and doctor output. No new secret
  flags exist on the CLI (D5), and no OS keyring or external secret
  manager integration is added (deferred; no demonstrated need).

### D5. CLI overrides for non-secret provider settings

Two mechanisms, both CLI-only, both validated through the canonical
models, both strongest in precedence:

- Direct flags on the root command for the common coordinates:
  `--base` (local), `--bucket`, `--container`, `--account-name`,
  `--region`, `--endpoint`, `--root`, `--kind`. A flag that does not
  belong to the effective provider exits naming the provider and its
  accepted flags; flags for one provider never silently affect
  another.
- A repeatable structured override for the tail:
  `--set <provider>.<field>=<value>` (for example
  `--set azure.read_chunk_size=1048576`). Values parse type-aware
  through pydantic; unknown fields fail naming the known set.

`--set` of a secret field is refused, pointing at the environment and
`env:` references; secrets do not belong in shell history. The
reported shorthand `sx -p local .` is rejected: a trailing path is
ambiguous between "local base" and "initial cwd inside the backend",
and `sx -p local --base .` is one flag away. Recorded as rejected, not
deferred.

### D6. `sx --version`

An eager `--version` option prints `sx <importlib.metadata
version("storix")>` and exits, importing no provider code and building
no backend. (`storix.__version__` does not exist and is not added; the
metadata lookup is the single source of truth.)

### D7. Missing-extra and configuration diagnostics

Provider construction failures stop dumping Rich tracebacks: the CLI
entry catches `ImportError` and `ConfigurationError` alongside the
existing `StorageError` family and prints one actionable line
(`--traceback` still reveals everything). The remedy text becomes
context-aware: when `sx` runs from a uv tool environment (detected via
the adjacent `uv-receipt.toml`), missing-extra messages suggest
`uv tool install "storix[cli,s3]"`; otherwise they suggest
`pip install "storix[s3]"` with the `uv add` form as the project
alternative. The `cli`-extra guard in `storix/cli/__init__.py` gets
the same context-aware remedy.

### D8. Named profiles

A profile is a named, complete connection selection: provider plus
provider config plus optional environment overlays. Profiles reuse the
canonical provider models; the profile parser owns no field schema.

```toml
[profiles.media]
provider = "azure"
default_environment = "dev"
kind = "auto"
account_name = "mediaaccount"
credential = "env:MEDIA_AZURE_CREDENTIAL"

[profiles.media.environments.dev]
container = "media-dev"

[profiles.media.environments.prod]
container = "media-prod"

[profiles.archive]
provider = "azure"
kind = "adls"
account_name = "archiveaccount"
credential = "env:ARCHIVE_AZURE_CREDENTIAL"
```

**Amended during implementation.** The first draft nested the settings
under a provider-named sub-table
(`[profiles.NAME.<provider>]`, `[profiles.NAME.environments.ENV.<provider>]`).
A profile names exactly one provider, so repeating it in every table was
ceremony, and worse: a table for a *second* provider inside a profile was
silently ignored, which is the class of silent config this ADR exists to
remove. Settings now sit directly in the profile and in each overlay, and a
key that is not a setting of the profile's provider is an error naming the
provider and its fields. `provider`, `default_environment`, and
`environments` are the profile's own reserved keys.

Rules:

- Profiles live in project scope, user scope, or both. A project
  profile shadows a user profile of the same name wholly (no
  cross-scope field merging; the effective profile is readable from
  one file).
- Names match `[A-Za-z0-9][A-Za-z0-9._-]*`. An unknown profile errors
  listing the available names and their source files.
- Selection: `sx --profile NAME`, or `STORIX_PROFILE`, or a top-level
  `profile = "NAME"` key in a config file. Flag beats env beats file.
  All three are `sx` only.
- A selected profile supplies the provider. `--profile` and a `-p`
  naming a different one is an error: the user said two things. A
  profile that is only *pinned* is a default, so `-p` steps off it
  rather than being refused; a pin that could veto `-p` would make one
  line in a personal file a lock on the whole CLI.
- The library selects a profile only when the call asks:
  `get_storage(profile=..., environment=...)`, through the same loader.
  Neither `STORIX_PROFILE` nor a pinned `profile` key reaches it. An
  operator's shell habit must not redirect a service's sessions (the
  ADR 0022 provider argument, same direction), and a pin that did would
  break `get_storage('s3')` beside `get_storage('azure')` - the shape
  every migration and every composite filesystem takes - on whichever
  machine happened to carry one. The convenience belongs where the
  human is.
- A profile layers over that provider's own table, so settings shared
  by every profile on a backend are written once under `[s3]` and each
  profile carries only what distinguishes it. This is why unrelated
  buckets are separate profiles rather than stages of one: a stage
  names a deployment, and `default_environment = "media"` would not.
- No profile inheritance (deferred until a real need appears; no
  inheritance means no cycle detection).
- Profile fields beyond provider config (default CLI layers, default
  cwd) are deferred.

### D9. Environment (stage) overlays

`[profiles.NAME.environments.ENV.<provider>]` overrides selected
fields of the profile's provider config; the overlay reuses the same
canonical model in partial form. An overlay cannot switch the
provider: stages of one logical profile share a backend kind by
definition, and letting `dev` silently point at a different provider
family invites credential cross-wiring.

Selection: `--environment` with `--env` as the documented alias, or
`STORIX_ENVIRONMENT` (`sx` only), else the profile's own
`default_environment` when it names one. `--env` without a selected
profile is an error; an unknown environment (selected or defaulted)
errors listing the profile's available environments. No environment
selected and no default means no overlay, the profile's base config
applies.

**Amended during implementation.** `default_environment` was listed as
deferred; a profile whose stages are the point ("I am nearly always on
dev") makes typing `--env dev` every time the norm rather than the
exception, so it lands here. It is validated against the profile's own
stages when the file is read. Internally and in documentation the
term is "environment" (docs say "environment (stage) overlays" once to
disambiguate from process environment variables; CacheLayer's
unrelated `environment` namespace option keeps its name).

### D10. `sx config` commands

Accepted subset, each solving a concrete problem:

```
sx config path                   # which files exist / would be used
sx config sources                # discovered files + precedence explanation
sx config show [--effective]     # merged view; --effective adds provenance
sx config get KEY [--effective]  # e.g. s3.bucket, cli.icons
sx config set KEY VALUE [--scope user|project]
sx config unset KEY [--scope user|project]
sx config init [--scope user|project] [--force]
sx config validate               # names file and exact invalid field
sx config edit [--scope user|project]   # $VISUAL then $EDITOR
sx config profiles               # list profiles + their environments + source
```

Every scope-taking command also accepts `--user` as a shorthand for
`--scope user`, since reaching for the machine-wide file is the common
deviation from the project default.

`--effective` answers "what will storix actually do", not "what is
written down": it resolves the selected profile and environment, prints
the provider in force and every field with its value, its readable size
where the field is a size, and the layer that supplied it (default,
user, project, profile, environment, environment variable, flag).
Without a value in the output the provenance is unreadable, and a user
cannot discover a default they never wrote; `sx config get --effective
azure.read_prefetch_size` is the single-key form of the same question.

Two rules make these views trustworthy rather than merely present.

Every view reports the selection this invocation made, flags included.
The root callback resolves `--profile` / `--env` once and records the
answer; a command that re-resolves sees only what it was passed, so it
reports the pinned profile while the session runs the named one. That
disagreement reads as "the flag did nothing", which is worse than no
view at all.

Reading configuration never resolves a credential. Naming the backend a
profile declares is a question about the file; opening it is a question
about secrets. Keeping them apart is what lets `sx config` and `sx
doctor` answer while an `env:` reference is unresolvable, which is when
they are reached for. For the same reason `doctor` reports an
importable extra as installed, not as ready: nothing there opens a
connection, and a word implying one is a diagnosis storix has not made.

Profiles print as a table, a stage as a row under its profile, because
dotted keys flatten the thing users reach for most into the least
readable shape (`profiles.NAME.environments.STAGE.account_name`).

Rules: two scopes only (`user`, `project`). Project scope writes the
nearest existing `storix.toml`; else a `pyproject.toml` already
carrying `[tool.storix]`; else it creates `./storix.toml` and says so.
The target file is always printed. Writes go through `tomlkit`
(round-trip, comment-preserving; new dependency of the `cli` extra
only), validate through the canonical models before committing,
refuse unknown keys, parse values type-aware, and land atomically
(temp file + rename, preserving mode; user-scope files created 600).
`init` writes a commented skeleton and never overwrites without
`--force`. Secret values are redacted in all read commands; `set` of a
secret field in project scope is refused (D4); in user scope it warns
and tightens permissions. No separate `sx profile` command group:
profiles are listed by `config profiles`, inspected by `config show`,
selected by `--profile`, and edited by `config set` (smallest surface
that makes them discoverable, inspectable, selectable, and safely
editable).

### D11. `sx update`

Package-manager-driven, never self-modifying. Surface:

```
sx update            # upgrade via the installing package manager
sx update --check    # report current vs latest, change nothing
```

Behavior: detect a uv tool installation by locating `uv-receipt.toml`
adjacent to the running environment. If found, run `uv tool upgrade
storix` as a plain argv subprocess (no shell), printing the command
first; uv's receipt preserves the originally requested extras
(verified in reproduction), so extras survive without a storix-side
manifest and no installation state file is needed. If the environment
is an editable checkout, a plain venv, or otherwise not a uv tool
install, print the exact manual command for that context and exit 2.
`--check` compares the installed version against the latest release on
PyPI (one metadata request) and exits 0 (network-touching, excluded
from the default unit suite; unit tests use a fake runner seam).
`--version X` and `--prerelease` are deferred: `uv tool install
"storix[...]==X"` is the documented manual path until a need appears.
The command never touches configuration or credentials. The exact uv
subcommand is verified against current uv documentation at
implementation time, not from memory.

### D12. `sx doctor`

Lands with D11 and only reuses existing introspection: installed
version (D6 path), installation method (D11 detection), Python
version, importable provider extras, discovered config files and
selected profile/environment with provenance (D3), effective provider
and its missing required fields, credential source type without
values, file-permission warnings (D4), and editor availability for
`config edit`. Update availability only via `sx doctor --updates`
(explicit network). No logic exists only for doctor; it is a
presentation of loader and updater APIs.

### D13. The standalone installer

Single source: `website/docs/install.sh`, copied verbatim by the
Zensical build into the site root and therefore served raw at
`https://storix.mghalix.com/install.sh` (stable URL, no HTML wrapper;
raw serving, headers, and `curl | sh` are verified against the built
site and the deployed site). Interface:

```
curl -LsSf https://storix.mghalix.com/install.sh | sh
curl -LsSf https://storix.mghalix.com/install.sh | sh -s -- --with azure,s3
curl -LsSf https://storix.mghalix.com/install.sh | sh -s -- --all
curl -LsSf https://storix.mghalix.com/install.sh | sh -s -- --version 0.5.0
curl -LsSf https://storix.mghalix.com/install.sh | sh -s -- --help
```

Requirements: POSIX sh with `set -eu`, ShellCheck-clean (enforced by
an automation test), no root, no credentials, no config creation, no
shell startup-file edits. With uv present it runs `uv tool install
--force "storix[cli,<extras>]"` (idempotent reruns, upgrade on rerun);
without uv it bootstraps via the official installer
(`https://astral.sh/uv/install.sh`) after announcing it. PATH is not
modified: the script prints where `sx` landed and how to add it
(mentioning `uv tool update-shell`) when it is not on PATH.
Non-interactive throughout (it runs piped). Uninstall is documented:
`uv tool uninstall storix`. The download-inspect-execute alternative
is documented next to the one-liner. The installer and `sx update`
share one model: uv tool is the installation mechanism, the receipt is
the state.

A second script, `website/docs/install.ps1`, serves Windows over the
same model and is published the same way:

```powershell
powershell -c "irm https://storix.mghalix.com/install.ps1 | iex"
& ([scriptblock]::Create((irm https://storix.mghalix.com/install.ps1))) -With azure,s3
```

It was originally deferred, and that was wrong for a tool whose
promise is one command on any machine: telling a Windows user to first
install uv, then compose an extras string by hand, is a worse first
five minutes than the one every other platform gets. Same
requirements, same options (`-With`, `-All`, `-Version`, `-Help`),
same refusal to touch PATH, credentials, or configuration. Both
scripts are executed for real in CI on their own operating system,
each followed by running the installed `sx`, so a broken installer
fails the merge rather than a user's first command. That check runs
the published release, so it asserts only that `sx` starts: an
unreleased flag would test this branch, not the installer.

### D14. CLI local default becomes the invocation cwd

When the effective provider is `local` and no base was supplied by any
source (no flag, `--set`, profile, environment variable, `.env`, or
TOML value), `sx` anchors at the invocation cwd instead of
`~/.storix`. A unix user running an exploration CLI expects `sx ls` to
list where they stand, exactly like `ls`. The library default is
untouched: ADR 0009's "zero config lands at `~/.storix`, never
silently the cwd" remains the library contract, because library code
writing to an application's cwd is a hazard, while a human at a
prompt is the one case where cwd is the honest default. Explicit
configuration always wins; only the nothing-configured case changes.

This is observable behavior today (`sx` with zero config reads and
writes `~/.storix`), so per ADR 0021 it ships in a pre-1.0 MINOR
release, last in the staging plan, with release notes and a
documentation callout. No deprecation period or compatibility flag: a
zero-config default flip is cleanly describable, and a flag would
outlive its usefulness.

## Staging

Six pull requests, one architectural direction, each independently
reviewable and releasable. Versioning per ADR 0021 (0.x shift-down).

```
PR 1  feat(config): unified configuration sources and CLI overrides
      D1 packaging fix, D3 loader + precedence + provenance,
      D4 secrets policy, D5 flags + --set, D6 --version,
      D7 diagnostics. Docs: installation (uv tool matrix), CLI guide,
      settings recipe. PATCH.
PR 2  feat(config): named profiles and environment overlays
      D8, D9, get_storage(profile=, environment=). PATCH.
PR 3  feat(cli): config introspection and manipulation commands
      D10, tomlkit. PATCH.
PR 4  docs(site): standalone installer at /install.sh
      D13 + install.ps1 + install/uninstall docs + ShellCheck
      automation test + a CI job that really runs each script on its
      own OS. Website asset, no package change; `documentation` label.
PR 5  feat(cli): sx update and sx doctor
      D11, D12. PATCH.
PR 6  feat(cli)!: local sessions default to the invocation cwd
      D14. MINOR.
```

Compatibility notes recorded intentionally:

- PR 1 turns two silent behaviors into defined ones: a provider table
  in project TOML was silently ignored and now takes effect, and an
  unknown key/table now errors instead of being dropped. Both follow
  the ADR 0022 precedent (silent config is treated as a bug, and
  making it speak is a backward-compatible fix): PATCH, called out in
  release notes.
- PR 1 removes a runtime dependency (zensical); dependency removal is
  not an API change: PATCH.
- PR 6 changes an observable default: MINOR, as decided in D14.

## Rejected and deferred

Rejected:

- `sx -p local .` trailing-path shorthand (ambiguous; `--base .` is
  the contract).
- Secret-bearing CLI flags (shell history).
- Environment overlays switching the provider.
- A storix-side installation manifest for update (uv's receipt already
  holds the extras; duplicating state invites drift).
- Renaming the XDG file to `~/.config/storix/storix.toml` (the
  directory is the namespace).

Deferred, revisit on demonstrated need:

- Profile inheritance (and with it, cycle detection).
- Profile-scoped CLI layers and default cwd.
- `sx update --version` / `--prerelease` flags.
- A `sx profile` command group beyond `config profiles`.
- OS keyring / external secret manager integration.
- Connection URI factory (already deferred by ADR 0009).

## Consequences

A globally installed `sx` becomes self-sufficient: install through uv
tool or one audited script, configure through three canonical TOML
files with one documented precedence chain, switch accounts through
profiles and stages through overlays, and introspect all of it with
provenance. The library and CLI read the same provider sections
through one loader, so semantics cannot drift between front-ends. The
base install sheds the documentation toolchain. Secrets have exactly
three sanctioned homes (env, `env:` references, guarded user file)
and zero new leak surfaces. Update and install share uv's receipt as
the single installation state. The cost: TOML that yesterday was
inert now acts (announced, PATCH), and the zero-config `sx` anchor
moves to cwd in a MINOR release at the end of the sequence.
