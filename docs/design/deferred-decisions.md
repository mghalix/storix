# Deferred design decisions

Decisions discussed during the 0.2.0 refactor that were deliberately postponed,
with the agreed shape and the trigger for adopting each. Recorded so the
reasoning isn't re-litigated later.

## House-style dataclass decorator (`@model`)

**What:** the port DTOs repeat `@dataclasses.dataclass(frozen=True, slots=True,
kw_only=True)`. A plain base class cannot carry dataclass options (the
decorator processes one class and `slots=True` even rebuilds it), so the
correct mechanism is a tiny decorator marked with `typing.dataclass_transform`
(PEP 681), which both pyright and mypy understand:

```python
from dataclasses import dataclass
from typing import dataclass_transform


@dataclass_transform(frozen_default=True, kw_only_default=True)
def model[T](cls: type[T]) -> type[T]:
    """Storix house-style model: frozen, slotted, keyword-only."""
    return dataclass(frozen=True, slots=True, kw_only=True)(cls)
```

Avoid the shortcut `model = dataclass(frozen=True, ...)` — pyright follows the
alias but mypy's support is unreliable, and we run both.

**Trigger:** adopt when ~5+ dataclass models exist and per-class option
drift becomes plausible. At two models the explicit line is clearer.

**Status:** adopted in 0.4.1 as `storix.models.model`. The fifth house-style
DTO (`TransferEvent`, ADR 0019) hit the trigger; `_Op` in the cache layer had
already drifted (it lacked `kw_only`), proving the point.

## Test-kind markers (`integration`, `e2e`)

**What:** test *location* mirrors the source tree; test *kind* is expressed
with pytest markers, not directories (a `tests/unit/` split would force every
test path to answer two questions and deep-nest the mirrored tree):

```toml
[tool.pytest.ini_options]
markers = [
    "integration: needs real external services (live Azure, Azurite)",
]
addopts = "-m 'not integration'"  # default run stays fast
```

CI runs `pytest -m integration` as a separate job with credentials.

**Trigger:** the Azure backend rewrite (first tests that need real services).
Until then every test is fast enough to be unmarked.

## Pydantic modernization

- `use_attribute_docstrings=True` on `StorixBaseModel` would lift the
  under-field docstrings in `models.py` into JSON-schema descriptions.
  Requires pydantic >= 2.7; current floor is 2.0. Adopt together with a
  deliberate floor bump.
- `json_encoders` in `StorixBaseModel.model_config` is deprecated in
  pydantic v2; replace with `field_serializer`/`model_serializer` when the
  models are next touched.

## `FileProperties.file_kind` → `kind`

The field keeps its legacy name because the old providers construct it and
tests assert on it. Rename to `kind` (matching `RawStat.kind` and
`StorixPath.kind`) when the legacy provider tree is deleted.

## Timezone-aware datetimes

Local stat times are naive (`datetime.fromtimestamp`) while cloud SDKs return
aware datetimes — an inconsistency the old providers ship today. The new port
should standardize on UTC-aware datetimes in `RawStat`, enforced by ruff's
`DTZ` rules. Decide when implementing the backends; legacy code is exempt
(it is deleted, not fixed).

## Layer composition DX (`layers=[...]` vs `.wrap()` chaining)

**What:** nested layer construction (`Storix(CacheLayer(SandboxLayer(
backend, root=...)))`) reads inside-out. Candidate ergonomics once
multiple layers exist:

- `Storix(backend, layers=[...])` taking layer *factories*
  (`Callable[[StorageBackend], StorageBackend]`, e.g.
  `partial(SandboxLayer, root='/x')`), applied left-to-right;
- `.wrap()` chaining on `BackendBase`/layers:
  `LocalBackend('x').wrap(SandboxLayer, root='/t').wrap(CacheLayer)`.

**Trigger:** deliberately deferred until a second shipped layer exists
(CacheLayer/MetadataLayer, 0.4.0). With one layer, nesting is shallow
and choosing an API shape now would be guessing at usage patterns; the
wrong convenience API is harder to remove than nesting is to read.

## MountLayer: the filesystem compositor

**What:** a mount-table backend routing the first path segment to child
backends, unix-mount style:

```python
fs = Storix(MountLayer({
    'raw': AzureBackend('raw', ...),
    'staging': AzureBackend('staging', ...),
    'processed': LocalBackend('~/cache'),
}))
await fs.cat('/raw/youtube/x.mp4')
await fs.mv('/raw/x.mp4', '/processed/x.mp4')   # cross-backend
```

Design notes: `list_dir('/')` yields the mount names as directories;
ops on '/' itself (delete, write) are refused; `mv`/`cp` crossing
mounts fall back to stream-copy + delete since the generic helpers
assume one backend; capabilities are the per-mount intersection (or
per-path resolution - decide). ~150 lines plus conformance edge cases.

**Trigger:** owner interest confirmed; sized as its own feature (0.2.x
candidate, post CLI-rewrite) rather than a pre-release add-on. Until
then a plain dict of sessions covers most multi-container work.

## Result-returning "Gate" (errors as values)

**What:** a functor over a `Storix` session that rewrites every operation's
return type from `T` to `Result[T, E]` (safe-result / returns-style), so
callers `.map`/`.unwrap_or` instead of writing try/except, which pays off most
in concurrent fan-out (`gather` over per-item Results). Distinct from a Layer
(backend -> backend, same interface): a Gate changes the interface, so it is a
terminal transform on the session, not a `layers=` entry.

**The finding that gates the whole idea:** Result gives *call-site enforcement*
(callers cannot ignore an `Err`), not *definition-site accuracy*. Python has no
checked exceptions, so nothing verifies a method's declared `E` matches what its
body actually raises, the same drift a `Raises:` docstring has. So a Gate does
not remove the need to get the error set right; it relocates an unverified
promise into a type and adds downstream checking.

A *mechanical* whole-session Gate can only do one blanket catch, and today that
catch would lie: `validate_chunk_size` raises a bare `ValueError`
(`_stream.py`), outside the `StorageError` taxonomy, so a
`Result[T, StorageError]` wrapper leaks it as a raw exception.

**Prerequisite / the real decision:** make `StorageError` the single *closed*
channel for every handleable error (migrate the stray bare `ValueError`s into
the taxonomy). Then `E` is uniformly `StorageError`, a mechanical
`except StorageError` wrap is honest and exhaustive-for-handleable, non-domain
errors (bugs, `KeyboardInterrupt`) correctly propagate, and `.map`/`.unwrap_or`
work on the uniform type. ADR 0004 already points here ("every failure raises",
`StorageError` is the base); this finishes the job.

**Lean:** once `E` is uniformly `StorageError`, a bespoke Gate abstraction is
likely overkill, `returns.future.future_safe(StorageError)` or a ~5-line wrapper
gets the same result. Prefer that over generating a parallel Result-API across
~30 ops in two flavors, unless a concrete call site proves the wrapper too
painful.

**Trigger:** deferred behind backend breadth (adoption comes first). Revisit
only after closing the taxonomy; that migration is the gating work, not the
Gate itself.
