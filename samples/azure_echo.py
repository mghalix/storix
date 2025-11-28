from collections.abc import AsyncGenerator, Generator


def _test_data() -> Generator[str]:
    return (str(i) + '\n' for i in range(100))


def sync() -> None:
    from storix import AzureDataLake

    fs = AzureDataLake('.', sandboxed=True)
    fs.echo(_test_data(), 'x.txt', mode='w')
    fs.echo('hi', 'x.txt', mode='a')


async def _atest_data() -> AsyncGenerator[str]:
    for i in range(100):
        yield str(i) + '\n'


async def a_sync() -> None:
    from storix.aio import AzureDataLake

    fs = AzureDataLake('.', sandboxed=True)
    await fs.echo(_atest_data(), 'x.txt', mode='a')


if __name__ == '__main__':
    import asyncio

    # sync()
    asyncio.run(a_sync())
