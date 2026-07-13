# Write a custom layer

A layer is storage middleware. It implements the same backend port, wraps an
inner backend, and changes only the operations it cares about. `LayerBase`
delegates everything else, so the layer keeps working over local, memory,
Azure, and custom backends.

This example records every successful write with its final byte count without
buffering the content:

```python
--8<-- "samples/recipes/custom_layer.py"
```

Run it:

```bash
uv run python samples/recipes/custom_layer.py
```

The important boundary is `write_stream()`. `Storix.echo()` always writes
through that method, even when its input is one `str` or `bytes` value, and
`LayerBase.write()` also funnels whole-object backend writes through it. One
override therefore covers scalar and streamed writes. The counting iterator
observes chunks as the inner backend consumes them, so memory remains bounded.

The log happens after `super().write_stream()` returns, which means it records
successful writes rather than attempts. Production middleware can use the same
shape to emit metrics, tracing spans, durable audit events, content validation,
or notifications. Avoid logging file contents, credentials, or sensitive
metadata.

## Async layers

The async form has the same boundary. Import `LayerBase` from `storix.aio`, take
an `AsyncIterator[bytes]`, make the counting wrapper an async generator, and
`await super().write_stream(...)`. All other composition behavior is identical.

Compose a layer fluently with `fs.with_layer(WriteLogLayer)`, or pass a bound
layer in `Storix(..., layers=[...])`. See [Layers](../guide/layers.md) for layer
ordering, capabilities, sandboxing, and cache composition.
