from importlib import import_module
from typing import Final


_CLI_PACKAGES: Final[frozenset[str]] = frozenset(
    {'click', 'prompt_toolkit', 'rich', 'typer'}
)
"""Top-level packages provided by the optional CLI extra."""

_CLI_EXTRA_ERROR: Final[str] = (
    "cli extra not installed. Install it by running `uv add 'storix[cli]'`."
)
"""Actionable error shown when the console launcher lacks CLI dependencies."""


def main() -> None:
    """Entry point for the storix CLI."""
    try:
        cli_module = import_module('storix.cli.app')
    except ModuleNotFoundError as exc:
        missing = (exc.name or '').partition('.')[0]
        if missing not in _CLI_PACKAGES:
            raise
        raise SystemExit(_CLI_EXTRA_ERROR) from None

    cli_main = cli_module.main
    cli_main()
