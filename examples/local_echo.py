from collections.abc import AsyncGenerator, Generator


def _test_data() -> Generator[str, None, None]:
    return (str(i) + "\n" for i in range(100))


def sync() -> None:
    from storix import LocalFilesystem

    fs = LocalFilesystem(".", sandboxed=True)
    fs.echo(_test_data(), "x.txt", mode="w")


async def _atest_data() -> AsyncGenerator[str, None]:
    for i in range(100):
        yield str(i) + "\n"


async def a_sync() -> None:
    from storix.aio import LocalFilesystem

    fs = LocalFilesystem(".", sandboxed=True)
    await fs.echo(_atest_data(), "x.txt", mode="a")


if __name__ == "__main__":
    import asyncio

    # sync()
    asyncio.run(a_sync())
