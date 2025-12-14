import asyncio

from storix.aio import LocalFilesystem


fs = LocalFilesystem()


async def main() -> None:
    it = (f for f in await fs.ls(abs=True) if f.maybe_file())
    first = next(it)
    print(first)

    print(await fs.du(first))
    # print(await fs.du('.'))  # BUG: something wrong here

    await fs.close()


asyncio.run(main())
