"""``sx update`` and ``sx doctor`` (ADR 0031 D11, D12).

Neither command owns knowledge of its own. ``update`` drives the package
manager that installed storix and never rewrites its own files; ``doctor``
prints what the loader, the factory, and the updater already know, so a
diagnosis can never disagree with the thing it is diagnosing.
"""

from __future__ import annotations

import os
import subprocess
import sys

from importlib import metadata
from typing import TYPE_CHECKING, Annotated

import typer

from storix.config import (
    PROVIDER_MODELS,
    available_profiles,
    config_provenance,
    configured_profile,
    find_project_config,
    find_user_config,
    installation_kind,
    is_secret,
    resolve_profile,
    upgrade_command,
)
from storix.errors import ConfigurationError

from .render import console, err
from .state import (
    _session,  # pyright: ignore[reportPrivateUsage]
    resolve_provider,
)


if TYPE_CHECKING:
    from collections.abc import Sequence


PYPI_JSON = 'https://pypi.org/pypi/storix/json'
"""Where ``--check`` asks what the latest release is."""


def installed_version() -> str:
    """The running storix version, from package metadata."""
    return metadata.version('storix')


def _run(argv: Sequence[str]) -> int:
    """Run a command as plain argv, no shell, streaming its output."""
    console.print(f'[dim]$ {" ".join(argv)}[/dim]')
    return subprocess.run(argv, check=False).returncode  # noqa: S603


def latest_version() -> str | None:
    """The newest release on PyPI, or None when it cannot be reached."""
    import json
    import urllib.error
    import urllib.request

    try:
        with urllib.request.urlopen(PYPI_JSON, timeout=10) as response:  # noqa: S310
            return str(json.load(response)['info']['version'])
    except (urllib.error.URLError, KeyError, ValueError, TimeoutError):
        return None


def update(
    *,
    check: Annotated[
        bool,
        typer.Option('--check', help='report current and latest, change nothing'),
    ] = False,
) -> None:
    """Upgrade storix through the package manager that installed it."""
    current = installed_version()
    if check:
        latest = latest_version()
        if latest is None:
            err.print('[yellow]sx: could not reach PyPI to check for updates[/yellow]')
            raise typer.Exit(1)
        console.print(f'installed [cyan]{current}[/cyan]  latest [cyan]{latest}[/cyan]')
        argv = upgrade_command()
        if latest != current and argv is not None:
            console.print(f'[green]run:[/green] {" ".join(argv)}')
        return

    kind = installation_kind()
    argv = upgrade_command()
    if kind != 'uv-tool' or argv is None:
        manual = ' '.join(argv) if argv else 'pip install --upgrade storix'
        err.print(
            f'[yellow]sx: storix runs from a {kind} install, which sx will not '
            f'modify. Upgrade it the way you installed it:\n  {manual}[/yellow]'
        )
        raise typer.Exit(2)
    raise typer.Exit(_run(argv))


def doctor(
    *,
    updates: Annotated[
        bool,
        typer.Option('--updates', help='also ask PyPI whether a newer release exists'),
    ] = False,
) -> None:
    """Report how storix is installed, configured, and what it can reach."""
    console.print('[bold]storix[/bold]')
    console.print(f'  version      {installed_version()}')
    console.print(f'  installed as {installation_kind()}')
    console.print(f'  python       {sys.version.split()[0]} ({sys.executable})')

    console.print('\n[bold]providers[/bold]')
    for provider in sorted(PROVIDER_MODELS):
        console.print(f'  {provider:8} {_extra_state(provider)}')

    console.print('\n[bold]configuration[/bold]')
    _report_config()

    console.print('\n[bold]tools[/bold]')
    editor = os.environ.get('VISUAL') or os.environ.get('EDITOR')
    console.print(f'  editor       {editor or "unset ($VISUAL / $EDITOR)"}')

    if updates:
        latest = latest_version()
        console.print('\n[bold]updates[/bold]')
        if latest is None:
            console.print('  could not reach PyPI')
        elif latest == installed_version():
            console.print('  up to date')
        else:
            argv = upgrade_command() or []
            console.print(f'  {latest} available: {" ".join(argv)}')


def _extra_state(provider: str) -> str:
    """Whether a provider's optional dependency is importable here."""
    from storix import available_providers

    return (
        '[green]ready[/green]'
        if provider in available_providers()
        else '[dim]extra not installed[/dim]'
    )


def _report_config() -> None:
    """Print discovered files, the selection, and the effective provider."""
    try:
        for label, disc in (
            ('project', find_project_config()),
            ('user', find_user_config()),
        ):
            console.print(f'  {label:8} {disc.path if disc else "[dim]none[/dim]"}')
        profile = _session.profile or configured_profile()
        if profile:
            resolved = resolve_profile(profile, _session.environment)
            stage = resolved.environment or 'none'
            console.print(f'  profile      {profile} (stage: {stage})')
        else:
            available = ', '.join(sorted(available_profiles())) or 'none defined'
            console.print(f'  profile      none selected (available: {available})')
        provider = resolve_provider(None, profile)
        console.print(f'  provider     {provider}')
        _report_fields(provider)
    except ConfigurationError as exc:
        err.print(f'  [red]{exc}[/red]')


def _report_fields(provider: str) -> None:
    """Print where each effective field comes from, and what is missing."""
    model = PROVIDER_MODELS.get(provider)
    if model is None:
        return
    provenance = config_provenance(provider)
    for field, source in sorted(provenance.items()):
        marker = ' [dim](secret)[/dim]' if is_secret(model, field) else ''
        console.print(f'    {field:20} [dim]<- {source}[/dim]{marker}')
    missing = sorted(
        name
        for name, info in model.model_fields.items()
        if info.is_required() and name not in provenance
    )
    if missing:
        console.print(f'    [yellow]missing:[/yellow] {", ".join(missing)}')
