# 9. Configuration and factory: STORIX_*, typed, lazy, extensible

Status: accepted

## Context
Legacy config was a flat unbranded env blob read eagerly inside
providers at import time.

## Decision
Per-backend pydantic-settings models under one brand prefix
(`STORIX_PROVIDER`, `STORIX_<PROVIDER>_<constructor-kwarg>` - the env
key always mirrors the kwarg). `get_storage(provider=None, /,
**overrides)` is the whole factory: settings -> config -> backend ->
core; overrides beat env; zero config lands at local `~/.storix` (never
silently the cwd). Overloads with Unpack'd TypedDicts give per-provider
IDE completion; the provider is positional-only and `provider=` as a
keyword is rejected statically (no catch-all overload) and at runtime -
it previously vanished silently into overrides. Heavy imports stay
inside builders (azure loads only when asked). `register_backend()`
opens the registry to third parties, whose configs live in their own
packages. Rejected: `Storix.local()/.azure()` classmethods (the engine
must not import its adapters); URI-scheme factory deferred to 0.3.0.

## Consequences
One rule derives every env var; DX is typed; plugins have a path.
