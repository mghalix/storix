# AGENTS.md

Guidance for AI agents (Claude Code and others) working in this repository.
CLAUDE.md is a symlink to this file.

## The one rule that matters: async is the source of truth

storix is async-first. The sync flavor under `src/storix/_sync/` (and each
test `_sync/` twin) is GENERATED from `src/storix/_async/` (and each `_async/`)
by `scripts/unasync.py` (token substitution: `async def` -> `def`, `await ` ->
"", `storix._async` -> `storix._sync`, and so on). The generated test trees are
`tests/unit/_sync/` (from `tests/unit/_async/`) and `tests/conformance/_sync/`
(from `tests/conformance/_async/`).

- Edit only the `_async` trees. Never edit `_sync/` by hand.
- After any change under `_async`, regenerate:
  `uv run --no-sync python scripts/unasync.py` (or `just gen`).
- The codegen and CI fail if the committed `_sync` tree drifts
  (`uv run --no-sync python scripts/unasync.py --check`).
- Hand-written twins that are NOT generated: `_compat.py`, `local.py`,
  `azure.py`, `opendal.py`, `test_compat.py`. Edit BOTH flavors by hand, and
  expect `--check` to stay silent about them, because the generator never
  writes them.

  This is not a gap in `scripts/unasync.py`. Token substitution renames
  `async def` and drops `await`; it cannot rewrite one library's API into
  another's, and these files call genuinely different libraries per flavor:
  `aiofiles.open` against `open`, `opendal.AsyncOperator` against
  `opendal.Operator`, the `azure.storage.filedatalake.aio` client against its
  sync counterpart. Their bodies differ in shape, not only in keywords (a sync
  write is `handle.writelines(chunks)` where the async one awaits per chunk),
  so generating them would mean maintaining a transpiler for five files
  instead of maintaining ten files. The `FORBIDDEN` scan enforces the split
  from the other side: an `aiofiles` or `asyncio` token in a generated file
  fails the build rather than emitting silently wrong sync code.

  `SKIP_NAMES` in `scripts/unasync.py` is the authority, and a test in
  `tests/automation/test_workflow_contracts.py` fails when this list drifts
  from it. A stale list is the dangerous kind of wrong: an agent edits only
  the async flavor, `--check` reports no drift because nothing is generated,
  and the sync twin is quietly incorrect.

## Commands

- `uv sync --locked --all-extras --all-groups` install the reviewed toolchain
- `uv run --no-sync python scripts/unasync.py` regenerate the sync tree (or `just gen`)
- `uv run pytest tests/unit/_async/test_layers.py -k without_layer` run one test
- `just test-unit` run local unit and conformance tests with branch coverage
- `just test-integration` run credentialed provider tests
- `just test-automation` run release and workflow contract tests
- `just typing` run strict BasedPyright and mypy checks
- `just dead-code` scan at 100 percent confidence
- `just audit-actions` audit workflows offline with Zizmor
- `just hooks` install the repository-managed commit message hook
- `just hooks-check` validate and run every applicable hook
- `just check` run the complete source and automation gate
- `just release-check` run the side-effect-free release candidate gate
- `just build` build the wheel and sdist with `uv build --no-sources`
- `just smoke` install and test both artifacts in fresh environments

Integration tests are opt-in; the default pytest config deselects them
(`-m 'not integration'`). Run `just` to list the verification-only recipes.
No local recipe changes a version, creates a tag, pushes, publishes, or creates
a release.

Test responsibilities stay separate:

- Library and conformance tests cover behavior in both generated flavors.
- Credentialed integration tests cover real optional providers.
- `tests/automation/` covers repository and release tooling.
- `tests/typing/` contains static typing fixtures, not Pytest tests.
- `tests/smoke/` contains plain consumers of built artifacts.

Artifact smoke tests install the exact wheel or sdist in a fresh temporary
environment, run outside the checkout, clear inherited Python environment
state, and use `--refresh`. Keep a core scenario, every meaningful extra, and
the missing-extra message contract. Editable installs are not packaging tests.

## Git workflow: areas, branches, worktrees, commits, pull requests

`main` is the only permanent in-repository branch. Contributors and
maintainers create short-lived topic branches from an up-to-date `main` and
open pull requests directly back to `main`. Do not create or recreate `dev`,
`develop`, staging, or another long-lived integration branch. Do not route
topic branches through an intermediate branch.

