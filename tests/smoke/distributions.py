"""Smoke-test built Storix distributions outside the source checkout."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tomllib

from pathlib import Path
from typing import TYPE_CHECKING, Final


if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence


_ROOT: Final[Path] = Path(__file__).parents[2]
_RUNNER: Final[Path] = _ROOT / 'scripts' / 'smoke'
_SCENARIOS: Final[Path] = Path(__file__).parent
_PROFILES: Final[tuple[tuple[str, str, str], ...]] = (
    ('default', 'core.py', '-'),
    ('missing-s3', 'missing_extra.py', '-'),
    ('azadls', 'azadls.py', 'azadls'),
    ('azblob', 'azblob.py', 'azblob'),
    ('s3', 's3.py', 's3'),
    ('gcs', 'gcs.py', 'gcs'),
    ('cli', 'cli.py', 'cli'),
)


class _SmokeError(RuntimeError):
    """Raised when built distributions do not match the smoke contract."""


def _project_version() -> str:
    project = tomllib.loads(Path('pyproject.toml').read_text())['project']
    version = project['version']
    if not isinstance(version, str):
        message = '[project].version must be a string'
        raise _SmokeError(message)
    return version


def _artifacts(dist: Path) -> tuple[Path, Path]:
    wheels = tuple(dist.glob('*.whl'))
    sdists = tuple(dist.glob('*.tar.gz'))
    if len(wheels) != 1 or len(sdists) != 1:
        message = 'expected exactly one wheel and one source distribution'
        raise _SmokeError(message)
    return wheels[0].resolve(), sdists[0].resolve()


def _run(
    command: Sequence[str],
    *,
    environment: Mapping[str, str],
) -> None:
    subprocess.run(  # noqa: S603
        command,
        cwd=_ROOT,
        env=environment,
        check=True,
    )


def _smoke_artifact(artifact: Path, version: str) -> None:
    environment = os.environ.copy()
    for variable in ('PYTHONPATH', 'UV_PROJECT_ENVIRONMENT', 'VIRTUAL_ENV'):
        environment.pop(variable, None)
    environment['STORIX_EXPECTED_VERSION'] = version

    for profile, scenario, extra in _PROFILES:
        sys.stdout.write(f'smoke: {artifact.name} [{profile}]\n')
        _run(
            (
                str(_RUNNER),
                str(artifact),
                str(_SCENARIOS / scenario),
                extra,
            ),
            environment=environment,
        )


def main(arguments: Sequence[str] | None = None) -> int:
    """Install and exercise one wheel and one sdist in isolated environments.

    Args:
        arguments: Command arguments without the executable name.

    Returns:
        Zero when every distribution and extra passes.

    Raises:
        _SmokeError: If the reusable smoke runner is missing.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('dist', type=Path)
    namespace = parser.parse_args(arguments)

    if not _RUNNER.is_file():
        message = f'artifact smoke runner is missing: {_RUNNER}'
        raise _SmokeError(message)

    wheel, sdist = _artifacts(namespace.dist)
    version = _project_version()
    for artifact in (wheel, sdist):
        _smoke_artifact(artifact, version)

    sys.stdout.write('wheel and source distribution smoke tests passed\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
