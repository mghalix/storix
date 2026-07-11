"""Sync twin of ``storix._async._compat`` - hand-written, NOT generated.

By the time this ``gather`` is called, its arguments have already been
evaluated sequentially during ``*`` unpacking (a sync call expression
executes immediately), so all that remains is collecting the results.
``limit`` is accepted for signature parity and has no effect.

Keep in lockstep with the async twin; both are excluded from codegen.
"""

from storix.constants import DEFAULT_CONCURRENCY


def gather[T](*results: T, limit: int = DEFAULT_CONCURRENCY) -> list[T]:
    """Collect already-computed results (see the async twin's semantics)."""
    del limit  # signature parity with the async twin only
    return list(results)
