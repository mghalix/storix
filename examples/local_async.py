import asyncio

from storix.aio import LocalFilesystem


async def main() -> None:
    fs = LocalFilesystem(".", sandboxed=True)
    await fs.cd("sample-files")

    content_data: bytes = await fs.cat("foo.txt")
    content: str = content_data.decode()
    print(content)


if __name__ == "__main__":
    asyncio.run(main())
