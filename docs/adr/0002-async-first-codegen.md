# 2. Async source of truth; sync flavor generated (unasync)

Status: accepted

## Context
Both flavors are product requirements. Options: hand-write both
(drift), sync-from-async codegen (httpcore/psycopg3), async-only with a
sync bridge (event-loop overhead on local disk - rejected for a library
whose default backend is local).

## Decision
`scripts/unasync.py`: ordered token substitution from `_async/` to
`_sync/` for source AND tests, whitelist-driven (unknown async
constructs hard-fail the build), `--check` for CI drift. Hand-written
twin exceptions where primitives genuinely differ: `_compat.py`,
`local.py`, `azure.py` (+ their tests), guarded by the conformance
suite instead of codegen.

## Consequences
Generated tests verify generated code - the sync flavor is proven, not
assumed (wire-verified on Azure in both flavors). Contributors must
learn 'edit async, regenerate'; docstrings must be written to transform
gracefully.