The repository accepts squash merges only, and the validated pull request
title becomes the Conventional Commit on `main`. Do not merge `main` into a
topic branch to satisfy strict checks; rebase it onto `origin/main`.

### Three areas name every change

`core`, `cli`, and `repo` are the areas, and the same three words are reused by
branch names, commit scopes, pull request titles, and labels:

- `core` the library: the `_async` source of truth and its generated `_sync`
  twin, backends, layers, capabilities, config, errors.
- `cli` the driving adapters over the core: `sx` (`cli/app.py`) and the REPL
  (`cli/shell.py`).
- `repo` repository-wide work: CI, packaging, release automation, dependency
  maintenance, development tooling, and agent guidance.

### Core and CLI changes are separate pull requests

Core and CLI behavioral changes must be independently reviewable, so a task
that needs both is split into two pull requests, core first:

```text
feat/core/progress-events
-> core PR labeled `core`
-> merge into the default branch
-> update the local default branch
-> create feat/cli/progress-output from it
-> CLI PR labeled `cli`
```

- The core change lands first, in its own branch and pull request. Create the
  CLI branch only after the core pull request has merged, from the updated
  default branch.
- The CLI pull request contains only CLI-specific changes.
- A behavioral pull request must not contain both core and CLI changes, and must
  not carry both the `core` and `cli` labels. If it does, split it.
- This holds even when the core API change exists solely to serve the CLI
  feature. That is the common case, not an exception (see "The core boundary").
- Do not create a stacked CLI branch or a stacked CLI pull request unless the
  maintainer explicitly asks for one.
- Repository-wide mechanical work (CI, packaging, release automation,
  dependencies, tooling) is not split artificially. It is one `repo` change
  unless it also changes core or CLI behavior.

### Branch naming

```text
<type>/<area>/<kebab-case-description>
```

Type is the Conventional Commit vocabulary: `feat`, `fix`, `refactor`, `perf`,
`docs`, `test`, `build`, `ci`, `chore`. Area is `core`, `cli`, or `repo`.

```text
feat/core/progress-events
feat/cli/progress-output
fix/core/path-resolution
fix/cli/cd-command
docs/cli/command-reference
ci/repo/release-workflow
chore/repo/dependencies
```

Lowercase and kebab-case throughout. No usernames, agent names, timestamps, or
other arbitrary identifiers, and no vague description such as `fix/stuff`. The
exception is workflow-owned `release/vX.Y.Z...` (see "Releasing").

### Worktree location and naming

A linked worktree lives outside the main checkout, under a per-repository
directory beside it:

```text
<workspace>/.worktrees/<repository>/<worktree-name>
```

So when the storix checkout is `<workspace>/storix`, its worktrees are in
`<workspace>/.worktrees/storix/`. The worktree name is the complete branch name
with every `/` replaced by `-`:

```text
feat/core/progress-events -> <workspace>/.worktrees/storix/feat-core-progress-events
feat/cli/progress-output  -> <workspace>/.worktrees/storix/feat-cli-progress-output
```

Keep that directory flat. Do not add `core/` or `cli/` subdirectories; the
branch already names the area, and `feat-core-*` and `feat-cli-*` sort together
on their own.

Never create a worktree inside the checkout (for example under `.claude/`). A
nested worktree is a second full checkout that repository-wide tooling walks:
`./scripts/clean` recurses from the checkout root, and test and lint collection
would see duplicate trees.

Before adding a worktree, check `git worktree list` for the branch and reuse the
existing worktree when it is appropriate. Manage the lifecycle with
`git worktree add`, `git worktree move`, `git worktree remove`, and
`git worktree prune`. Do not move or delete a registered worktree by hand when a
`git worktree` command does it.

### Commit messages

Every commit follows Conventional Commits (`cz check` enforces it through the
commit-msg hook; see `just hooks`). The scope is the stable high-level area:

```text
feat(core): add progress event protocol
test(core): cover streaming progress events
feat(cli): render transfer progress
fix(cli): handle previous-directory navigation
docs(cli): document the cd command
ci(repo): validate release artifacts
```

Never nest a subsystem into the scope (`feat(cli/render):`, `feat(core/cd):`).
The subsystem, command, or behavior belongs in the description:
`feat(cli): add rich progress rendering`, not `feat(cli/render): add progress`.

