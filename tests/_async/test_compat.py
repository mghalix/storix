"""Tests for the async gather shim.

Excluded from codegen (like the shim itself); tests/_sync/test_compat.py
is the hand-written twin.
"""

import asyncio

import pytest

from storix._async._compat import gather
from storix.errors import PathNotFoundError


async def test_gather_preserves_order():
    async def double(x: int) -> int:
        await asyncio.sleep(0)
        return x * 2

    assert await gather(*(double(i) for i in range(5))) == [0, 2, 4, 6, 8]


async def test_gather_empty():
    assert await gather() == []


async def test_gather_propagates_first_exception_unwrapped():
    """The storix error contract must survive: no ExceptionGroup wrapping."""

    async def ok() -> int:
        return 1

    async def boom() -> int:
        missing = '/x'
        raise PathNotFoundError(missing)

    with pytest.raises(PathNotFoundError):
        await gather(ok(), boom(), ok())


async def test_gather_bounds_concurrency():
    active = 0
    peak = 0

    async def task() -> None:
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        active -= 1

    await gather(*(task() for _ in range(20)), limit=4)
    assert 1 < peak <= 4
