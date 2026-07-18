"""Session state and backend-stack access for the storix CLI.

One process-wide session holds the live filesystem (so cwd persists
across shell commands) and the display preferences; the helpers here walk
the layer stack and read directory entries at the port level. Everything
presentation-related lives in ``render``; the typer surface in ``app``.
"""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING, Final

from storix import (
    CacheLayer,
    DataUrlLayer,
    MetadataLayer,
    SandboxLayer,
    cache as cache_op,
    get_storage,
)
from storix._sync._compat import concurrent
from storix.errors import StorageError


if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from storix import Storix
    from storix.models import RawStat
    from storix.types import StorixPath


_CLI_READ_CAP: Final[int] = 8 * 1024 * 1024
"""Cache cap for file content in the CLI (8 MiB), so `cat`ing a huge
file never balloons the session's memory."""


class _Session:
    """Holds the one live filesystem so state (cwd) persists across commands."""

    fs: Storix | None = None
    icons: bool | None = None
    """Whether listings decorate entries with icons; None = unresolved
    (falls back to the persistent preferences on first use)."""


_session = _Session()


def build_base(provider: str | None = None) -> Storix:
    """Open a bare session on ``provider``, else the configured default.

    Precedence: an explicit ``-p/--provider``, then the config file's
    ``provider``, then ``STORIX_PROVIDER`` / the factory default. No
    layers - see ``build_session`` for the configured stack.

    Args:
        provider: The provider named on the command line, if any.

    Raises:
        SystemExit: If the provider is unknown, naming the available ones.
    """
    from .config import load_prefs

    name = provider or load_prefs().provider
    try:
        return get_storage(name) if name is not None else get_storage()
    except (StorageError, ValueError, KeyError) as exc:
        # the factory's own error already names the available providers
        message = f'sx: cannot open provider {name!r}: {exc}'
        raise SystemExit(message) from exc


def build_session(provider: str | None = None) -> Storix:
    """A session on the resolved provider, wrapped in the configured stack."""
    return stack_from_prefs(build_base(provider))


def _fs() -> Storix:
    if _session.fs is None:
        _session.fs = build_session()
    return _session.fs


def current_fs() -> Storix:
    """The active session filesystem (public entry point for the shell)."""
    return _fs()


def use_fs(fs: Storix) -> None:
    """Point the session at ``fs`` (public entry point for the shell)."""
    _session.fs = fs


def icons_enabled() -> bool:
    """Whether listings decorate with icons (flag > config > default)."""
    if _session.icons is None:
        from .config import load_prefs

        _session.icons = load_prefs().icons
    return _session.icons


def set_icons(enabled: bool) -> None:  # noqa: FBT001 - a setter takes the value
    """Force icons on or off for this process (the flag override)."""
    _session.icons = enabled


# --- concurrent per-entry lookups ---
#
# A listing needs per-entry facts the listing itself does not carry: a
# directory's emptiness (the folder glyph), an entry's mtime (`ls -t`), a
# file's size when the backend did not include it. Each is one backend call
# per entry, and doing them in a Python loop is N serial round trips - the
# thing that made `sx ls` on a cloud container take N x latency. Batch them
# through the core `concurrent` helper instead, so N distinct-target calls
# run at once (a thread pool over the sync backends' GIL-releasing I/O, ADR
# 0025). The CLI only declares the batch; the concurrency lives in the core.


def stat_all(fs: Storix, paths: Sequence[StorixPath]) -> list[RawStat]:
    """Stat every path concurrently - one cloud round trip, not N serial."""
    return concurrent(partial(fs.backend.stat, path) for path in paths)


def empty_all(fs: Storix, paths: Sequence[StorixPath]) -> list[bool | None]:
    """Test each directory for emptiness concurrently.

    ``None`` for a directory whose check failed (vanished or unreadable),
    so the caller can render the neutral glyph rather than guess.
    """

    def probe(path: StorixPath) -> bool | None:
        try:
            return fs.is_empty(path)
        except StorageError:
            return None

    return concurrent(partial(probe, path) for path in paths)


def apply_layers(
    fs: Storix, *, cache: bool, cache_ttl: float | None, sandbox: str | None
) -> Storix:
    """Wrap the session in the requested layers - sandbox innermost."""
    if sandbox is not None:
        fs = _sandboxed(fs, root=sandbox)
    if cache:
        fs = _cached(fs, ttl=cache_ttl)
    return fs


def _cached(
    fs: Storix, *, ttl: float | None = None, max_bytes: int = _CLI_READ_CAP
) -> Storix:
    """The CLI cache stack: metadata + du + bounded read (ADR 0015)."""
    return fs.with_layer(
        CacheLayer,
        metadata=True,
        du=True,
        read=cache_op(max_bytes=max_bytes),
        ttl=ttl,
    )


