"""Test-wide isolation from the developer's own machine.

The configuration loader reads a user-scope file (`~/.config/storix/
config.toml`) and the `STORIX_*` environment. Without this, a developer's
real configuration would take part in the test run: a profile they are
mid-edit, a provider they happen to prefer, a credential they exported.
Tests would then pass or fail depending on whose machine they ran on,
which is the opposite of what a suite is for.

`STORIX_TEST_*` is a different thing and is left alone. It is the suite's
own namespace, and the loader never reads it: it is the declared input the
credentialed conformance backends are built from, not ambient
configuration that could leak in.
"""

# ruff: noqa: INP001 - pytest discovers conftest by path, not as a package
from __future__ import annotations

import os

from typing import TYPE_CHECKING

import pytest


if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path


def _is_ambient_configuration(name: str) -> bool:
    """Whether an environment variable is connection config the loader reads."""
    return name.startswith('STORIX_') and not name.startswith('STORIX_TEST_')


@pytest.fixture(autouse=True)
def _isolated_configuration(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> Generator[None]:
    """Point config discovery at an empty XDG home and clear STORIX_*.

    `STORIX_TEST_*` survives; see the module docstring for why.
    """
    empty: Path = tmp_path_factory.mktemp('xdg')
    monkeypatch.setenv('XDG_CONFIG_HOME', str(empty))
    for name in [key for key in os.environ if _is_ambient_configuration(key)]:
        monkeypatch.delenv(name, raising=False)
    yield
