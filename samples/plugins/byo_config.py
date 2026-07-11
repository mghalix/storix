"""Bring your own config / env-var names for the built-in backends.

`STORIX_*` is storix's *default* convention (namespaced to avoid
collisions - see docs/adr/0009). It is not a cage. If your project
already uses `STORAGE_AZURE_*` (or any scheme), you have two clean
options - neither duplicates the backend.

Recommendation: keep `STORIX_*` if you can; reach for these only when an
existing env contract must be honored.

Run:  uv run python samples/plugins/byo_config.py
"""

import os

from pydantic_settings import BaseSettings, SettingsConfigDict

from storix import Storix, get_storage, register_backend
from storix.backends import AzureBackend


# --- Option A: own your settings, pass explicitly (fully decoupled) ---
# storix never reads your env; you read it and hand values in. Clearest
# separation, works with any config source (Vault, TOML, CLI flags...).


class MyAzureSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix='STORAGE_AZURE_')
    container: str = 'raw'
    account_name: str = 'acct'
    credential: str = 'token'


def make_fs_explicit() -> Storix:
    cfg = MyAzureSettings()
    return Storix(
        AzureBackend(
            cfg.container, account_name=cfg.account_name, credential=cfg.credential
        )
    )


# --- Option B: register a builder that reads YOUR config ---
# Replace the built-in 'azure' builder (or register under a new name) so
# get_storage('azure') reads STORAGE_AZURE_* instead of STORIX_AZURE_*.
# Same backend, your config source - no duplicate entry.


def azure_from_my_env(**overrides: object) -> AzureBackend:
    cfg = MyAzureSettings(**overrides)  # type: ignore[arg-type]
    return AzureBackend(
        cfg.container, account_name=cfg.account_name, credential=cfg.credential
    )


register_backend('azure', azure_from_my_env)  # get_storage('azure') now uses your env


def main() -> None:
    os.environ.setdefault('STORAGE_AZURE_CONTAINER', 'my-raw')

    # both paths honor STORAGE_AZURE_* without touching STORIX_AZURE_*
    fs_a = make_fs_explicit()
    print('explicit  -> container', fs_a.backend.container)

    fs_b = get_storage('azure')  # builder reads STORAGE_AZURE_*
    print('registered-> container', fs_b.backend.container)


if __name__ == '__main__':
    main()