def _sandboxed(fs: Storix, *, root: str) -> Storix:
    """Jail the session under ``root``, refusing a root that is not there.

    ``SandboxLayer`` is deliberately pure (its async twin cannot do I/O in
    a constructor), so a missing root only surfaces later, rescoped, as
    ``PathNotFoundError: path '/' does not exist`` - true inside the jail
    and unreadable outside it. sx owns the jail, so it checks the real
    root once, up front, where it can still name it.

    Raises:
        SystemExit: If ``root`` does not exist or is not a directory.
    """
    resolved = fs.resolve(root)
    try:
        if fs.isdir(resolved):
            return fs.with_layer(SandboxLayer, root=resolved)
        problem = (
            'is a file, not a directory' if fs.exists(resolved) else 'does not exist'
        )
    except StorageError as exc:  # an unreachable backend, not a missing root
        message = f'sx: cannot verify sandbox root {resolved}: {exc}'
        raise SystemExit(message) from exc
    provider = type(fs.base_backend).__name__
    message = (
        f'sx: sandbox root {resolved} {problem} on {provider} '
        f'(create it first, or point --sandbox / the config layer elsewhere)'
    )
    raise SystemExit(message)


def _url(fs: Storix) -> Storix:
    """Backfill ``url`` with a data: URL, preferring a native presign."""
    return fs.with_layer_missing(DataUrlLayer)


def _metadata(fs: Storix) -> Storix:
    """Backfill custom metadata (JSON sidecars), preferring native."""
    return fs.with_layer_missing(MetadataLayer)


_LAYER_BUILDERS: Final[dict[str, Callable[..., Storix]]] = {
    'cache': _cached,
    'sandbox': _sandboxed,
    'url': _url,
    'metadata': _metadata,
}
"""Config-file layer names -> builders, one per built-in layer a config
file can express. ``url`` and ``metadata`` backfill a capability, so they
go through ``with_layer_missing``: a backend that already has it natively
(an Azure SAS URL) keeps it, and the layer is skipped rather than
shadowing the real thing. ``ObservabilityLayer`` is deliberately absent:
its only argument is a sink callable, which TOML cannot express, and
without one it is a passthrough - sx attaches it itself around transfers
(ADR 0019)."""


def stack_from_prefs(fs: Storix) -> Storix:
    """Apply the configured ``[[cli.layers]]`` stack to a session.

    Entries apply in listed order, each wrapping the previous, so the
    last entry is outermost. A no-op with no configured layers.

    Raises:
        SystemExit: If an entry names an unknown layer or passes options
            its builder does not accept, naming the offending entry.
    """
    from .config import load_prefs

    for spec in load_prefs().layers:
        name = spec.get('name')
        builder = _LAYER_BUILDERS.get(name) if isinstance(name, str) else None
        if builder is None:
            known = ', '.join(sorted(_LAYER_BUILDERS))
            message = f'sx: unknown layer {name!r} in config (known: {known})'
            raise SystemExit(message)
        options = {key: value for key, value in spec.items() if key != 'name'}
        try:
            fs = builder(fs, **options)
        except TypeError as exc:
            message = f'sx: bad options for config layer {name!r}: {exc}'
            raise SystemExit(message) from exc
    return fs


def cache_layer(fs: Storix) -> CacheLayer | None:
    """The active ``CacheLayer`` in the session's stack, if any."""
    return next((la for la in fs.layers if isinstance(la, CacheLayer)), None)


# op name -> the CLI verbs it accelerates, for the layer summary
_CACHE_VERBS = {'metadata': 'ls/stat', 'du': 'du', 'read': 'cat', 'url': 'url'}


def layer_summary(fs: Storix) -> str | None:
    """A one-line description of the active layer stack (outermost first)."""
    parts: list[str] = []
    for layer in fs.layers:
        if isinstance(layer, CacheLayer):
            ops = (o for o in layer.enabled if o in _CACHE_VERBS)
            verbs = '/'.join(_CACHE_VERBS[o] for o in ops)
            via = '+'.join(layer.store_names())
            parts.append(f'cache {verbs} via {via}')
        elif isinstance(layer, SandboxLayer):
            parts.append(f'sandbox {layer.to_real("/")}')  # public audit handle
        elif isinstance(layer, DataUrlLayer):
            parts.append('url via data: URLs')
        elif isinstance(layer, MetadataLayer):
            parts.append('metadata via sidecars')
    return ' · '.join(parts) if parts else None
