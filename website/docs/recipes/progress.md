# Progress bars

`ObservabilityLayer` emits a `TransferEvent` per chunk with cumulative
`transferred` bytes. storix never guesses a total: you produced the source, so
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
