# ruff: noqa: A004 - storix error classes intentionally shadow stdlib names
"""AzureBlobBackend account-key SAS signing, offline (no credentials).

SAS generation is local HMAC crypto, so a throwaway base64 account key
exercises the real signing path without a live account. Behavioral
coverage lives in the conformance suite (test_backends.py, integration).
"""

import base64

from pathlib import PurePosixPath as P

import pytest

from storix._async.backends.azblob import AzureBlobBackend
from storix.enums import PathKind
from storix.errors import IsADirectoryError
from storix.models import RawStat
from storix.utils import craft_blob_url_sas
from storix.utils.time import utcnow


# a throwaway key: valid base64, no 'sig=' marker, never a real credential
FAKE_KEY = base64.b64encode(b'storix-offline-test-account-key-0').decode()


def _blob(*, root: str = '/', endpoint: str | None = None) -> AzureBlobBackend:
    return AzureBlobBackend(
        'mycontainer',
        account_name='acct',
        credential=FAKE_KEY,
        endpoint=endpoint or 'https://acct.blob.core.windows.net',
        root=root,
    )


def _file_stat() -> RawStat:
    now = utcnow()
    return RawStat(kind=PathKind.FILE, size=3, created=now, modified=now)


def test_account_key_advertises_presigned_urls():
    assert _blob().capabilities.presigned_urls is True


def test_sas_token_credential_is_unchanged():
    # opendal governs the capability for a SAS-token credential; the
    # account-key override must not touch it
    fs = AzureBlobBackend('mycontainer', account_name='acct', credential='sv=x&sig=abc')
    assert 'account_key' not in fs._options


async def test_make_url_signs_locally(monkeypatch: pytest.MonkeyPatch):
    fs = _blob()

    async def stat(_path: P) -> RawStat:
        return _file_stat()

    monkeypatch.setattr(fs, 'stat', stat)

    url = await fs.make_url(P('/docs/a.txt'))

    assert url.startswith('https://acct.blob.core.windows.net/mycontainer/docs/a.txt?')
    assert 'sig=' in url


async def test_make_url_honors_root_and_endpoint(monkeypatch: pytest.MonkeyPatch):
    fs = _blob(root='/prefix', endpoint='http://127.0.0.1:10000/devstoreaccount1')

    async def stat(_path: P) -> RawStat:
        return _file_stat()

    monkeypatch.setattr(fs, 'stat', stat)

    url = await fs.make_url(P('/docs/a.txt'))

    assert url.startswith(
        'http://127.0.0.1:10000/devstoreaccount1/mycontainer/prefix/docs/a.txt?'
    )
    assert 'sig=' in url


async def test_make_url_rejects_a_directory(monkeypatch: pytest.MonkeyPatch):
    fs = _blob()

    async def stat(_path: P) -> RawStat:
        now = utcnow()
        return RawStat(kind=PathKind.DIRECTORY, size=0, created=now, modified=now)

    monkeypatch.setattr(fs, 'stat', stat)

    with pytest.raises(IsADirectoryError):
        await fs.make_url(P('/docs'))


def test_craft_blob_url_sas_embeds_endpoint_root_and_token():
    url = craft_blob_url_sas(
        endpoint='http://127.0.0.1:10000/devstoreaccount1',
        container='mycontainer',
        blob_name='prefix/docs/a.txt',
        sas_token='?sig=token',  # noqa: S106 - a fixed literal for the assertion
    )
    assert url == (
        'http://127.0.0.1:10000/devstoreaccount1/mycontainer/prefix/docs/a.txt?sig=token'
    )