Keep commits atomic, and keep each commit inside the area its scope names.

### Pull requests

The title is a Conventional Commit with the same high-level scope, because it
becomes the commit on `main`:

```text
feat(core): add progress events
feat(cli): render transfer progress
ci(repo): validate release artifacts
```

Apply the area label that matches: `core` for core changes, `cli` for CLI
changes, `repo` for repository-wide maintenance. The area label is orthogonal to
the release-note label below, so a pull request carries one of each. Do not
create a new label unless the maintainer asks.

### Pull request body: authorship and tone

A pull request is a permanent public project artifact. It reads as though the
maintainer wrote it, and it is self-contained: a future contributor with no
access to the session that produced it gets the complete picture from the body
alone.

- Never mention agents, AI, prompts, instructions, terminal sessions,
  conversations, or delegated work, and never imply that an agent produced the
  implementation or the description.
- Never address the reader directly. No `you`, `your`, `for you`, or
  `I need your decision`.
- Do not continue the terminal conversation in the body. It is not a reply to
  anyone.
- No conversational or agent-oriented headings: `Decisions worth your
  attention`, `What I need from you`, `Notes for the maintainer`, `What I
  decided`, `Things you should review`.
- No process commentary: why an approach was chosen over what an agent first
  tried, which instructions were followed, what is left for someone to decide,
  what comes next in the session.
- State design choices neutrally, as project decisions, tradeoffs, constraints,
  or implementation details.
- Concise, professional, repository-facing tone. No speculation,
  self-congratulation, or narrative. The marketing and maturity rules in
  "Public communication & feature standards" apply to pull request bodies too.

`.github/PULL_REQUEST_TEMPLATE.md` ships the section set below. Fill the
sections that carry real information and delete the rest; `Design decisions` and
`Breaking changes` are optional by design, and no section wants a `None`:

```markdown
## Summary

## Motivation

## Changes

## Design decisions

## Testing

## Breaking changes

## Checklist
```

Write:

```markdown
## Design decisions

- Progress events are emitted by the core layer.
- Rendering remains the responsibility of CLI consumers.
- The event API remains transport-agnostic.
```

Not:

```markdown
## Decisions worth your attention

I decided to put progress events in core because I think this is what you wanted.
```

## Releasing

Versioning follows ADR 0021 (0.x shift-down): a breaking public API change
bumps the MINOR (0.4.0 -> 0.5.0); a backward-compatible feature or a bug fix
bumps the PATCH (0.4.0 -> 0.4.1). In 0.x, MINOR is the breaking-change dial.
Published versions are immutable and monotonic: never publish a version <= the
latest published one. Between releases, `[project].version` stays at the latest
published version. Do not bump the version by hand. Only the `Prepare release`
workflow in `.github/workflows/prepare-release.yml` advances it.

CI (`.github/workflows/ci.yml`) runs the supported Python matrix, default core,
optional integrations, runtime lower bounds, typing, automation, strict docs,
and isolated artifact smoke tests. Branch protection depends only on the
stable aggregate job named `Required`.

Branch, worktree, commit, and pull request mechanics are in "Git workflow"
above; only the release-specific parts are here. Branches matching
`release/vX.Y.Z...` are short-lived and workflow-owned. Only Prepare release
creates them. Automatic head-branch deletion removes them after merge; delete
an abandoned branch explicitly after its pull request closes unmerged.

Give every pull request an intentional release-note label before merge. Use
`skip-changelog` for internal-only CI, release automation, dependency,
repository-tooling, and agent-guidance changes. Use `documentation` for
user-facing docs. Before Prepare release, audit every merged pull request since
the last tag and correct missed labels directly on those pull requests.

Releases are draft-first and fully automated:

1. Dispatch `Prepare release` and choose `patch`, `minor`, or `major`.
2. The release App opens `release/vX.Y.Z...` with the version, lockfile, and
   generated notes. Curate the notes and squash-merge after `Required` passes.
3. GitHub Actions builds and smoke-tests that exact merge commit, attests one
   wheel and one sdist, then attaches them to a draft GitHub Release.
4. Review and publish the complete draft. Release immutability locks its tag
   and assets.
5. Approve the protected `pypi` environment. Trusted Publishing uploads those
   exact verified assets without rebuilding.

Draft creation is implemented by
`.github/workflows/create-draft-release.yml`. Publishing is implemented by
`.github/workflows/release.yml`.

