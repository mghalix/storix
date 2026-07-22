"""Opendal-engine specifics; shared behavior lives in test_backends.py.

Runs offline over the credential-free memory service.
"""

from collections.abc import AsyncIterator
from pathlib import PurePosixPath as P

import pytest

from storix._async.backends.opendal import OpendalBackend
from storix.models import RawStat


async def _astream(*chunks: bytes) -> AsyncIterator[bytes]:
    for chunk in chunks:
        yield chunk


async def test_list_dir_non_empty_directory_makes_no_stat_calls(
    monkeypatch: pytest.MonkeyPatch,
):
    # list-first: one real child proves the directory; the old stat
    # precheck cost up to two extra requests per listing
    backend = OpendalBackend('memory')
    await backend.make_dir(P('/d'), parents=False)
    await backend.write_stream(
        P('/d/a.txt'), _astream(b'x'), mode='w', content_type=None
    )

    calls = 0
    original = backend.stat

    async def counting_stat(path: P) -> RawStat:
        nonlocal calls
        calls += 1
        return await original(path)

    monkeypatch.setattr(backend, 'stat', counting_stat)

    entries = [entry async for entry in backend.list_dir(P('/d'))]

    assert {entry.name for entry in entries} == {'a.txt'}
    assert calls == 0
