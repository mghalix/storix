"""pwd / resolve / locate - three answers to 'where is this?'

The confusion worth clearing up: ``locate`` returns a URI for *external*
reference and is deliberately NOT something you cd to. To bookmark a
spot and return to it, use ``resolve`` (a plain port path).

Run:  uv run python samples/navigation.py
"""

import asyncio

from storix.aio import SandboxLayer, Storix
from storix.aio.backends import LocalBackend


async def main() -> None:
    import tempfile

    base = tempfile.mkdtemp()
    fs = Storix(LocalBackend(base))
    await fs.mkdir('/raw/videos', parents=True)

    # pwd: where am I now (virtual)
    await fs.cd('/raw/videos')
    print('pwd     ->', fs.pwd())  # /raw/videos

    # resolve: the NAVIGABLE, bookmarkable absolute port path
    bookmark = fs.resolve()  # /raw/videos
    await fs.cd('/')  # wander off
    print('pwd     ->', fs.pwd())  # /
    await fs.cd(bookmark)  # ...and back, because resolve() is a port path
    print('back to ->', fs.pwd())  # /raw/videos

    # locate: the EXTERNAL physical URI - for audit/logs/other tools.
    # Not a port path: you cannot cd to it.
    await fs.echo(b'...', 'clip.mp4')
    print('locate  ->', fs.locate('clip.mp4'))  # file:///<base>/raw/videos/clip.mp4

    # under a sandbox, resolve stays virtual, locate reveals the real path
    jailed = Storix(SandboxLayer(LocalBackend(base), root='/raw'))
    await jailed.cd('/videos')
    print()
    print('jailed pwd     ->', jailed.pwd())  # /videos   (its world)
    print('jailed resolve ->', jailed.resolve())  # /videos   (cd-able here)
    print('jailed locate  ->', jailed.locate())  # file:///<base>/raw/videos


if __name__ == '__main__':
    asyncio.run(main())
