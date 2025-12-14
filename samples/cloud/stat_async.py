import asyncio

from storix.aio import AzureDataLake


async def main() -> None:
    fs = AzureDataLake()
    print(fs.pwd())
    print(await fs.ls())
    await fs.cd('file')
    print(fs.pwd())
    print(await fs.stat(fs.pwd()))
    await fs.close()


asyncio.run(main())
