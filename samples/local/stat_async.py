import asyncio

from storix.aio import LocalFilesystem


async def main() -> None:
    fs = LocalFilesystem()
    print(fs.pwd())
    dir = await fs.ls()
    print(await fs.stat(dir[0]))
    await fs.close()


asyncio.run(main())
