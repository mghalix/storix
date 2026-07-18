"""Tests for the sync concurrency twin (hand-written, not generated).

Mirrors the ``concurrent`` cases in tests/unit/_async/test_compat.py. The async
``gather`` tests have no counterpart here: the sync ``gather`` was removed
once every call site moved to thunks.
"""

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
