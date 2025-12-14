import asyncio

from storix.aio import AzureDataLake


fs = AzureDataLake()


async def main() -> None:
    dir = await fs.ls()
    await fs.cd(dir[0])

    it = (f for f in await fs.ls(abs=True) if f.maybe_file())
    first = next(it)
    print(first)

    print(await fs.du(first))
    # print(await fs.du('.'))  # BUG: something wrong here

    await fs.close()


asyncio.run(main())
