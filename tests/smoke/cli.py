"""Verify the CLI extra: entry point, ``--version``, and config discovery."""

import os
import subprocess
import sys
import tempfile

from pathlib import Path


def _sx(*args: str, cwd: str | None = None) -> str:
    completed = subprocess.run(  # noqa: S603
        (sys.executable, '-I', '-m', 'storix', *args),
        check=True,
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    return completed.stdout


# the entry point starts through the installed module and renders help
assert 'Usage' in _sx('--help')

# --version prints the installed metadata version (no backend is built)
version_output = _sx('--version')
assert version_output.startswith('sx ')
expected = os.environ.get('STORIX_EXPECTED_VERSION')
if expected:
    assert expected in version_output, version_output

# a project storix.toml [local] base is discovered and honored (anchored at
# the file's directory, ADR 0031); the previously silent drop now acts
with tempfile.TemporaryDirectory() as project:
    root = Path(project)
    (root / 'storix.toml').write_text('[local]\nbase = "."\n')
    (root / 'marker.txt').write_text('discovered')
    listing = _sx('-p', 'local', 'ls', '-a', cwd=str(root))
    assert 'marker.txt' in listing, listing
