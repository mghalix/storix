"""Use storix inside FastAPI with dependency injection.

One session is created for the app's lifetime and injected into route
handlers. Uploads are streamed to storage in chunks, so a large file never
lands in application memory whole.

Note: Reading `UploadFile` in chunks avoids accumulating large payloads in application
memory. `UploadFile` is backed by Starlette's spooled temporary file for large requests.
For raw unbuffered network body streaming without multipart parsing, `request.stream()`
can be passed directly to `fs.echo()`.

Run:  uv run --with "fastapi[standard]" fastapi dev samples/recipes/fastapi_di.py
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Request, UploadFile

from storix.aio import DataUrlLayer, Storix, get_storage


@asynccontextmanager
async def lifespan(app: FastAPI):
    # One session for the whole app. get_storage reads STORIX_* from the
    # environment, so the provider (local, memory, azure, ...) is configured, not
    # hard-coded. DataUrlLayer backfills url() so it works on any backend.
    fs = get_storage().with_layer_missing(DataUrlLayer)
    app.state.fs = fs
    try:
        # Provision application-owned directories once, before requests arrive.
        await fs.mkdir('/uploads', parents=True)
        yield
    finally:
        await fs.close()


app = FastAPI(lifespan=lifespan)


def get_fs(request: Request) -> Storix:
    """The shared storix session, injected into route handlers."""
    return request.app.state.fs


FsDep = Annotated[Storix, Depends(get_fs)]


@app.post('/files/{name}')
async def upload(name: str, file: UploadFile, fs: FsDep) -> dict[str, str]:
    async def chunks():
        while data := await file.read(1024 * 1024):  # 1 MiB at a time
            yield data

    await fs.echo(chunks(), f'/uploads/{name}')  # streamed, bounded memory
    return {'stored': name}


@app.get('/files/{name}')
async def link(name: str, fs: FsDep) -> dict[str, str]:
    # Hand back a short-lived link instead of proxying the bytes.
    return {'url': await fs.url(f'/uploads/{name}', expires_in=600)}
