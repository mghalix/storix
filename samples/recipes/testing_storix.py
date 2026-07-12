"""Test code that uses storix, with no disk and no mocking.

MemoryBackend is a full in-process backend, so a session over it behaves exactly
like one over local disk or the cloud. scratch() gives a disposable workspace
for isolating a test's writes.
"""

from __future__ import annotations

import pytest

from storix import Storix
from storix.backends import MemoryBackend


@pytest.fixture
def fs() -> Storix:
    return Storix(MemoryBackend())


def test_write_then_read(fs: Storix) -> None:
    fs.echo(b'hello', '/a.txt')
    assert fs.cat('/a.txt') == b'hello'


def test_scratch_is_isolated(fs: Storix) -> None:
    fs.mkdir('/data')
    with fs.scratch() as tmp:
        tmp.echo(b'temp', '/x')
        assert tmp.exists('/x')
    # the scratch workspace is gone; /data is untouched
    assert fs.exists('/data')
