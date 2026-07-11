from pathlib import Path

import pytest

from storix._async import Storix, get_storage
from storix._async.backends.local import LocalBackend
from storix.errors import ConfigurationError, StorageError


def test_default_is_local(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv('STORIX_LOCAL_BASE', str(tmp_path))
    fs = get_storage()
    assert isinstance(fs, Storix)
    assert isinstance(fs.backend, LocalBackend)
    assert fs.backend._base == tmp_path


def test_provider_argument_overrides_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv('STORIX_PROVIDER', 'azure')
    fs = get_storage('local', base=str(tmp_path))
    assert isinstance(fs.backend, LocalBackend)


def test_kwargs_override_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv('STORIX_LOCAL_BASE', '/definitely/not/this')
    fs = get_storage('local', base=str(tmp_path))
    assert fs.backend._base == tmp_path


def test_env_selects_provider(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv('STORIX_PROVIDER', 'local')
    monkeypatch.setenv('STORIX_LOCAL_BASE', str(tmp_path))
    assert isinstance(get_storage().backend, LocalBackend)


def test_azure_from_kwargs_builds_without_network():
    fs = get_storage('azure', container='raw', account_name='acct', credential='token')
    assert fs.backend.container == 'raw'


def test_azure_missing_config_raises_helpfully(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.chdir(tmp_path)  # hermetic: a developer .env must not leak in
    for var in (
        'STORIX_AZURE_CONTAINER',
        'STORIX_AZURE_ACCOUNT_NAME',
        'STORIX_AZURE_CREDENTIAL',
    ):
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(ConfigurationError) as excinfo:
        get_storage('azure')
    message = str(excinfo.value)
    assert 'container' in message
    assert 'STORIX_AZURE_' in message


def test_unknown_provider_raises():
    with pytest.raises(ConfigurationError):
        get_storage('carrier-pigeon')


def test_keyword_provider_is_rejected_not_swallowed():
    """provider= must never silently become a config override."""
    with pytest.raises(ConfigurationError, match='positionally'):
        get_storage(provider='azure')  # type: ignore[call-overload]


def test_configuration_error_is_a_storage_error():
    assert issubclass(ConfigurationError, StorageError)


def test_register_backend_extends_the_factory():
    from storix._async.backends.memory import MemoryBackend
    from storix._async.factory import _BUILDERS, register_backend

    received: dict[str, str] = {}

    def build(**overrides: str) -> MemoryBackend:
        received.update(overrides)
        return MemoryBackend()

    register_backend('unit-test', build)
    try:
        fs = get_storage('unit-test', flavor='x')
        assert isinstance(fs.backend, MemoryBackend)
        assert received == {'flavor': 'x'}
    finally:
        _BUILDERS.pop('unit-test')
