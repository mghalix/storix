from pathlib import Path

from storix._async import temporary


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
