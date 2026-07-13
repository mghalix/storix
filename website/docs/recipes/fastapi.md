# FastAPI

Wire a storix session into FastAPI with dependency injection: create one session
for the app's lifetime, inject it into handlers, and stream uploads straight to
storage.

## The pattern

- **One session, shared.** Build it in the `lifespan` and close it on shutdown,
  so setup is paid once and every request reuses it.
- **Provision once at startup.** Create application-owned directories before
  the app accepts requests. `mkdir(..., parents=True)` is idempotent across
  restarts.
- **Inject with `Depends`.** A tiny `get_fs` dependency hands the session to any
  route, which keeps handlers testable: override it with a `MemoryBackend`
  session in tests, no disk and no cloud.
- **Stream, do not buffer.** `echo` takes an async iterator, so an upload flows
  to storage a chunk at a time and memory stays flat regardless of file size.
- **Hand back links when the provider supports them.** Azure returns a
  short-lived presigned link. `DataUrlLayer` keeps the example portable by
  returning an inline `data:` URL on local and memory storage.

## The full example

```python
--8<-- "samples/recipes/fastapi_di.py"
```

Run it:

```bash
uv run --with "fastapi[standard]" fastapi dev samples/recipes/fastapi_di.py
```

Then upload and retrieve a link:

```bash
curl -F "file=@report.csv" http://127.0.0.1:8000/files/report.csv
curl http://127.0.0.1:8000/files/report.csv
```

!!! warning "Large local files"

    Azure creates a presigned URL without reading the file. The portable
    `DataUrlLayer` fallback must read and base64-encode the complete file, so use
    it for small local or in-memory files, not large downloads.

!!! tip "Testing the routes"

    Because the session is a dependency, a test overrides `get_fs` to return a
    `Storix(MemoryBackend())`. The routes run against in-memory storage with no
    disk, no cloud, and no mocking.

This example is a real, syntax-checked file in the repository
([`samples/recipes/fastapi_di.py`](https://github.com/mghalix/storix/blob/main/samples/recipes/fastapi_di.py)),
embedded here so the page never drifts from working code.
