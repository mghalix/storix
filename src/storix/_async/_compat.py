"""The concurrency shim: the ONLY place async and sync semantics diverge.

This file is excluded from codegen; ``storix._sync._compat`` is its
hand-written twin. Callers import ``gather`` from here, the codegen
rewrites the import path, and sync call sites degrade to sequential
execution naturally: their arguments are evaluated one by one during
``*`` unpacking, so the sync ``gather`` merely collects results.

Keep this module tiny - every line here is exempt from the "async source
of truth" guarantee and must be audited by hand against its twin.
"""

import asyncio

from collections.abc import Awaitable
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
