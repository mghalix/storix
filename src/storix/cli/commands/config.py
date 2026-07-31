"""``sx config``: see, explain, and edit configuration (ADR 0031 D10).

Presentation only. Discovery, precedence, validation, the secret policy,
and the writes themselves live in ``storix.config``, because ``sx`` is a
driving adapter over the library and must not grow a second copy of the
rules it displays.
"""

from __future__ import annotations

from typing import Annotated, Any, cast

import typer

from rich.markup import escape
from rich.table import Table

from storix.config import (
    PROVIDER_MODELS,
    DiscoveredConfig,
    Scope,
    available_profiles,
    find_project_config,
    find_user_config,
    is_secret,
    project_config_path,
    resolve_profile,
    scope_path,
    set_setting,
    split_key,
    unset_setting,
    user_config_path,
)
from storix.errors import ConfigurationError

from ..registry import (
    _SETUP,  # pyright: ignore[reportPrivateUsage]
    app,
)
from ..render import console, err, launch_editor
from ..state import resolve_provider, selection


_MISSING = object()
"""Sentinel for "this model has no such field", distinct from a None value."""

REDACTED = '***'
"""What a secret's value is shown as, in every read command."""

config_app = typer.Typer(
    name='config',
    help='See, explain, and edit storix configuration.',
    no_args_is_help=True,
)

app.add_typer(config_app, rich_help_panel=_SETUP)

_SCOPE = Annotated[
    str, typer.Option('--scope', help='user | project (default: project)')
]
_USER = Annotated[
    bool,
    typer.Option('--user', help='shorthand for --scope user (your global config)'),
]


def _target(scope: str, user: bool) -> Scope:  # noqa: FBT001 - a typer flag
    """The scope a write targets, from ``--scope`` and the ``--user`` shorthand.

    Raises:
        SystemExit: If both are given and disagree.
    """
    if user and scope not in {'project', 'user'}:
        message = f"sx: --scope must be 'user' or 'project', not {scope!r}"
        raise SystemExit(message)
    if user and scope == 'project':
        return 'user'
    return _scope(scope)


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
    err.print(f'[red]sx: {escape(str(exc))}[/red]')
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


def _settings_cell(section: dict[str, Any]) -> str:
    """One profile's or stage's settings, one ``key = value`` per line."""
    skip = {'provider', 'environments', 'default_environment'}
    return '\n'.join(
        f'[cyan]{key}[/cyan] = {value!r}'
        for key, value in sorted(section.items())
        if key not in skip
    )


def _profiles_table(
    profiles: dict[str, DiscoveredConfig],
    selected: str | None,
    stage_selected: str | None = None,
) -> None:
    """Print profiles as a table, grouped by the file that defines them.

    Dotted keys flatten a profile into one long line per field
    (``profiles.NAME.environments.STAGE.account_name``), which is the least
    readable shape for the thing a user reaches for most. A stage is a row
    under its profile instead, and the values sit in a column that wraps.
    """
    by_source: dict[str, list[tuple[str, DiscoveredConfig]]] = {}
    for name, disc in sorted(profiles.items()):
        by_source.setdefault(str(disc.path), []).append((name, disc))

    for path, entries in by_source.items():
        console.print(f'[bold]profiles[/bold] [dim]{path}[/dim]')
        table = Table(box=None, pad_edge=False, header_style='dim')
        table.add_column('profile')
        table.add_column('provider')
        table.add_column('stage')
        table.add_column('settings')
        for name, disc in entries:
            profile = _redacted_profile(disc.data['profiles'][name])
            if not isinstance(profile, dict):
                continue
            section = cast('dict[str, Any]', profile)
            label = f'[cyan]{name}[/cyan]'
            if name == selected:
                label += ' [green]*[/green]'
            provider = str(section.get('provider', '?'))
            table.add_row(label, provider, '', _settings_cell(section))
            stages = section.get('environments')
            if not isinstance(stages, dict):
                continue
            in_force = stage_selected if name == selected else None
            in_force = in_force or section.get('default_environment')
            for stage, values in sorted(cast('dict[str, Any]', stages).items()):
                if not isinstance(values, dict):
                    continue
                marked = f'{stage} [green]*[/green]' if stage == in_force else stage
                cell = _settings_cell(cast('dict[str, Any]', values))
                table.add_row('', '', marked, cell)
        console.print(table)
        console.print('[dim]* what this invocation would use[/dim]')


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
        typer.Option(
            '--effective',
            help='what a session would actually use, and where each value is from',
        ),
    ] = False,
) -> None:
    """Print the configuration as storix reads it, secrets redacted."""
    try:
        if effective:
            _show_effective()
            return
        for label, disc in (
            ('project', find_project_config()),
            ('user', find_user_config()),
        ):
            if disc is None:
                continue
            console.print(f'[bold]{label}[/bold] [dim]{disc.path}[/dim]')
            document = _redacted(disc.data)
            document.pop('profiles', None)  # shown as a table below, not dotted
            _render(document)
        _show_profiles()
    except ConfigurationError as exc:
        _die(exc)


