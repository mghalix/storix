"""Switch storage providers without touching your code.

The payoff of the hexagonal core: your logic depends on `Storix`, never
on a provider. Swap local <-> azure <-> anything by config alone; the
pipeline function below never changes.

Run:  uv run python samples/switch_providers.py
"""

import asyncio
import os

from storix.aio import Storix, get_storage


async def run_pipeline(fs: Storix) -> int:
    """Provider-agnostic: identical against local, azure, memory, ..."""
    await fs.mkdir('/reports', parents=True)
    await fs.echo(b'quarterly numbers', '/reports/q1.txt')
    return await fs.du('/reports')


async def main() -> None:
    # 1. Explicit switch - the provider is just a value:
    for provider in ('local', 'memory'):  # add 'azure' with creds
        fs = get_storage(provider) if provider != 'memory' else _memory_fs()
        size = await run_pipeline(fs)
        print(f'{provider:8} -> {size} bytes')

    # 2. Config-driven switch - flip one env var, zero code change:
    os.environ['STORIX_PROVIDER'] = 'local'
    fs = get_storage()  # reads STORIX_PROVIDER (+ STORIX_<PROVIDER>_* config)
    print('env-driven -> provider is', type(fs.backend).__name__)

    # In production the whole app just calls get_storage(); deployment
    # sets STORIX_PROVIDER=azure and STORIX_AZURE_* and nothing else moves.


def _memory_fs() -> Storix:
    # memory has no env config, so build it directly (still a Storix)
    from storix.aio.backends import MemoryBackend

    return Storix(MemoryBackend())


if __name__ == '__main__':
    asyncio.run(main())