An immutable draft may reserve `vX.Y.Z` without a visible Git tag ref. This is
expected and is not, by itself, a failed draft workflow. Publishing the
complete draft materializes the public tag and locks it with the reviewed
assets.

Before starting a release, run exactly:

```text
uv sync --locked --all-extras --all-groups
uv run coverage erase
uv run --no-sync just release-check
```

Passing this gate means the repository is ready. It does not by itself mean a
release is ready. Release readiness also requires confirmed GitHub rulesets,
squash-only merging, the `Required` status check, the `release-automation` and
`pypi` environments, GitHub App credentials, immutable releases, and the PyPI
Trusted Publisher.

While Storix has only one trusted maintainer, its explicit `pypi` transition
mode uses that maintainer as the required reviewer with prevent self-review
disabled. This preserves a deliberate manual pause but not independent
approval. Agents must report it as the weaker solo mode and confirm the remote
setting before each release. When a second trusted maintainer becomes
available, make that person a required reviewer and enable prevent self-review.

Never create a release tag manually. If draft creation fails after the release
pull request merges and before a tag or draft candidate exists, fix the
workflow through a normal pull request and use the guarded default-branch
recovery dispatch.
See `release/README.md` for setup, curation, recovery, and verification details.

When guiding a future release, an agent must:

1. Inspect the current version, latest tag or release, canonical notes, merged
   user-facing changes, release-note labels, and worktree status.
2. Recommend the bump from ADR 0021 and explain the compatibility reason.
3. Run the complete local gate. Never bypass failure with a manual tag.
4. Ask the maintainer to dispatch `Prepare release` with the chosen bump.
5. Review the generated pull request version, lockfile, notes, Conventional
   title, and `Required` result.
6. Ask the maintainer to curate the notes and squash-merge with that title.
7. Monitor draft creation and verify its proposed tag name, target commit,
   wheel, sdist, attestations, and draft state. Do not require a visible tag ref
   until publication.
8. Ask the maintainer to publish the complete draft, verify the public tag and
   immutable assets, approve `pypi`, and verify a fresh installation from real
   PyPI.

Confirm each remote setting before advancing to the next manual checkpoint.
Never infer remote release readiness from repository files alone.

## Architecture (the big picture)

Hexagonal: one core engine over one small port.

- `Storix` (`_async/core.py`) is the unix-flavored session. It owns cwd/home and
  path resolution (`~`, `..`, cwd via `pathops`) and implements every user-facing
  operation (`ls`/`cat`/`echo`/`du`/`mv`/`url`/...). It speaks only to a
  `StorageBackend`.
- `StorageBackend` (the port, about 14 methods) is what backends implement:
  - **LocalBackend**: real disk filesystem anchored at a base directory
  - **MemoryBackend**: reference backend, ideal for tests
  - **AzureBackend**: ADLS Gen2 native (HNS accounts)
  - **AzureBlobBackend**: Azure Blob Storage via OpenDAL engine
  - **S3Backend**: Amazon S3 and S3-compatible stores (R2, MinIO) via OpenDAL engine
  - **GcsBackend**: Google Cloud Storage via OpenDAL engine
  Backends do zero path logic and raise only `storix.errors`.
- Layers are backends that wrap backends (same port). Compose them with
  `Storix(be, layers=[...])`, `fs.with_layer(Layer, **kwargs)`, or
  `fs.with_layer_missing(Layer)` (native-preference, capability inferred).
  `SandboxLayer` is an escape-proof chroot, `CacheLayer` is a read-through cache,
  `ObservabilityLayer` emits transfer progress events, `DataUrlLayer` and
  `MetadataLayer` backfill capabilities, `LayerBase` is the delegating base
  for custom layers. `fs.without_layer(Layer)` / `fs.uncached` strip layers
  for one session; a `SandboxLayer` is non-removable (`removable = False`).
- Capabilities (`models.Capabilities`) gate optional features; requesting a
  missing one raises `UnsupportedOperationError` naming the capability.
- Factory: `get_storage(provider, /, **overrides)` (env-driven through `STORIX_*`
  pydantic-settings), plus `register_backend` and `available_providers`.
- CLI: `sx` (`cli/app.py`, typer) and a REPL (`cli/shell.py`) over the sync core.
- Errors: `storix.errors` is a typed taxonomy (`StorageError` base, with dual
  stdlib inheritance where it fits). Every failure raises; there are no boolean
  error returns.

