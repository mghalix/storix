from typer.testing import CliRunner

from storix.cli import app


runner = CliRunner()


def test_cli_ls():
    result = runner.invoke(app.app, ['ls'])
    assert result.exit_code == 0


def test_cli_pwd():
    result = runner.invoke(app.app, ['pwd'])
    assert result.exit_code == 0


def test_cli_cd():
    result = runner.invoke(app.app, ['cd', '/'])
    assert result.exit_code == 0
