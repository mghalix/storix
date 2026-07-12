# FastAPI

Wire a storix session into FastAPI with dependency injection: create one session
for the app's lifetime, inject it into handlers, and stream uploads straight to
storage.

## The pattern

- **One session, shared.** Build it in the `lifespan` and close it on shutdown,
  so setup is paid once and every request reuses it.
- **Inject with `Depends`.** A tiny `get_fs` dependency hands the session to any
  route, which keeps handlers testable: override it with a `MemoryBackend`
  session in tests, no disk and no cloud.
- **Stream, do not buffer.** `echo` takes an async iterator, so an upload flows
  to storage a chunk at a time and memory stays flat regardless of file size.
- **Hand back links, not bytes.** `url()` returns a short-lived presigned link (a
  `data:` URL on backends without native presigning, via `DataUrlLayer`).

## The full example

```python
--8<-- "samples/recipes/fastapi_di.py"
```

Run it:

```bash
uv run --with "fastapi[standard]" fastapi dev samples/recipes/fastapi_di.py
```

Then `POST /files/report.csv` with a file body, and `GET /files/report.csv` to get
a link back.

!!! tip "Testing the routes"

    Because the session is a dependency, a test overrides `get_fs` to return a
    `Storix(MemoryBackend())`. The routes run against in-memory storage with no
    disk, no cloud, and no mocking.

This example is a real, syntax-checked file in the repository
([`samples/recipes/fastapi_di.py`](https://github.com/mghalix/storix/blob/main/samples/recipes/fastapi_di.py)),
embedded here so the page never drifts from working code.
