# Transfers

`push` and `pull` move files between the local host and the provider, drawing a
live progress bar:

```bash
sx push ./video.mp4 /media/video.mp4   # host -> provider
sx pull /media/video.mp4 ./video.mp4   # provider -> host
```

Both stream, so a file larger than memory moves fine. Uploads detect a content
type (from the extension, else by sniffing the head) and set it on backends
that support it.

The bar is the [`ObservabilityLayer`](../recipes/progress.md), which `sx`
attaches around `upload` and `download` for you. The same layer is available in
code when you want the events somewhere other than a terminal.

## Both ends create their parents

`push` creates missing destination parents inside the storage root
(directories, or key prefixes on an object store), and `pull` creates missing
local ones. So this works with no prior `mkdir`:

```bash
sx -p s3 push ./video.mp4 /storix/demos/video.mp4
```

What neither does is create the storage root itself. The configured S3/R2
bucket, Azure container, or ADLS filesystem must already exist, because
creating one is a provider control-plane operation rather than a filesystem
operation. That is what [`sx provision`](commands.md#provisioning-the-storage-root)
is for, and where it cannot help it says so.

## Tuning a transfer

`sx` reads the same `STORIX_*` environment your application does, so the
transfer knobs apply to the CLI without a separate config surface:

```bash
STORIX_MAX_TRANSFER_RANGES=1 sx pull /media/movie.mkv   # one stream per file
STORIX_AZURE_READ_PREFETCH_SIZE=4194304 sx pull /media  # less memory per stream
STORIX_S3_READ_CHUNK_SIZE=8388608 sx -p s3 pull /media  # fewer, larger requests
```

What each one trades away - memory per in-flight transfer against requests per
byte, and speed against transaction count - is in
[Tune transfers](../recipes/transfers.md).

## Stopping a transfer

Ctrl+C asks a running `push` or `pull` to stop, and it actually stops: every
stream unwinds at its next chunk boundary, the files that had not started never
start, and no worker keeps running behind your prompt. A half-written local
file is removed rather than left looking complete, so `pull` never leaves a
truncated file where a whole one belongs. The command reports it and exits
`130`, the shell's usual code for an interrupt:

```console
/ ❯ pull /media/season-1
stopping...
pull: stopped
```

A second Ctrl+C skips the graceful path and interrupts immediately.

### What a stopped push leaves behind

One asymmetry to know: a stopped `pull` removes the destination it was writing,
a stopped `push` does not. What it leaves depends on the backend, because each
one commits a write differently (measured, mid-upload stop):

| backend | destination after a stopped push |
| --- | --- |
| Azure ADLS Gen2 | the path exists, **length 0** - appended bytes are staged and never flushed |
| S3, GCS, Azure Blob | whatever the engine committed; an object store publishes on completion, so an interrupted upload may also leave an incomplete multipart upload behind |
| Local | the bytes written so far |

In every case the previous contents of that path are already gone: a `push`
truncates its destination when it opens it, so stopping does not preserve what
was there. storix does not then delete the path, for two reasons. The first is
that deleting cannot restore what the truncate destroyed, so it would trade a
wrong file for a missing one while the user is asking storix to *stop* doing
things. The second is that on an object store there may be nothing to delete
and the real leftover is an incomplete multipart upload, which the storage port
has no way to address.

Re-running the same `push` overwrites the destination. If you need a stop (or a
crash, or a dropped connection) to leave the destination untouched, that is
atomic writes - `echo(atomic=True)`, write-temp-then-move - which is on the
roadmap and not implemented today.
