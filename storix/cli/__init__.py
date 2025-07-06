from collections.abc import Callable

cli_main: Callable | None

try:
    from .app import main as cli_main
except ImportError:
    cli_main = None


def main() -> None:
    """Entry point for the storix CLI."""
    if not cli_main:
        message = (
            "[red]Error: storix CLI is not installed.\n"
            "Install with: pip install storix[cli]"
        )
        print(message)
        return
    cli_main()