Design rationale is recorded as ADRs in `docs/adr/`; the roadmap is
`docs/roadmap.md`. The public documentation site is a separate Zensical project
under `website/` (not part of the shipped package). The ports-and-adapters
framing (what is the core, the driven port, an adapter, a driving adapter) is
`docs/design/architecture.md`.

### The core boundary: interfaces never grow logic the core should own

`Storix` is the application core; `sx` (and any future front-end: a pathlike
adapter, a flat facade, an MCP server) is a driving adapter over it. A driving
adapter presents the core, it does not extend it. So when you are building an
interface and reach for something that is missing - a listing that keeps the
kind/size the port already produced, an "is this directory empty" check, a way
to read the layer stack without touching a private `_inner` - that gap is in
the core, not a thing to quietly reimplement in the interface.

Do not silently add it to the interface. Stop, and take it to the maintainer
with a proposed core change; a new ADR may be warranted (it usually is, since
it is a core-interface change). Proceed only once it is agreed. A capability
re-implemented in `sx` is a capability the next front-end re-implements again,
and core semantics that live in two places drift. The one exception is a
genuine "the core cannot express this" - state why in a comment, as
`_sandboxed` does for constructor-time I/O in a pure layer.

## Testing

The tree splits by kind (explicit directories, not just marks):

- `tests/unit/` offline, fast: the core-engine codegen twin (`_async/` ->
  `_sync/`) plus flavor-agnostic loose tests (`test_cli.py`, `test_errors.py`,
  ...). `just test-unit` runs `tests/unit tests/conformance` with coverage.
- `tests/conformance/` the parametrized backend suite (codegen twin). Its
  `memory`/`local` params run offline in `test-unit`; the cloud params
  (`azure`/`azblob`/`s3`/`gcs`) are `@pytest.mark.integration` and run only
  under `just test-integration` (`pytest tests/conformance -m integration`),
  skipping when credentials are absent. Marks are right here because it is one
  parametrized body over unit and cloud backends, not a separable suite.
- `tests/automation/` release and workflow-contract tests (`just test-automation`).
- `tests/typing/` static `assert_type` targets, checked by BasedPyright/mypy
  (`just typing`), not collected by pytest. `tests/smoke/` are scripts, not
  `test_*.py`, run by `just smoke`. Both sit outside `testpaths`.

Integration credentials (per backend, all `STORIX_TEST_<BACKEND>_*` except s3's
AWS keys): azure/ADLS `STORIX_TEST_AZURE_ACCOUNT_NAME`+`_CREDENTIAL`; azblob
`STORIX_TEST_AZBLOB_CONTAINER` (+`_ACCOUNT_NAME`/`_CREDENTIAL`/`_ENDPOINT`); s3
`STORIX_TEST_S3_BUCKET` (+`_REGION`/`_ENDPOINT`, `AWS_ACCESS_KEY_ID`,
`AWS_SECRET_ACCESS_KEY`); gcs `STORIX_TEST_GCS_BUCKET`
(+`_CREDENTIAL_PATH`/`_ENDPOINT`).

`just test-integration` auto-loads `.env` when present (override the path with
`STORIX_ENV_FILE=path.env`), so putting the `STORIX_TEST_*` vars there is
enough locally; in CI, set them as real environment variables instead. Note
this is the test namespace, separate from the library's `STORIX_*` connection
config. Run one backend with `just test-integration -k azure`.

- Mirror the source layout. A test for `_async/layers/cache.py` lives in
  `tests/unit/_async/test_layers.py`; its `tests/unit/_sync/` twin is generated,
  never written by hand.
- Keep test cases concise and meaningful, one behavior each, Given-When-Then.
- Prefer pytest fixtures over mocking.
- Async tests need no `@pytest.mark.asyncio`; it is configured in pyproject.
- New backends and layers slot into the conformance suite rather than getting a
  bespoke harness.

## Configuration changes keep `storix.toml.example` in step

`storix.toml.example` at the repository root is the complete, annotated
reference for every key a config file may carry: top-level settings,
every provider table, profiles and their stage overlays, and `[cli]`.

A change that adds, renames, or removes a setting updates that file in the
same pull request. Two tests in `tests/unit/test_config.py` enforce it: one
loads the example as a real project config, and one fails when a provider
model has a field the example does not mention. Neither can be satisfied by
editing the test.

