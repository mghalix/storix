# Test with storix

`MemoryBackend` is a full in-process backend, so tests run against real storage
semantics with no disk, no cloud, and no mocking. `scratch()` isolates a test's
writes in a disposable workspace.

```python
--8<-- "samples/recipes/testing_storix.py"
```

The same trick makes application code testable. If your code takes a `Storix`
(or gets one from a dependency, as in the [FastAPI recipe](fastapi.md)), a test
hands it a `Storix(MemoryBackend())` and runs the real code path against in-memory
storage.

!!! tip "Sandboxing untrusted paths"

    When a test (or a request) works with caller-supplied paths, wrap the session
    in a `SandboxLayer` so a stray `..` cannot escape the intended directory. The
    jail holds even against paths that bypass the core.
