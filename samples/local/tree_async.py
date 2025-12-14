import asyncio

from storix.aio import LocalFilesystem


fs = LocalFilesystem(initialpath='..')


async def main() -> None:
    # print(fs.find("."))
    # res = fs.find(".") | wc
    # print(res)
    # print(fs.tree("."))
    t = await fs.tree('.', abs=False)

    print(t)
    print(f'size: {t.size}')

    # # check built caching working
    # for _ in range(int(1e4 * 10)):
    #     t.build()


asyncio.run(main())
