"""Five minutes of storix, async flavor - identical names, awaitable.

Uses temporary(): a real on-disk workspace that deletes itself on exit.
"""

import asyncio

from storix.aio import temporary


async def main() -> None:
    async with temporary() as fs:
        await fs.mkdir('/docs')
        await fs.echo('unicode is encoded for you', '/docs/note.txt')
        print('cat  ->', await fs.cat('/docs/note.txt'))

        await fs.cd('/docs')
        await fs.touch('a.txt', 'b.txt')
        print('ls   ->', await fs.ls())

        print('data url ->', (await fs.data_url('note.txt'))[:40], '...')
    # the temporary directory is gone here


if __name__ == '__main__':
    asyncio.run(main())
