import asyncio

from storix.aio import AzureDataLake


fs = AzureDataLake()


async def main() -> None:
    # print(fs.pwd())
    # fs.cd('user')

    # print(fs.find("."))
    # res = fs.find(".") | wc
    # print(res)
    # print(fs.tree("."))
    # t = fs.tree('.', abs=False)
    t = await fs.tree('.', abs=False)

    print(t)

    # # try exhaustion
    # print(t.size)
    # print(t.size)
    #
    # print(len(t))
    # assert len(t) == t.size
    #
    # # check built caching working
    # for _ in range(int(1e4 * 10)):
    #     t.build()
    await fs.close()


asyncio.run(main())
