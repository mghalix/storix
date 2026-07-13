"""Five minutes of storix, sync flavor (async twin: quickstart_async.py).

Runs fully in memory - no disk touched. Swap MemoryBackend for
LocalBackend('~/storix-data') or AzureBackend(...) and nothing else changes.
"""

from storix import Storix
from storix.backends import MemoryBackend


def main() -> None:
    fs = Storix(MemoryBackend())

    fs.mkdir('/docs')
    fs.echo(b'hello, storix!', '/docs/readme.txt')
    print('cat     ->', fs.cat('/docs/readme.txt'))

    fs.cd('/docs')  # sessions have a cwd, like a shell
    fs.touch('a.txt', 'b.txt', '.hidden')  # variadic, like real touch
    print('ls      ->', fs.ls())  # dotfiles hidden, like real ls
    print('ls -a   ->', fs.ls(all=True))

    fs.mkdir('/archive')
    fs.mv('a.txt', 'b.txt', '/archive')  # last argument is the destination
    print('archive ->', fs.ls('/archive'))

    print('du /    ->', fs.du('/'), 'bytes')
    print('stat    ->', fs.stat('readme.txt'))

    fs.rm('/archive', recursive=True)  # rm -r; rmdir is strictly empty dirs
    print('after rm-r ->', fs.ls('/'))


if __name__ == '__main__':
    main()
