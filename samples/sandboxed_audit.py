"""Production pattern: containers, sandboxes, and real-path auditing.

Three ideas, kept deliberately separate:

- a *container* is backend configuration - ``AzureBackend('raw', ...)``
  anchors '/' at the raw container. Three containers = three backends
  = three independent filesystems (simulated here with MemoryBackends);
- a *sandbox* confines a session to a directory INSIDE one filesystem -
  it knows only its root ('/youtube'), never the container;
- *audit records* are composed by the provider, who owns both facts:
  the container name and the privileged path translation.

The privilege split: workers get sessions and see only virtual paths;
the provider keeps the layer handle. ``fs.chroot(path)`` is the
no-handle convenience when you just want the jail.

FastAPI wiring sketch:

    @lru_cache
    def get_yt() -> tuple[Storix, SandboxLayer]:
        raw = AzureBackend('raw', account_name=..., credential=...)
        sandbox = SandboxLayer(raw, root='/youtube')
        return Storix(sandbox), sandbox

    @app.post('/videos/{video_id}')
    async def upload(video_id: str, yt=Depends(get_yt)):
        fs, sandbox = yt
        await fs.echo(payload, f'/{video_id}.mp4')
        await audit.insert(
            container='raw',                                  # provider fact
            path=str(sandbox.to_real(fs.resolve(f'/{video_id}.mp4'))),
        )

Run:  uv run python samples/sandboxed_audit.py
"""

import asyncio

from storix.aio import SandboxLayer, Storix
from storix.aio.backends import MemoryBackend, StorageBackend


async def main() -> None:
    # three containers, three filesystems - in production:
    #   {name: AzureBackend(name, account_name=..., credential=...) ...}
    containers: dict[str, StorageBackend] = {
        name: MemoryBackend() for name in ('raw', 'staging', 'processed')
    }
    raw_fs = Storix(containers['raw'])
    staging_fs = Storix(containers['staging'])

    # each is independent and fully usable at any time
    await raw_fs.mkdir('/youtube')
    await staging_fs.touch('/manifest.json')

    # --- the audit-grade sandbox: provider keeps the handle ---
    sandbox = SandboxLayer(containers['raw'], root='/youtube')
    yt_fs = Storix(sandbox)

    await yt_fs.echo(b'...video bytes...', '/dQw4w9WgXcQ.mp4')
    virtual = yt_fs.resolve('/dQw4w9WgXcQ.mp4')
    print(f'worker saw    : {virtual}')
    print(f'audit records : container=raw path={sandbox.to_real(virtual)}')

    # --- the convenience jail: no handle, one line ---
    yt = raw_fs.chroot('/youtube')
    print(f'chroot ls     : {await yt.ls("/")}')

    # sandboxes cannot see the wider filesystem, and errors leak nothing:
    try:
        await yt.cat('/manifest.json')  # exists in staging, not in the jail
    except FileNotFoundError as err:
        print(f'jailed error  : {err}')


if __name__ == '__main__':
    asyncio.run(main())
