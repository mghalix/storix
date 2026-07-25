"""``sx config``: see, explain, and edit configuration (ADR 0031 D10).

Presentation only. Discovery, precedence, validation, the secret policy,
and the writes themselves live in ``storix.config``, because ``sx`` is a
driving adapter over the library and must not grow a second copy of the
rules it displays.
"""

from __future__ import annotations

import os
import subprocess

from typing import Annotated, Any, cast

import typer

from storix.config import (
    PROVIDER_MODELS,
    DiscoveredConfig,
    Scope,
    available_profiles,
    find_project_config,
    find_user_config,
    is_secret,
    project_config_path,
    scope_path,
    set_setting,
    split_key,
    unset_setting,
    user_config_path,
)
from storix.errors import ConfigurationError

from .render import console, err


REDACTED = '***'
"""What a secret's value is shown as, in every read command."""

config_app = typer.Typer(
    name='config',
    help='See, explain, and edit storix configuration.',
    no_args_is_help=True,
)

_SCOPE = Annotated[
    str, typer.Option('--scope', help='user | project (default: project)')
]


def _scope(value: str) -> Scope:
    """Validate a ``--scope`` value.

    Raises:
        SystemExit: If the scope is neither ``user`` nor ``project``.
    """
    if value not in {'user', 'project'}:
        message = f"sx: --scope must be 'user' or 'project', not {value!r}"
        raise SystemExit(message)
    return 'user' if value == 'user' else 'project'


def _die(exc: ConfigurationError) -> None:
    """Report a configuration failure as one line and exit non-zero.

    Raises:
        typer.Exit: Always, with status 1.
    """
    err.print(f'[red]sx: {exc}[/red]')
    raise typer.Exit(1)


def _redacted(document: dict[str, Any]) -> dict[str, Any]:
    """A copy of a config document with every secret value replaced.

    Covers profiles as well as the top-level provider tables: a profile
    carries the same fields, so a user-scope profile holding a literal
    credential must not be printed either.
    """
    out: dict[str, Any] = {}
    for key, value in document.items():
        if key == 'profiles' and isinstance(value, dict):
            table = cast('dict[str, Any]', value)
            out[key] = {name: _redacted_profile(p) for name, p in table.items()}
            continue
        if PROVIDER_MODELS.get(key) is not None and isinstance(value, dict):
            out[key] = _redacted_section(cast('dict[str, Any]', value), key)
        else:
            out[key] = value
    return out


def _redacted_section(section: dict[str, Any], provider: str) -> dict[str, Any]:
    """One provider table with its secret fields replaced."""
    model = PROVIDER_MODELS.get(provider)
    if model is None:
        return dict(section)
    return {
        field: (REDACTED if is_secret(model, field) else value)
        for field, value in section.items()
    }


def _redacted_profile(profile: Any) -> Any:
    """One profile, and each of its stages, with secret fields replaced."""
    if not isinstance(profile, dict):
        return profile
    table = cast('dict[str, Any]', profile)
    provider = str(table.get('provider', ''))
    out = _redacted_section(table, provider)
    stages = table.get('environments')
    if isinstance(stages, dict):
        overlays = cast('dict[str, Any]', stages)
        out['environments'] = {
            name: _redacted_section(cast('dict[str, Any]', stage), provider)
            for name, stage in overlays.items()
            if isinstance(stage, dict)
        }
    return out


def _render(document: dict[str, Any], *, prefix: str = '') -> None:
    """Print a config document as dotted keys, deepest last."""
    for key, value in document.items():
        path = f'{prefix}{key}'
        if isinstance(value, dict):
            _render(cast('dict[str, Any]', value), prefix=f'{path}.')
        else:
            console.print(f'[cyan]{path}[/cyan] = {value!r}')


@config_app.command('path')
def config_path() -> None:
    """Print the config files storix reads, and whether they exist."""
    project, project_exists = project_config_path()
    user = user_config_path()
    for label, path, exists in (
        ('project', project, project_exists),
        ('user', user, user.is_file()),
    ):
        state = '[green]exists[/green]' if exists else '[dim]would be created[/dim]'
        console.print(f'{label:8} {path} {state}')


@config_app.command('sources')
def config_sources() -> None:
    """Explain which files were found and in what order they win."""
    try:
        discovered = [
            ('project', find_project_config()),
            ('user', find_user_config()),
        ]
    except ConfigurationError as exc:
        _die(exc)
        return
    for label, disc in discovered:
        if disc is None:
            console.print(f'{label:8} [dim]none found[/dim]')
        else:
            console.print(f'{label:8} [green]{disc.path}[/green]')
    console.print(
        '\n[dim]strongest first: flags and --set, the selected profile stage, '
        'the profile, STORIX_* in the environment, .env, the project file, '
        'the user file, built-in defaults[/dim]'
    )


