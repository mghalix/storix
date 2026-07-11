"""Tests for the sync gather twin (hand-written, not generated)."""

from storix._sync._compat import gather


def test_gather_collects_values():
    assert gather(1, 2, 3) == [1, 2, 3]


def test_gather_empty():
    assert gather() == []


def test_gather_accepts_limit_for_signature_parity():
    assert gather('a', limit=4) == ['a']