def _show_profiles() -> None:
    """Print the profiles, narrowed to the selected one when there is one.

    A selected profile is the only one this invocation would use, so
    printing the rest alongside it invites reading the wrong row.
    """
    profiles = available_profiles()
    if not profiles:
        return
    profile, stage = selection()
    if profile is not None and profile in profiles:
        _profiles_table({profile: profiles[profile]}, profile, stage)
        others = sorted(set(profiles) - {profile})
        if others:
            console.print(
                f'[dim]{len(others)} more not selected: {", ".join(others)} '
                '(sx config profiles)[/dim]'
            )
        return
    _profiles_table(profiles, profile, stage)


def _show_effective() -> None:
    """Print what a session would use: the provider in force and its values.

    Only the effective provider, because the others are not what this
    invocation would open, and every field with its value, because a source
    without a value answers half the question.
    """
    from storix.config import StorixSettings, config_provenance

    from ..state import selection

    profile, environment = selection()
    provider = resolve_provider(None, profile)
    where = f" [dim](profile '{profile}')[/dim]" if profile else ''
    console.print('[bold]effective[/bold]')
    console.print(f'  provider     [cyan]{provider}[/cyan]{where}')

    settings = StorixSettings()
    for field in sorted(StorixSettings.model_fields):
        if field == 'provider':
            continue  # the headline above already says which one is in force
        console.print(f'  {field:20} {getattr(settings, field)!r}')

    model = PROVIDER_MODELS.get(provider)
    if model is None:
        console.print(f'  [dim]{provider} takes no configuration[/dim]')
        return
    resolved = (
        resolve_profile(profile, environment).values if profile is not None else {}
    )
    values = model(**resolved)
    sources = config_provenance(provider, profile=profile, environment=environment)
    for field in sorted(model.model_fields):
        value = getattr(values, field, None)
        if value is not None and is_secret(model, field):
            value = REDACTED
        readable = getattr(value, 'human_readable', None)
        shown = f'{value!r} ({readable()})' if callable(readable) else repr(value)
        source = sources.get(field, 'default')
        console.print(f'  {provider}.{field:20} {shown} [dim]<- {source}[/dim]')


@config_app.command('get')
def config_get(
    key: Annotated[str, typer.Argument(help='e.g. s3.bucket, cli.icons')],
    *,
    effective: Annotated[
        bool,
        typer.Option(
            '--effective',
            help='the value storix would use, including defaults, and its source',
        ),
    ] = False,
) -> None:
    """Print one value: as written in a file, or as storix would resolve it."""
    try:
        if effective:
            _print_effective(key)
            return
        for disc in (find_project_config(), find_user_config()):
            if disc is None:
                continue
            node: Any = _redacted(disc.data)
            for part in split_key(key):
                if not isinstance(node, dict) or part not in node:
                    node = None
                    break
                node = cast('dict[str, Any]', node)[part]
            if node is not None:
                console.print(f'{node!r} [dim]({disc.path})[/dim]')
                return
    except ConfigurationError as exc:
        _die(exc)
        return
    err.print(
        f'[yellow]sx: {key} is not set in any config file; '
        f'try `sx config get --effective {key}` for the value in force[/yellow]'
    )
    raise typer.Exit(1)


