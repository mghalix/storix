from pathlib import Path, PurePosixPath as P

from storix._async import scratch, temporary
from storix._async.backends.memory import MemoryBackend


async def test_temporary_round_trip_and_cleanup():
    async with temporary() as fs:
        base = Path(fs.backend._base)
        assert base.exists()
        await fs.echo(b'scratch', '/a.txt')
        assert await fs.cat('/a.txt') == b'scratch'
    assert not base.exists()


async def test_temporary_sessions_are_isolated():
    async with temporary() as one, temporary() as two:
        await one.touch('/only-in-one')
        assert not await two.exists('/only-in-one')


async def test_scratch_works_on_any_backend_and_cleans_up():
    backend = MemoryBackend()
    async with scratch(backend) as fs:
        await fs.mkdir('/work')
        await fs.echo(b'ephemeral', '/work/a.txt')
        assert await fs.cat('/work/a.txt') == b'ephemeral'
    # the scratch subtree is gone; the backend itself survives
    assert [p async for p in backend.list_dir(P('/'))] == []
    assert await backend.exists(P('/'))


async def test_scratch_sessions_are_isolated_on_one_backend():
    backend = MemoryBackend()
    async with scratch(backend) as one, scratch(backend) as two:
        await one.touch('/only-in-one')
        assert not await two.exists('/only-in-one')
