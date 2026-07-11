"""pwd / resolve / locate - and how to persist a location for later.

The three primitives answer different questions:

    pwd()      -> where am I now (virtual)
    resolve()  -> the port path, to cd/cat/persist WITHIN storix
    locate()   -> a physical URI, to hand to something OUTSIDE storix

The key clarification: locate() is NOT how you save-and-reopen inside
your program (it is a URI, not a port path, and cannot be cd'd). To
persist a spot and return to it later, dump (provider, config, resolve)
and rebuild - shown below and it actually round-trips.

Run:  uv run python samples/navigation.py
"""

import asyncio
import json
import tempfile

from storix.aio import Storix, get_storage
from storix.aio.backends import LocalBackend


async def main() -> None:
    base = tempfile.mkdtemp()

    fs = Storix(LocalBackend(base))
    await fs.mkdir('/raw/videos', parents=True)
    await fs.cd('/raw/videos')
    await fs.echo(b'...', 'clip.mp4')

    print('pwd     ->', fs.pwd())  # /raw/videos
    print('resolve ->', fs.resolve('clip.mp4'))  # /raw/videos/clip.mp4  (port path)
    print('locate  ->', fs.locate('clip.mp4'))  # file:///<base>/.../clip.mp4  (URI)

    # --- persist a location IN-PROGRAM: (provider, config, resolve) ---
    # You own the config (you built the session), so you dump it with the
    # stable port path. This is the round-trippable bookmark.
    bookmark = json.dumps(
        {'provider': 'local', 'config': {'base': base}, 'path': str(fs.resolve())}
    )
    # ...later, another process, from just that string:
    saved = json.loads(bookmark)
    reopened = get_storage(saved['provider'], **saved['config'])
    await reopened.cd(saved['path'])
    print()
    print('reopened at ->', reopened.pwd())  # /raw/videos
    print('and reads   ->', await reopened.cat('clip.mp4'))  # b'...'

    # --- what locate() is actually for: EXTERNAL consumers ---
    # storix does not read it back (that is the URI factory, 0.3.0).
    # You log it / store it so a *different* tool can find the object:
    uri = fs.locate('clip.mp4')
    print()
    print(f'audit log: uploaded {uri}')
    print('  -> file:// opens in a file manager')
    print('  -> abfss:// pastes into Azure Storage Explorer / az CLI')
    print('  -> serves as a stable cross-system identity/dedup key')


if __name__ == '__main__':
    asyncio.run(main())
