"""Tests for the sync concurrency twin (hand-written, not generated).

Mirrors the ``concurrent`` cases in tests/unit/_async/test_compat.py. The async
``gather`` tests have no counterpart here: the sync ``gather`` was removed
once every call site moved to thunks.
"""

import threading

from functools import partial

import pytest

from storix._sync._compat import concurrent
from storix.errors import PathNotFoundError


def test_concurrent_runs_thunks_in_order():
    def double(x: int) -> int:
        return x * 2

    assert concurrent(partial(double, i) for i in range(5)) == [0, 2, 4, 6, 8]


def test_concurrent_empty():
    assert concurrent([]) == []


def test_concurrent_propagates_first_exception_unwrapped():
    """The storix error contract must survive: no ExceptionGroup wrapping."""

    def ok() -> int:
        return 1

    def boom() -> int:
        missing = '/x'
        raise PathNotFoundError(missing)

    with pytest.raises(PathNotFoundError):
        concurrent([ok, boom, ok])


def test_concurrent_does_not_start_queued_thunks_after_a_failure():
    """Teardown cancels the queue instead of joining it.

    Sync-only, so it has no async counterpart: this is the thread-pool
    ``shutdown(wait=False, cancel_futures=True)`` contract, while the async
    twin documents the opposite (remaining tasks run in the background).
    Only the thunk a just-freed worker had already picked up may still
    start; every later one is cancelled.
    """
    started: list[int] = []
    stop = threading.Event()

    def boom() -> int:
        missing = '/x'
        raise PathNotFoundError(missing)

    def record(index: int) -> int:
        started.append(index)
        stop.wait(timeout=1)  # hold the worker so nothing else can start
        return index

    thunks = [boom, *(partial(record, i) for i in range(10))]
    try:
        with pytest.raises(PathNotFoundError):
            concurrent(thunks, limit=1)
        assert set(started) <= {0}
    finally:
        stop.set()
