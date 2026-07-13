"""Log successful writes with a small storix middleware layer."""

import logging

from collections.abc import Iterator, Mapping
from pathlib import PurePosixPath

from storix import LayerBase, get_storage
from storix.types import EchoMode


logger = logging.getLogger(__name__)


class WriteLogLayer(LayerBase):
    """Record successful writes and their streamed byte count."""

    def write_stream(
        self,
        path: PurePosixPath,
        data: Iterator[bytes],
        *,
        chunk_size: int | None = None,
        mode: EchoMode,
        content_type: str | None,
        metadata: Mapping[str, str] | None = None,
    ) -> None:
        written = 0

        def counted_chunks() -> Iterator[bytes]:
            nonlocal written
            for chunk in data:
                written += len(chunk)
                yield chunk

        super().write_stream(
            path,
            counted_chunks(),
            chunk_size=chunk_size,
            mode=mode,
            content_type=content_type,
            metadata=metadata,
        )
        logger.info('stored path=%s bytes=%d mode=%s', path, written, mode)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    fs = get_storage('memory').with_layer(WriteLogLayer)
    fs.echo([b'hello ', b'from ', b'a layer'], '/hello.txt')


if __name__ == '__main__':
    main()
