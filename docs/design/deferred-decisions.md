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