def _print_effective(key: str) -> None:
    """Print the value storix would use for ``key``, and where it comes from.

    Reads through the same models a session is built from, so a default is
    reported as a default rather than as "not set" - the question a user
    actually has is "what will storix do", not "what did I write down".

    Raises:
        ConfigurationError: If the key names no known section or field.
    """
    from storix.config import StorixSettings, config_provenance

    from ..config import load_prefs

    parts = list(split_key(key))
    section = parts[0] if len(parts) > 1 else ''
    field = parts[-1]

    if section == 'cli':
        value = getattr(load_prefs(), field, _MISSING)
        _report_effective(key, value, 'cli preferences')
        return
    if section == '':
        value = getattr(StorixSettings(), field, _MISSING)
        _report_effective(key, value, config_provenance('local').get(field, 'default'))
        return

    model = PROVIDER_MODELS.get(section)
    if model is None:
        known = ', '.join([*sorted(PROVIDER_MODELS), 'cli'])
        msg = f'{section!r} is not a config section; known: {known}'
        raise ConfigurationError(msg)
    value = getattr(model(), field, _MISSING)
    if value is not _MISSING and value is not None and is_secret(model, field):
        value = REDACTED
    _report_effective(key, value, config_provenance(section).get(field, 'default'))


def _report_effective(key: str, value: object, source: object) -> None:
    """Print one resolved value with its source, or say the key is unknown.

    Raises:
        typer.Exit: With status 1 when the field does not exist.
    """
    if value is _MISSING:
        err.print(f'[yellow]sx: {key} is not a storix setting[/yellow]')
        raise typer.Exit(1)
    readable = getattr(value, 'human_readable', None)
    shown = f'{value!r} ({readable()})' if callable(readable) else repr(value)
    console.print(f'{shown} [dim]<- {source}[/dim]')


@config_app.command('set')
def config_set(
    key: Annotated[str, typer.Argument(help='e.g. s3.bucket')],
    value: Annotated[str, typer.Argument()],
    *,
    scope: _SCOPE = 'project',
    user: _USER = False,
) -> None:
    """Set one value, validated, keeping the file's comments."""
    try:
        written = set_setting(key, value, _target(scope, user))
    except ConfigurationError as exc:
        _die(exc)
        return
    console.print(f'[green]{key}[/green] set in {written}')


@config_app.command('unset')
def config_unset(
    key: Annotated[str, typer.Argument(help='e.g. s3.bucket')],
    *,
    scope: _SCOPE = 'project',
    user: _USER = False,
) -> None:
    """Remove one value, keeping the rest of the file as it was."""
    try:
        written = unset_setting(key, _target(scope, user))
    except ConfigurationError as exc:
        _die(exc)
        return
    console.print(f'[green]{key}[/green] removed from {written}')


@config_app.command('init')
def config_init(
    *,
    scope: _SCOPE = 'project',
    user: _USER = False,
    force: Annotated[
        bool, typer.Option('--force', help='overwrite an existing file')
    ] = False,
) -> None:
    """Write a commented starter config, without overwriting one."""
    target = _target(scope, user)
    path, exists = scope_path(target)
    if exists and not force:
        err.print(f'[yellow]sx: {path} exists; pass --force to overwrite[/yellow]')
        raise typer.Exit(1)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_SKELETON, encoding='utf-8')
    if target == 'user':
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
def config_edit(*, scope: _SCOPE = 'project', user: _USER = False) -> None:
    """Open the config file in $VISUAL, else $EDITOR."""
    path, exists = scope_path(_target(scope, user))
    if not exists:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_SKELETON, encoding='utf-8')
    launch_editor(path)


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
    selected, stage = selection()
    _profiles_table(profiles, selected, stage)


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
