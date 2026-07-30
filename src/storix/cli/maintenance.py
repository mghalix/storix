"""``sx update``, ``sx install`` and ``sx doctor`` (ADR 0031 D11, D12, D15).

No command here owns knowledge of its own. ``update`` and ``install``
drive the package manager that installed storix and never rewrite its own
files; the extra set they work from is uv's receipt, not a record storix
keeps. ``doctor`` prints what the loader, the factory, and the updater
already know, so a diagnosis can never disagree with the thing it is
diagnosing.
"""

from __future__ import annotations

import os
import subprocess
import sys

from importlib import metadata
from typing import TYPE_CHECKING, Annotated

import typer

from rich.markup import escape

from storix.config import (
    PROVIDER_MODELS,
    available_profiles,
    config_provenance,
    declared_extras,
    extra_installed,
    find_project_config,
    find_user_config,
    installation_kind,
    installed_extras,
    is_secret,
    resolve_profile,
    upgrade_command,
)
from storix.errors import ConfigurationError

from .render import console, err
from .state import resolve_provider, selection


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


def _run_quietly(argv: Sequence[str], label: str) -> int:
    """Run a command behind a spinner, showing its output only on failure.

    ``sx update`` should read as one tool updating itself, not as a wrapper
    that shells out - the package manager's resolve log is an
    implementation detail while it is working. It stops being one the
    moment it fails, so a non-zero exit prints everything, unedited,
    together with the command that produced it.

    Args:
        argv: The command to run.
        label: What to show beside the spinner, in the present tense.
    """
    with console.status(f'[cyan]{label}[/cyan]', spinner='dots'):
        done = subprocess.run(  # noqa: S603
            argv, check=False, capture_output=True, text=True
        )
    if done.returncode != 0:
        err.print(f'[red]sx: {label} failed[/red]\n[dim]$ {" ".join(argv)}[/dim]')
        err.print(done.stdout + done.stderr, markup=False, highlight=False)
    return done.returncode


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
    version: Annotated[
        str | None,
        typer.Argument(
            help='exact version to move to (e.g. 0.5.1); the newest release '
            'when omitted'
        ),
    ] = None,
    *,
    check: Annotated[
        bool,
        typer.Option('--check', help='report current and latest, change nothing'),
    ] = False,
    verbose: Annotated[
        bool,
        typer.Option('-v', '--verbose', help="show the package manager's own output"),
    ] = False,
) -> None:
    """Upgrade storix through the package manager that installed it.

    With no argument this moves to the newest release. Naming a version
    moves to exactly that one, which is also how to go back.
    """
    current = installed_version()
    if check:
        latest = latest_version()
        if latest is None:
            err.print('[yellow]sx: could not reach PyPI to check for updates[/yellow]')
            raise typer.Exit(1)
        console.print(f'installed [cyan]{current}[/cyan]  latest [cyan]{latest}[/cyan]')
        if latest != current:
            console.print(f'[green]run:[/green] {" ".join(upgrade_command(version))}')
        return

    kind = installation_kind()
    argv = upgrade_command(version)
    if kind != 'uv-tool':
        manual = ' '.join(argv)
        err.print(
            f'[yellow]sx: storix runs from a {kind} install, which sx will not '
            f'modify. Upgrade it the way you installed it:\n  {manual}[/yellow]'
        )
        raise typer.Exit(2)

    target = version or latest_version()
    if version is None and target == current:
        console.print(f'already on [cyan]{current}[/cyan], the newest release')
        raise typer.Exit(0)
    _warn_if_backwards(current, target)
    if verbose:
        raise typer.Exit(_run(argv))

    moving = f'{current} -> {target}' if target else f'from {current}'
    code = _run_quietly(argv, f'updating storix ({moving})')
    if code == 0:
        console.print(f'[green]updated[/green] storix {moving}')
    raise typer.Exit(code)


def _warn_if_backwards(current: str, target: str | None) -> None:
    """Say so when a named version moves backwards rather than forwards.

    ``update`` reads as forwards, and one command that moves either way is
    still better than a second command whose only difference is comparing
    two numbers. Naming the direction is what removes the surprise, and an
    older storix can reject configuration keys the current one wrote, which
    is the part worth a warning rather than a silent success.

    Args:
        current: The installed version.
        target: The version being moved to, if it is known.
    """
    if target is None:
        return
    try:
        backwards = _as_release(target) < _as_release(current)
    except ValueError:
        # a version storix cannot order (a local or pre-release spelling):
        # say nothing rather than guess a direction
        return
    if backwards:
        console.print(f'[yellow]downgrade[/yellow] {current} -> {target}')
        console.print(
            '[dim]an older storix may reject configuration keys this one accepts[/dim]'
        )


def _as_release(version: str) -> tuple[int, ...]:
    """Parse a plain ``MAJOR.MINOR.PATCH`` into comparable parts.

    Args:
        version: The version string to order.

    Raises:
        ValueError: If it is not three dot-separated integers, which is
            every version storix itself publishes (ADR 0021).
    """
    parts = version.split('.')
    if len(parts) != 3:  # noqa: PLR2004 - major.minor.patch, not a tunable
        msg = f'not a release version: {version}'
        raise ValueError(msg)
    return tuple(int(part) for part in parts)


