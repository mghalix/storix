from importlib import import_module
from typing import Final


_CLI_PACKAGES: Final[frozenset[str]] = frozenset(
    {'click', 'prompt_toolkit', 'rich', 'typer'}
)
"""Top-level packages provided by the optional CLI extra."""


def main() -> None:
    """Entry point for the storix CLI."""
    try:
        cli_module = import_module('storix.cli.app')
    except ModuleNotFoundError as exc:
        missing = (exc.name or '').partition('.')[0]
        if missing not in _CLI_PACKAGES:
            raise
        # context-aware remedy (D7): uv tool users need `uv tool install`,
        # not the project-context `uv add`
        from storix.config import install_hint

        message = f'cli extra not installed. Install it: {install_hint("cli")}'
        raise SystemExit(message) from None

    cli_main = cli_module.main
    cli_main()