## Public communication & feature standards

When writing public documentation, READMEs, issue templates, or release notes:

- **Never oversell maturity.** Avoid buzzwords like "production-grade",
  "enterprise-ready", or "zero-copy" unless backed by explicit benchmarks or evidence.
- **Distinguish available vs planned capabilities.** Clearly separate shipped features
  from items on the roadmap or under consideration.
- **Verify every public example.** Public examples must either be executable and tested,
  or explicitly marked as fragments. In both cases, verify their syntax, imports, types,
  async usage, and actual API behavior.
- **Maintain an honest maintainer voice.** Frame missing capabilities or errors as
  opportunities for workflow improvements rather than hiding them.

## Naming the public surface

Two rules, both already visible in the existing API - follow them so new
additions stay consistent.

- **Borrow the established unix name.** A user-facing operation takes the name
  of the unix command or well-known program that already means it: `ls`, `cat`,
  `du`, `mv`, `cp`, `echo`, `touch`, `stat`, `tree`. When you add one, reach for
  that vocabulary before inventing: an "absolute path" resolver is `realpath`,
  not `get_absolute`; a lazy rich listing is `scandir` (after `os.scandir`), a
  lazy name listing is `iterdir` (after `pathlib`). The names are the docs; a
  unix user already knows them.
- **Prefer an extensible `kind` over a boolean.** A classification that could
  grow a case tomorrow is an enum, not a bool. `PathKind` (`file`/`directory`,
  and a future `symlink`) is why user-facing entries carry `kind`, not
  `is_dir` - a boolean cannot represent the third case without a breaking
  change. Booleans are for genuinely two-valued facts.

## Writing style

ASCII only. No Unicode punctuation, em-dashes, or decorative characters. Use
plain quotes (" and '), `->` for arrows, `...` for ellipsis. Break sentences with
commas, parentheses, or separate sentences, never with `--`.

Note: much of the existing corpus (README, ADRs, docstrings) predates this rule
and still uses em-dashes and en-dashes. Follow ASCII-only in new content, and
migrate existing text opportunistically or in a dedicated pass.

### Comments and docstrings are permanent project artifacts

They are read by contributors who were not there when the code was written, so
they are held to the standard the pull request body is (see "Pull request body:
authorship and tone"), for the same reason.

- No first person. Not `we assume`, `our writes`, `I chose`. State the fact:
  `a suffix is taken as a file`.
- Never mention agents, AI, prompts, sessions, tooling modes, or personal
  shorthand. A marker naming the process that produced a line means nothing to
  the next reader and dates the code.
- Explain why, not what. `# bump the counter` beside `counter += 1` is noise; a
  comment earns its place by recording a constraint, a tradeoff, a defect it
  avoids, or a reason the obvious approach is wrong.
- A deliberate shortcut is worth a comment when it has a known ceiling. Name
  the ceiling and what would lift it, in plain prose, with no marker prefix.
- `TODO` names a subject and a condition, not an aspiration. `TODO: fix later`
  and `TODO: override in cloud backends` are noise. Either write what the
  constraint actually is and what would change it, or make it a documented
  limitation in the docstring where a user will see it.
- No commented-out code. Delete it; git remembers.

Existing text that predates a rule is migrated opportunistically or in a
dedicated pass, as with ASCII-only above.

## Typing and docstrings

House style on top of what ruff enforces. Match it in new code.

- Annotate constants with a parametrized `Final[...]`, always with the value type
  (`MAX_RETRIES: Final[int] = 3`), never a bare `Final`.
- Annotate with the abstract collection types from `collections.abc` (`Sequence`,
  `Mapping`, `Iterable`, `MutableMapping`), not the concrete builtins, unless the
  concrete type is genuinely part of the contract. Accept the widest type you use
  and always parametrize the generic (`Sequence[str]`), never a bare `Sequence`.
- Declare type aliases with the `type` statement so they read as aliases, not
  constructible values (`type BoundLayer = ...`).
- Document a parameter in the docstring (Google `Args:` block), never as a comment
  above the parameter. Document every exception in a `Raises:` block, naming the
  condition that triggers it, not just the type.
- Document a module global, constant, or pydantic `Field` with a docstring on the
  line below it, not a trailing comment. storix already does this; see
  `src/storix/constants.py`.
