"""Guarded release helper for storix.

The manual dance (merge dev -> main, verify, tag, push) is easy to get
wrong - the 0.2.1 mis-tag happened because ``main`` was tagged before it
carried the version bump. This script removes that whole class of error:
the tag is *derived* from ``main``'s own ``pyproject`` version, so you can
only ever tag a version main actually has, and it refuses to run unless
main is clean, pushed, and passing every gate.

    uv run python scripts/release.py check   # gates only, no side effects
    uv run python scripts/release.py tag      # gate + verify + tag + push (confirms)

Before ``tag``, get main ready the usual way:
    git checkout main && git pull && git merge --ff-only dev && git push origin main
"""

from __future__ import annotations

import subprocess

from typing import Annotated

import typer

from rich.console import Console
from rich.panel import Panel


app = typer.Typer(add_completion=False, help='Guarded release for storix.')
console = Console()
err = Console(stderr=True)


def _run(*cmd: str, check: bool = True) -> str:
    result = subprocess.run(cmd, check=False, text=True, capture_output=True)
    if check and result.returncode != 0:
        err.print(f'[red]$ {" ".join(cmd)}[/red]\n{result.stderr or result.stdout}')
        raise typer.Exit(1)
    return result.stdout.strip()


def _abort(msg: str) -> None:
    err.print(f'[red]✗ {msg}[/red]')
    raise typer.Exit(1)


def _tracked_py() -> list[str]:
    return _run('git', 'ls-files', '*.py').split()


def _gates() -> None:
    """Run every CI gate locally, on tracked files only (as CI sees them)."""
    files = _tracked_py()
    gates: list[tuple[str, list[str]]] = [
        ('format', ['uv', 'run', 'ruff', 'format', '--check', *files]),
        ('lint', ['uv', 'run', 'ruff', 'check', *files]),
        ('codegen drift', ['uv', 'run', 'python', 'scripts/unasync.py', '--check']),
        ('tests', ['uv', 'run', 'pytest', '-q']),
        ('build', ['uv', 'build']),
    ]
    for name, cmd in gates:
        with console.status(f'{name}…'):
            result = subprocess.run(cmd, check=False, text=True, capture_output=True)
        if result.returncode != 0:
            err.print(result.stdout[-2000:] or result.stderr[-2000:])
            _abort(f'gate failed: {name}')
        console.print(f'  [green]✓[/green] {name}')


@app.command()
def check() -> None:
    """Run the full release preflight - no side effects."""
    _gates()
    console.print('[green]✓ all preflight gates passed[/green]')


@app.command()
def tag(
    *, yes: Annotated[bool, typer.Option('--yes', '-y', help='skip confirm')] = False
) -> None:
    """Gate, verify main is release-ready, then tag + push it."""
    version = _run('uv', 'version', '--short')
    tagname = f'v{version}'

    branch = _run('git', 'rev-parse', '--abbrev-ref', 'HEAD')
    if branch != 'main':
        _abort(
            f"on '{branch}', not 'main'. Get main ready first:\n"
            '  git checkout main && git pull && '
            'git merge --ff-only dev && git push origin main'
        )
    if _run('git', 'status', '--porcelain'):
        _abort('working tree is not clean')

    _run('git', 'fetch', '--quiet', 'origin', 'main')
    if _run('git', 'rev-parse', 'HEAD') != _run('git', 'rev-parse', 'origin/main'):
        _abort('local main != origin/main - push or pull it first')

    # the guard that would have caught 0.2.1: the tag is main's own version,
    # so a tag that already exists means main is stale (bump not merged yet).
    existing = _run('git', 'tag', '-l', tagname)
    if existing:
        _abort(
            f'{tagname} already exists - main is at {version}. '
            'Did you merge the version bump (dev -> main) yet?'
        )

    _gates()

    short = _run('git', 'rev-parse', '--short', 'HEAD')
    console.print(
        Panel(f'Release [bold]{tagname}[/bold] from main @ {short}', expand=False)
    )
    if not yes and not typer.confirm(f'Tag and push {tagname}?'):
        raise typer.Exit(0)

    _run('git', 'tag', tagname)
    _run('git', 'push', 'origin', tagname)
    console.print(
        f'[green]✓ pushed {tagname}[/green] - the release workflow is now running '
        '(build -> PyPI -> GitHub release).'
    )


if __name__ == '__main__':
    app()
