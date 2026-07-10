from unittest.mock import Mock, patch

from storix.cli.shell import StorixShell


def test_repl_instantiation():
    shell = StorixShell()
    assert shell is not None


@patch('builtins.input', return_value='help')
def test_repl_help_command(mock_input: Mock) -> None:
    shell = StorixShell()
    # Simulate running the help command
    shell.execute_command('help', [])
    # No exception means success
