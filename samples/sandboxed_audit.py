"""Production pattern: sandboxed filesystems with real-path auditing.

The privilege split is the point:

- the *session* (handed to pipelines, agents, request handlers) sees
  only virtual paths - its '/' IS the sandbox root;
- the *provider* (the code that built the sandbox) keeps the layer
  handle, and only it can translate virtual paths to real ones for
  audit records, indexes, or cross-system references.

Storix's core stays sandbox-unaware on purpose: give a worker `fs` and
it cannot learn where in the wider store it lives from paths or errors.

In FastAPI the provider pair becomes a dependency:

    def get_yt() -> tuple[Storix, SandboxLayer]:      # app.state-cached
        backend = AzureBackend('raw', account_name=..., credential=...)
        sandbox = SandboxLayer(backend, root='/raw/youtube')
        return Storix(sandbox), sandbox

    @app.post('/videos/{video_id}')
    async def upload(video_id: str, yt=Depends(get_yt)):
        fs, sandbox = yt
        await fs.echo(payload, f'/{video_id}.mp4')
        await audit_store.insert(
            path=str(sandbox.to_real(fs.resolve(f'/{video_id}.mp4')))
        )

Run:  uv run python samples/sandboxed_audit.py
"""

import asyncio

from storix.aio import SandboxLayer, Storix
from storix.aio.backends import MemoryBackend, StorageBackend


def get_youtube_fs(store: StorageBackend) -> tuple[Storix, SandboxLayer]:
    """The provider: builds the jail, returns session + privileged handle."""
    sandbox = SandboxLayer(store, root='/raw/youtube')
    return Storix(sandbox), sandbox


async def ingest_video(fs: Storix, video_id: str) -> str:
    """A worker: sees only the virtual namespace, returns the virtual path."""
    virtual = f'/{video_id}.mp4'
    await fs.echo(b'...video bytes...', virtual)
    return str(fs.resolve(virtual))


async def main() -> None:
    store = MemoryBackend()  # swap for AzureBackend(...) in production
    await store.make_dir(Storix(store).resolve('/raw/youtube'), parents=True)

    fs, sandbox = get_youtube_fs(store)

    virtual = await ingest_video(fs, 'dQw4w9WgXcQ')
    real = sandbox.to_real(virtual)

    print(f'worker saw   : {virtual}')
    print(f'audit records: {real}')
    print(f'reconstructed: {sandbox.to_virtual(real)}')

    # errors are scoped too - the worker cannot learn the real prefix:
    try:
        await fs.cat('/missing.mp4')
    except FileNotFoundError as err:
        print(f'worker error : {err}')  # no '/raw/youtube' anywhere


if __name__ == '__main__':
    asyncio.run(main())
