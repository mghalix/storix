import posixpath

from types import SimpleNamespace

from storix.types import StrPathLike


# Expose 'magic' at module level for testability and patching.
# Will be used by get_mimetype; tests may monkeypatch storix.utils.magic.
try:
    import magic as magic
except (ImportError, OSError):  # libmagic may be missing at either level
    magic = SimpleNamespace(  # type: ignore[assignment]
        from_buffer=lambda _buf, mime=True: 'application/octet-stream'
    )


def craft_adlsg2_url(*, account_name: str) -> str:
    """Structure an Azure Datalake Gen2 URL."""
    return f'https://{account_name}.dfs.core.windows.net'


def craft_adlsg2_url_sas(
    *, account_name: str, container: str, directory: str, filename: str, sas_token: str
) -> str:
    """Structure an Azure Datalake Gen2 URL with a SAS token embedded."""
    base_url = craft_adlsg2_url(account_name=account_name)
    path = posixpath.join(*(p.strip('/') for p in (container, directory, filename)))
    return f'{base_url}/{path}?{sas_token.lstrip("?")}'


def get_mimetype(*, buf: bytes) -> str:
    """Detect mimetype from a buffer using globally exposed 'magic'."""
    return magic.from_buffer(buf, mime=True)  # type: ignore[attr-defined]


def guess_mimetype_from_path(path: StrPathLike) -> str | None:
    """Guess mimetype from file extension using stdlib.

    Returns None when type can't be determined.
    """
    import mimetypes

    mime, _ = mimetypes.guess_type(str(path))
    return mime


def detect_mimetype(
    *,
    buf: bytes | None = None,
    path: StrPathLike | None = None,
    default: str = 'application/octet-stream',
) -> str:
    """Detect best content-type given optional path and/or buffer.

    Precedence:
    1) If a path is provided and has a known extension -> return its mimetype
    2) Else if a non-empty buffer is provided -> sniff using libmagic
    3) Else -> return `default`

    This keeps lookups cheap while remaining robust when extensions are absent.
    """
    if path is not None:
        guessed = guess_mimetype_from_path(path)
        if guessed:
            return guessed

    if buf:
        try:
            return get_mimetype(buf=buf)
        except Exception:  # noqa: BLE001, S110 - best-effort sniff, fall to default
            pass

    return default


def to_data_url(*, buf: bytes, mimetype: str | None = None) -> str:
    """Create a data url."""
    template = 'data:{mimetype};base64,{base64_data}'

    b64_data = _b64_encode(buf=buf)
    mimetype = mimetype or get_mimetype(buf=buf)

    return template.format(mimetype=mimetype, base64_data=b64_data)


def _b64_encode(*, buf: bytes) -> str:
    import base64

    return base64.b64encode(buf).decode('utf-8')
