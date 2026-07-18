"""Verify the CLI extra starts through the installed module entry point."""

import subprocess
import sys


completed = subprocess.run(  # noqa: S603
    (sys.executable, '-I', '-m', 'storix', '--help'),
    check=True,
    capture_output=True,
    text=True,
)
assert 'Usage' in completed.stdout