@config_app.command('show')
def config_show(
    *,
    effective: Annotated[
        bool,
        typer.Option('--effective', help='add where each value comes from'),
    ] = False,
) -> None:
    """Print the configuration as storix reads it, secrets redacted."""
    from storix.config import config_provenance

    try:
        for label, disc in (
            ('project', find_project_config()),
            ('user', find_user_config()),
        ):
            if disc is None:
                continue
            console.print(f'[bold]{label}[/bold] [dim]{disc.path}[/dim]')
            _render(_redacted(disc.data))
        if not effective:
            return
        console.print('\n[bold]effective[/bold]')
        for provider in sorted(PROVIDER_MODELS):
            for field, source in sorted(config_provenance(provider).items()):
                console.print(f'[cyan]{provider}.{field}[/cyan] [dim]<- {source}[/dim]')
    except ConfigurationError as exc:
        _die(exc)


@config_app.command('get')
def config_get(key: Annotated[str, typer.Argument(help='e.g. s3.bucket')]) -> None:
    """Print one value, from the strongest file that sets it."""
    try:
        parts = split_key(key)
        for disc in (find_project_config(), find_user_config()):
            if disc is None:
                continue
            node: Any = _redacted(disc.data)
            for part in parts:
                if not isinstance(node, dict) or part not in node:
                    node = None
                    break
                node = node[part]  # pyright: ignore[reportUnknownVariableType]
            if node is not None:
                console.print(f'{node!r} [dim]({disc.path})[/dim]')
                return
    except ConfigurationError as exc:
        _die(exc)
        return
    err.print(f'[yellow]sx: {key} is not set in any config file[/yellow]')
    raise typer.Exit(1)


@config_app.command('set')
def config_set(
    key: Annotated[str, typer.Argument(help='e.g. s3.bucket')],
    value: Annotated[str, typer.Argument()],
    *,
    scope: _SCOPE = 'project',
) -> None:
    """Set one value, validated, keeping the file's comments."""
    try:
        written = set_setting(key, value, _scope(scope))
    except ConfigurationError as exc:
        _die(exc)
        return
    console.print(f'[green]{key}[/green] set in {written}')


@config_app.command('unset')
def config_unset(
    key: Annotated[str, typer.Argument(help='e.g. s3.bucket')],
    *,
    scope: _SCOPE = 'project',
) -> None:
    """Remove one value, keeping the rest of the file as it was."""
    try:
        written = unset_setting(key, _scope(scope))
    except ConfigurationError as exc:
        _die(exc)
        return
    console.print(f'[green]{key}[/green] removed from {written}')


@config_app.command('init')
def config_init(
    *,
    scope: _SCOPE = 'project',
    force: Annotated[
        bool, typer.Option('--force', help='overwrite an existing file')
    ] = False,
) -> None:
    """Write a commented starter config, without overwriting one."""
    path, exists = scope_path(_scope(scope))
    if exists and not force:
        err.print(f'[yellow]sx: {path} exists; pass --force to overwrite[/yellow]')
        raise typer.Exit(1)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_SKELETON, encoding='utf-8')
    if _scope(scope) == 'user':
        path.chmod(0o600)
    console.print(f'[green]wrote[/green] {path}')


@config_app.command('validate')
def config_validate() -> None:
    """Load every config file the way storix does, and report the first fault."""
    try:
        found = [
            disc
            for disc in (find_project_config(), find_user_config())
            if disc is not None
        ]
        for disc in found:
            for model in PROVIDER_MODELS.values():
                model()  # settings sources replay this file's policy
            del disc
    except ConfigurationError as exc:
        _die(exc)
        return
    if not found:
        console.print('[dim]no config file found; storix would use defaults[/dim]')
        return
    for disc in found:
        console.print(f'[green]ok[/green] {disc.path}')


@config_app.command('edit')
def config_edit(*, scope: _SCOPE = 'project') -> None:
    """Open the config file in $VISUAL, else $EDITOR."""
    path, exists = scope_path(_scope(scope))
    editor = os.environ.get('VISUAL') or os.environ.get('EDITOR')
    if editor is None:
        err.print('[red]sx: set $VISUAL or $EDITOR to use sx config edit[/red]')
        raise typer.Exit(1)
    if not exists:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_SKELETON, encoding='utf-8')
    subprocess.run([*editor.split(), str(path)], check=False)  # noqa: S603


@config_app.command('profiles')
def config_profiles() -> None:
    """List the profiles that can be selected, and where they come from."""
    try:
        profiles = available_profiles()
    except ConfigurationError as exc:
        _die(exc)
        return
    if not profiles:
        console.print('[dim]no profiles defined[/dim]')
        return
    for name, disc in sorted(profiles.items()):
        _print_profile(name, disc)


def _print_profile(name: str, disc: DiscoveredConfig) -> None:
    """Print one profile's provider, stages, and source file."""
    table: Any = disc.data['profiles'][name]
    provider = table.get('provider', '?')
    stages = sorted(table.get('environments', {}))
    default = table.get('default_environment')
    marked = [f'{s}*' if s == default else s for s in stages]
    suffix = f' [dim]stages:[/dim] {", ".join(marked)}' if marked else ''
    console.print(f'[cyan]{name}[/cyan] [dim]->[/dim] {provider}{suffix}')
    console.print(f'         [dim]{disc.path}[/dim]')


_SKELETON = """\
# storix configuration. See storix.toml.example in the repository for every
# key, or run `sx config path` to see which files are read.

# provider = "local"          # which backend sx and get_storage() open
# max_transfer_ranges = 8     # parallel ranges per file; 1 disables

# [local]
# base = "./data"

# [cli]
# icons = true
"""
