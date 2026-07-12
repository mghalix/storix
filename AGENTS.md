# AGENTS.md

Guidance for AI agents (Claude Code and others) working in this repository.
CLAUDE.md is a symlink to this file.

## The one rule that matters: async is the source of truth

storix is async-first. The sync flavor under `src/storix/_sync/` and
`tests/_sync/` is GENERATED from `src/storix/_async/` and `tests/_async/` by
`scripts/unasync.py` (token substitution: `async def` -> `def`, `await ` -> "",
`storix._async` -> `storix._sync`, and so on).

- Edit only the `_async` trees. Never edit `_sync/` by hand.
- After any change under `_async`, regenerate:
  `uv run python scripts/unasync.py` (or `just gen`).
- The codegen and CI fail if the committed `_sync` tree drifts
  (`uv run python scripts/unasync.py --check`).
- Hand-written twins that are NOT generated: `_compat.py`, `local.py`,
  `azure.py`, `test_compat.py`. Their primitives differ per flavor, so the sync
  twin is maintained by hand and must exist.

## Commands

- `uv run python scripts/unasync.py`   regenerate the sync tree (or `just gen`)
- `uv run pytest -q`                    run the tests (or `just test`)
- `uv run pytest tests/_async/test_layers.py -k without_layer`   a single test
- `uv run pytest -m integration`        azure integration suite (needs STORIX_AZURE_* creds)
- `uv run ruff check .` / `uv run ruff format .`   lint / format
- `uv build`                            build the wheel and sdist

Integration tests are opt-in; the default pytest config deselects them
(`-m 'not integration'`). If a justfile is present, `just` lists the shortcuts
(`just gen`, `just check`, `just lint`, `just fmt`, `just release`); `just check`
is the full push gate (lint + format + codegen drift + tests).

## Architecture (the big picture)

Hexagonal: one core engine over one small port.

- `Storix` (`_async/core.py`) is the unix-flavored session. It owns cwd/home and
  path resolution (`~`, `..`, cwd via `pathops`) and implements every user-facing
  operation (`ls`/`cat`/`echo`/`du`/`mv`/`url`/...). It speaks only to a
  `StorageBackend`.
- `StorageBackend` (the port, about 14 methods) is what backends implement:
  `LocalBackend`, `MemoryBackend` (the reference backend, ideal for tests), and
  `AzureBackend` (ADLS Gen2, HNS accounts only). Backends do zero path logic and
  raise only `storix.errors`.
- Layers are backends that wrap backends (same port). Compose them with
  `Storix(be, layers=[...])`, `fs.with_layer(Layer, **kwargs)`, or
  `fs.with_layer_missing(Layer)` (native-preference, capability inferred).
  `SandboxLayer` is an escape-proof chroot, `CacheLayer` is a read-through cache,
  `DataUrlLayer` and `MetadataLayer` backfill capabilities, `LayerBase` is the
  delegating base for custom layers. `fs.without_layer(Layer)` / `fs.uncached`
  strip layers for one session; a `SandboxLayer` is non-removable
  (`removable = False`).
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
under `website/` (not part of the shipped package).

## Testing

- Mirror the source layout. A test for `_async/layers/cache.py` lives in
  `tests/_async/test_layers.py`; its `tests/_sync/` twin is generated, never
  written by hand.
- Keep test cases concise and meaningful, one behavior each, Given-When-Then.
- Prefer pytest fixtures over mocking.
- Async tests need no `@pytest.mark.asyncio`; it is configured in pyproject.
- A parametrized conformance suite runs every backend and layer in both flavors.
  New backends and layers should slot into it rather than getting a bespoke
  harness.

## Writing style

ASCII only. No Unicode punctuation, em-dashes, or decorative characters. Use
plain quotes (" and '), `->` for arrows, `...` for ellipsis. Break sentences with
commas, parentheses, or separate sentences, never with `--`.

Note: much of the existing corpus (README, ADRs, docstrings) predates this rule
and still uses em-dashes and en-dashes. Follow ASCII-only in new content, and
migrate existing text opportunistically or in a dedicated pass.

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
