# Progress bars

`ObservabilityLayer` emits a `TransferEvent` per chunk with cumulative
`transferred` bytes for that stream. storix never guesses a total: you produced the source, so
the total is yours (a local file's `stat().st_size`, an HTTP upload's
`Content-Length`), and a percentage is your division to make. That one contract
drives any UI: a bar when you have a total, a counter when you do not.

## Drive a rich bar

You own the payload, so you own the total; the sink only moves the bar:

```bash
uv add rich
```

```python
--8<-- "samples/observability_progress.py"
```

Attach the layer outermost (the last `with_layer`) so it counts the full
logical transfer, whatever other layers sit below it.

!!! warning "The demo materializes its payload"

    The sample builds its whole 64 MiB payload as one `bytes` object up
    front, purely to keep the example short and the total known. Multiply
    the size by 50 for a slow-motion bar, but expect roughly 3 GiB of RAM
    for that payload object alone. The cost is the demo's source
    construction, not storix: `echo` and `stream` move data chunk by chunk
    either way, and a real application would stream from a file or socket
    without ever holding the total in memory.

## One file, several streams

`transferred` is cumulative *per stream*, and a parallel `download()` reads one
file through several ranges at once, each counting from zero. The event carries
`offset` - where its stream starts in the file - so a sink that accumulates a
whole transfer keys on the pair:

```python
seen: dict[tuple[PurePosixPath, int], int] = {}
completed = 0


def on_event(event: TransferEvent) -> None:
    global completed
    stream = (event.path, event.offset)
    completed += event.transferred - seen.get(stream, 0)
    seen[stream] = event.transferred
```

Keying on `path` alone silently undercounts: with eight ranges in flight the
bar reports one range's bytes rather than the file's. `offset` is 0 for a
whole-file `stream()` or `echo()`, so a sink written this way is correct for
every transfer, sequential or parallel.

## Stop a transfer from the sink

The sink runs once per chunk, in whichever thread produced it, which makes it
the one place a transfer can be stopped from. Raise, and the exception unwinds
that stream; with a bulk transfer running several files at once, the others
stop at their own next chunk:

```python
import threading

stop = threading.Event()


class Stopped(Exception):
    """Raised to unwind a transfer the caller asked to stop."""


def on_event(event: TransferEvent) -> None:
    if stop.is_set():
        raise Stopped
    bar.update(event.transferred)
```

This is exactly how `sx` implements Ctrl+C: the signal handler sets an event
instead of raising, and the sink turns it into an exception inside every
worker. A partially written destination is the caller's to clean up - storix
does not guess whether a half-file is worth keeping.

## No total? Count bytes

A truly unbounded source (a generator, a pipe) has no end to know. Render a
counter or a spinner instead of a bar; `transferred` is still exact:

```python
from storix import ObservabilityLayer, TransferEvent, get_storage


def on_event(event: TransferEvent) -> None:
    print(f"\r{event.op} {event.path}: {event.transferred:,} bytes", end="")


fs = get_storage("local").with_layer(ObservabilityLayer, sink=on_event)
```

## Async sinks

With `storix.aio` the sink may be a coroutine function (push SSE frames,
websocket messages, ...); it is awaited once per chunk:

```python
async def on_event(event: TransferEvent) -> None:
    await queue.put(event)
```
