"""The concurrency shim: the ONLY place async and sync semantics diverge.

This file is excluded from codegen; ``storix._sync._compat`` is its
hand-written twin. Call sites hand their work to ``concurrent`` as
*thunks* (zero-arg callables, built with ``functools.partial``) and the
two flavors dispatch them differently: async invokes each thunk to get a
coroutine and gathers them under a bounded semaphore, sync submits them to
a bounded thread pool. Passing thunks *un-invoked* is the whole trick -
under codegen the sync call site would otherwise evaluate ``backend.op(x)``
eagerly during ``*`` unpacking, computing every result sequentially before
any pool could run; a thunk defers the work so the pool can spread it.

Keep this module tiny - every line here is exempt from the "async source
of truth" guarantee and must be audited by hand against its twin.
"""

import asyncio

from collections.abc import Awaitable, Callable, Iterable
from typing import cast

from storix.constants import DEFAULT_CONCURRENCY


async def gather[T](*aws: Awaitable[T], limit: int = DEFAULT_CONCURRENCY) -> list[T]:
    """Run awaitables concurrently, at most ``limit`` in flight, in order.

    Error semantics follow ``asyncio.gather`` defaults: the first
    exception propagates *unwrapped* - deliberately, so the storix error
    taxonomy survives (``except PathNotFoundError`` keeps working; a
    ``TaskGroup``'s ``ExceptionGroup`` would break it). Remaining tasks
    run to completion in the background.

    Each call gets its own semaphore: recursive walks (``du``,
    ``delete_tree``) bound concurrency per tree level, not globally,
    which also makes parent-holds-permit deadlocks impossible.
    """
    if not aws:
        return []

    semaphore = asyncio.Semaphore(limit)

    async def bounded(aw: Awaitable[T]) -> T:
        async with semaphore:
            return await aw

    results = await asyncio.gather(*(bounded(aw) for aw in aws))
    return cast('list[T]', results)


async def concurrent[T](
    thunks: Iterable[Callable[[], Awaitable[T]]], *, limit: int = DEFAULT_CONCURRENCY
) -> list[T]:
    """Run each thunk concurrently, at most ``limit`` in flight, in order.

    A thunk is a zero-arg callable; the async flavor invokes it to obtain
    a coroutine and gathers those under the bounded ``gather`` semaphore.
    Empty input yields ``[]``. Error semantics follow ``gather``: the
    first exception propagates unwrapped. See the sync twin for the
    thread-pool dispatch.
    """
    return await gather(*(thunk() for thunk in thunks), limit=limit)
