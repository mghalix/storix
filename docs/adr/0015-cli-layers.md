# 15. Layers in the CLI (and where their config lives)

Status: accepted; declarative config file landed in 0.4.3 and the
provider-scoping rule below is amended there (ADR 0022)

## Context
`sx -p azure` builds a bare backend; a CLI user never feels the layers
the library ships (cache, sandbox). Yet the interactive shell is
exactly where a read-through cache pays off - a long-lived session with
repeated `ls`/`du`/`cat` - while a one-shot `sx ls` builds and discards
a cache for nothing (only a *persistent* store shared across
invocations would help it, which few configure). So the target is the
REPL, and the honest headline is `du`.

## Decision
**First increment - curated flags, fixed order.** Two flags on the root callback,
applied via `with_layer` sandbox-innermost / cache-outermost (cache
keys on `locate()`, so it stays correct under the sandbox):
- `--sandbox PATH` -> `SandboxLayer(root=PATH)`. Jailing the session is
  the safest thing a storage CLI can offer (no stray `rm -r` across a
  whole container).
- `--cache [--cache-ttl N]` -> `CacheLayer(metadata=True, du=True,
  read=cache(max_bytes=8 * 1024 * 1024))`. metadata+du+read is the CLI default:
  `du` is the headline win with no cross-session staleness (own writes
  self-evict), `read` is bounded by the cap.

Opt-in, **not** default-on: silently caching a live bucket hides other
writers' uploads until TTL - a footgun for an exploration tool.
Default-on-in-shell stays a future toggle, once it is proven to feel
good.

**REPL touches.** A start banner names the active stack; a `refresh`
meta-command clears the cache via `CacheLayer.clear()` scoped to the
layer's namespace prefix (never a blind `*`, which would nuke a shared
Redis); `provider` grows a `layers:` line.

**Config scoping - the anti-confusion rule.** storix is both a library
and a tool, so `[tool.storix]` is ambiguous about who it affects. Split
by *kind*: connection config ("which backend, how to connect") is
genuinely shared and already spans both surfaces (`STORIX_*` env, read
by `get_storage`, which the CLI calls) - keep it at `[tool.storix]` /
env. The **layer stack** is a UX/policy choice that legitimately
differs between library and CLI, so it is CLI-scoped under
`[tool.storix.cli]`. The library never auto-applies it - you opt in
with `with_layer()` in code. The section name states who it affects;
no spooky wrapping for `get_storage` users.

**Deferred (designed here so it is not re-litigated).** A declarative
stack, ruff-style: loader precedence `storix.toml` / `.storix.toml` ->
`pyproject.toml [tool.storix.cli]` -> env/defaults; an ordered
`[[layers]]` array of `{name, ...kwargs}` resolved through a
name->LayerFactory registry (mirrors `register_backend`, ADR 0009).
The stack is also how a CLI user swaps the cache's in-memory default
for a persistent store (`store=` a cashews URL, or a built-in
disk-backed `CacheStore`) - which is what lets a one-shot `sx --cache`
benefit across invocations. That store needs a cross-process staleness
default (a TTL, or content-hash validation), since separate `sx`
processes sharing one store reopen the single-writer assumption of
ADR 0014. Deliberate non-goal for 0.2.1: no half-built config loader -
flags-only now, the whole file system later, so `--cache`/`--sandbox`
never become a second config source competing with the file.

## Consequences
The interactive shell gets instant repeat navigation / `du` / `cat`
behind one flag, and the CLI's most valuable safety feature (sandbox)
behind another. The config story is pinned - backend shared, layers
CLI-scoped - so the future file lands without churn, and library users
keep an explicit, surprise-free `get_storage`. The cost is a curated
(not arbitrary) flag set until the `[[layers]]` DSL arrives.
