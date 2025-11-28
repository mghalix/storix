import asyncio

from storix.aio import LocalFilesystem


async def main() -> None:
    fs = LocalFilesystem(".", sandboxed=True)
    print(fs.pwd())
    print(await fs.ls())
    print()
    fs = fs.chroot("./sample-files/")
    print(fs.pwd())
    print(await fs.ls())
    print()


if __name__ == "__main__":
    asyncio.run(main())
