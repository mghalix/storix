"""Upload and download progress bars from ObservabilityLayer transfer events."""

from typing import Final

from rich.progress import Progress

from storix import ObservabilityLayer, TransferEvent, get_storage


CHUNK_SIZE: Final[int] = 64 * 1024
"""Transfer chunk size; one TransferEvent fires per chunk."""


def main() -> None:
    payload = b'\0' * (64 * 1024 * 1024)  # you produced the source: the total is yours
    chunks = (payload[i : i + CHUNK_SIZE] for i in range(0, len(payload), CHUNK_SIZE))

    with Progress() as progress:
        tasks = {
            'write': progress.add_task('uploading', total=len(payload)),
            'read': progress.add_task('downloading', total=len(payload)),
        }

        def on_event(event: TransferEvent) -> None:
            progress.update(tasks[event.op], completed=event.transferred)

        fs = get_storage('memory').with_layer(ObservabilityLayer, sink=on_event)
        fs.echo(chunks, '/upload.bin')
        for _chunk in fs.stream('/upload.bin', chunk_size=CHUNK_SIZE):
            pass  # hand each chunk to its real consumer here


if __name__ == '__main__':
    main()