def _extras_argument(extras: str) -> list[str]:
    """Split and validate a comma-separated extras argument.

    Args:
        extras: The argument as typed, for example ``s3`` or ``azure,gcs``.

    Returns:
        The named extras, in the order given, without duplicates.

    Raises:
        Exit: If a name is not an extra this distribution declares. uv
            would otherwise spend a full resolve before saying so, and its
            message names a package rather than the typo.
    """
    declared = declared_extras()
    named = [name.strip() for name in extras.split(',') if name.strip()]
    unknown = [name for name in named if name not in declared]
    if unknown or not named:
        known = ', '.join(sorted(declared - {'core'}))
        subject = f'no such extra: {", ".join(unknown)}' if unknown else 'name an extra'
        err.print(f'[red]sx: {subject}[/red]\navailable: {known}')
        raise typer.Exit(2)
    return list(dict.fromkeys(named))


def _reinstall(extras: frozenset[str]) -> None:
    """Recreate this tool installation with exactly ``extras``.

    Pinned to the running version: adding a backend is not a moment to
    also move versions, which is what ``sx update`` is for. ``--force`` is
    what makes uv rebuild an environment that already exists, and is the
    same flag the published installer uses.

    Args:
        extras: The complete extra set the installation should end up with.

    Raises:
        Exit: Always - with uv's exit code, or 2 when this installation is
            not one storix may rewrite.
    """
    kind = installation_kind()
    if kind != 'uv-tool':
        bundle = ','.join(sorted(extras))
        err.print(
            f'[yellow]sx: storix runs from a {kind} install, which sx will not '
            f'modify. Change its extras the way you installed it:\n'
            f'  pip install "storix[{bundle}]"[/yellow]'
        )
        raise typer.Exit(2)
    spec = f'storix[{",".join(sorted(extras))}]=={installed_version()}'
    raise typer.Exit(_run(['uv', 'tool', 'install', '--force', spec]))


def install(
    extras: Annotated[
        str,
        typer.Argument(help='provider extras to add, comma separated (s3, azure)'),
    ],
) -> None:
    """Add provider extras to this installation, keeping the ones it has."""
    named = _extras_argument(extras)
    # cli is what makes sx runnable at all: whatever the receipt says, an
    # installation sx just rewrote has to still have a command in it
    target = installed_extras() | {'cli', *named}
    if target == installed_extras():
        console.print(f'already installed: {", ".join(named)}')
        return
    _reinstall(target)


def uninstall(
    extras: Annotated[
        str,
        typer.Argument(help='provider extras to remove, comma separated'),
    ],
) -> None:
    """Remove provider extras from this installation, keeping the rest.

    Removes extras only. To remove storix itself: ``uv tool uninstall
    storix``.
    """
    named = _extras_argument(extras)
    if 'cli' in named:
        err.print(
            '[red]sx: the cli extra is what makes sx runnable; removing it '
            'would leave no command to reinstall it with.[/red]\n'
            'To remove storix entirely: uv tool uninstall storix'
        )
        raise typer.Exit(2)
    current = installed_extras()
    target = current - set(named)
    if target == current:
        console.print(f'not installed: {", ".join(named)}')
        return
    _reinstall(target)


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

    console.print('\n[bold]provider extras[/bold] [dim](importable here)[/dim]')
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
    """Whether a provider's optional dependency is importable here.

    Deliberately not "ready": nothing here opens a connection or checks a
    credential, so a word that implies either would be a diagnosis storix
    has not made. Credentials show up under ``configuration``.

    Deliberately not ``available_providers()`` either, which names what
    ``get_storage`` accepts rather than what this environment can import,
    and so reported every built-in provider as installed.
    """
    return (
        '[green]installed[/green]'
        if extra_installed(provider)
        else '[dim]not installed[/dim]'
    )


def _report_config() -> None:
    """Print discovered files, the selection, and the effective provider."""
    try:
        for label, disc in (
            ('project', find_project_config()),
            ('user', find_user_config()),
        ):
            console.print(f'  {label:8} {disc.path if disc else "[dim]none[/dim]"}')
        profile, environment = selection()
        if profile:
            resolved = resolve_profile(profile, environment)
            stage = resolved.environment or 'none'
            console.print(f'  profile      {profile} (stage: {stage})')
        else:
            available = ', '.join(sorted(available_profiles())) or 'none defined'
            console.print(f'  profile      none selected (available: {available})')
        provider = resolve_provider(None, profile)
        console.print(f'  provider     {provider}')
        _report_fields(provider, profile, environment)
    except ConfigurationError as exc:
        err.print(f'  [red]{escape(str(exc))}[/red]')


def _report_fields(
    provider: str, profile: str | None = None, environment: str | None = None
) -> None:
    """Print where each effective field comes from, and what is missing.

    Args:
        provider: The provider whose fields to report.
        profile: The selected profile, so its settings are attributed to it
            rather than reading as untouched defaults.
        environment: The selected stage overlay, if any.
    """
    model = PROVIDER_MODELS.get(provider)
    if model is None:
        return
    provenance = config_provenance(provider, profile=profile, environment=environment)
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
