# ruff: noqa: A004 - storix error classes intentionally shadow stdlib names
"""INTERNAL Apache OpenDAL adapter engine (async flavor).

Not part of the public API: users see the typed per-provider facades
(``S3Backend``, ``GcsBackend``, ...) that subclass this engine with
explicit, documented constructors. Everything here - the service and
option vocabulary, directory-marker handling, error translation - is an
implementation detail and may change without notice.

Hand-written twin pair (excluded from codegen): the sync sibling speaks
``opendal.Operator`` while this flavor speaks ``opendal.AsyncOperator``.
Keep ``storix._sync.backends.opendal`` in lockstep by hand; the
conformance suite is the drift guard.

One engine, ~50 services (s3, gcs, azblob, fs, memory, ...): the
service name plus its options go straight to the opendal operator, and
capabilities are derived from what the chosen service actually supports.
"""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Any, Final

from storix._async._stream import batch_chunks, resolve_chunk_size
from storix.constants import DEFAULT_URL_EXPIRY_SECONDS
from storix.enums import Capability, PathKind
from storix.errors import (
    AlreadyExistsError,
    ConfigurationError,
    DirectoryNotEmptyError,
    IsADirectoryError,
    NotADirectoryError,
    PathNotFoundError,
    PermissionDeniedError,
    StorageError,
    StorageRootNotFoundError,
    UnsupportedOperationError,
)
from storix.models import Capabilities, Entry, RawStat
from storix.utils.time import utcnow

from .base import BackendBase


try:
    import opendal

    from opendal import exceptions as ope
except ModuleNotFoundError as exc:  # pragma: no cover
    if (exc.name or '').partition('.')[0] != 'opendal':
        raise
    _msg = (
        'the storage engine for this backend is not installed. Install the '
        "matching extra: `uv add 'storix[azure]'`, 'storix[azblob]', "
        "'storix[s3]', or 'storix[gcs]'."
    )
    raise ImportError(_msg) from None


if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Mapping

    from opendal.types import Metadata

    from storix.types import EchoMode


# opendal's exception classes are flat (Error is a sibling, not a base),
# so 'any opendal failure' is this tuple, collected from its module
_OPENDAL_ERRORS: Final[tuple[type[Exception], ...]] = tuple(
    cls
    for cls in vars(ope).values()
    if isinstance(cls, type) and issubclass(cls, Exception)
)

# opendal exceptions -> storix taxonomy; opendal's taxonomy is small and
# service-independent, so the map is exact rather than best-effort
_ERROR_MAP: tuple[tuple[type[Exception], type[StorageError]], ...] = (
    (ope.NotFound, PathNotFoundError),
    (ope.AlreadyExists, AlreadyExistsError),
    (ope.IsADirectory, IsADirectoryError),
    (ope.NotADirectory, NotADirectoryError),
    (ope.PermissionDenied, PermissionDeniedError),
)


def _translate(exc: Exception, path: PurePosixPath) -> StorageError:
    """Translate an opendal failure into the storix taxonomy."""
    for opendal_cls, storix_cls in _ERROR_MAP:
        if isinstance(exc, opendal_cls):
            return storix_cls(path)
    if isinstance(exc, ope.ConfigInvalid):
        return ConfigurationError(f'opendal configuration invalid: {exc}')
    return StorageError(f"'{path}': {exc}")


_MISSING_ROOT_CODES: Final[dict[str, tuple[str, str]]] = {
    's3': ('NoSuchBucket', 'bucket'),
    'azblob': ('ContainerNotFound', 'container'),
}
"""Per-service missing-root signal: the provider error code a missing
bucket/container embeds in the message, and the root vocabulary for the
error text (ADR 0029). String matching is unavoidable - opendal's Python
exceptions carry no structured fields - so it is confined to this table
and matches the quoted ``code: "..."`` token, never bare prose. gcs is
absent until its real missing-bucket message is captured live; unmatched
errors keep the generic translation."""


class OpendalBackend(BackendBase):
    """Adapter over an `Apache OpenDAL <https://opendal.apache.org>`_ operator.

    ``service`` selects the opendal service (``'s3'``, ``'gcs'``,
    ``'azblob'``, ``'memory'``, ...) and ``options`` are that service's
    native configuration keys, passed through verbatim (``bucket``,
    ``region``, ``root``, ...). Capabilities are derived per service from
    ``opendal``'s own capability report, so a single adapter honestly
    advertises what each service can do.

    Object-store directory semantics: opendal marks directories with a
    trailing ``/`` on the key. The adapter owns that translation; port
    paths never carry trailing slashes.
    """

    def __init__(self, service: str, /, **options: str) -> None:
        """Create an opendal-backed storage backend.

        Args:
            service: opendal service scheme, e.g. ``'s3'`` or ``'memory'``.
            options: Service-specific opendal configuration, passed through
                to the operator untouched.

        Raises:
            ConfigurationError: If opendal rejects the service or options.
        """
        self._service = service
        self._options = options
        try:
            self._op = opendal.AsyncOperator(service, **options)
        except _OPENDAL_ERRORS as exc:
            msg = f'opendal {service!r} configuration invalid: {exc}'
            raise ConfigurationError(msg) from exc
        cap = self._op.capability()
        self.capabilities = Capabilities(
            content_type=cap.write_with_content_type,
            custom_metadata=cap.write_with_user_metadata,
            presigned_urls=cap.presign_read,
            bulk_listing=cap.list_with_recursive,
        )

    @staticmethod
    def _key(path: PurePosixPath) -> str:
        """Root-relative opendal key for a port path ('' for the root)."""
        return str(path).lstrip('/')

    def _dir_key(self, path: PurePosixPath) -> str:
        """Directory-form key: trailing slash, ``/`` for the root."""
        key = self._key(path)
        return f'{key}/' if key else '/'

    def locate(self, path: PurePosixPath) -> str:
        """``opendal+<service>://`` locator, with the bucket when known."""
        authority = self._options.get('bucket') or self._options.get('container', '')
        prefix = self._options.get('root', '/').rstrip('/')
        return f'opendal+{self._service}://{authority}{prefix}{path}'

    def _error(self, exc: Exception, path: PurePosixPath) -> StorageError:
        """Translate an opendal failure, detecting a missing storage root."""
        return self._missing_root(exc) or _translate(exc, path)

    def _missing_root(self, exc: Exception) -> StorageRootNotFoundError | None:
        """The failure as a missing-root error, when its provider code says so."""
        entry = _MISSING_ROOT_CODES.get(self._service)
        if entry is None:
            return None
        code, kind = entry
        if f'code: "{code}"' not in str(exc):
            return None
        root = self._options.get('bucket') or self._options.get('container', '')
        return StorageRootNotFoundError(root, kind=f'{self._service} {kind}')

    async def _stat_md(self, path: PurePosixPath) -> Metadata:
        """Fetch opendal metadata, trying the file key then the directory key.

        Raises:
            PathNotFoundError: If neither key form exists.
        """
        key = self._key(path)
        try:
            return await self._op.stat(key)
        except ope.NotFound:
            try:
                return await self._op.stat(f'{key}/')
            except _OPENDAL_ERRORS as inner:
                raise self._error(inner, path) from inner
        except _OPENDAL_ERRORS as exc:
            raise self._error(exc, path) from exc

    def _to_raw(self, md: Metadata) -> RawStat:
        """Shape opendal metadata into the port's RawStat."""
        # ponytail: services without timestamps (memory) fall back to
        # utcnow() at stat time; real stores (s3, gcs) report last_modified
        timestamp = md.last_modified or utcnow()
        metadata = md.user_metadata
        return RawStat(
            kind=PathKind.DIRECTORY if md.is_dir else PathKind.FILE,
            size=0 if md.is_dir else md.content_length,
            created=timestamp,
            modified=timestamp,
            metadata=dict(metadata) if metadata else None,
        )

    async def stat(self, path: PurePosixPath) -> RawStat:
        """Return raw facts about a path (directory sizes are 0)."""
        if not self._key(path):  # the operator root is always a directory
            now = utcnow()
            return RawStat(kind=PathKind.DIRECTORY, size=0, created=now, modified=now)
        return self._to_raw(await self._stat_md(path))

    async def read_stream(
        self, path: PurePosixPath, *, chunk_size: int | None = None
    ) -> AsyncIterator[bytes]:
        """Stream a file's contents in bounded chunks.

        Raises:
            ValueError: If ``chunk_size`` is zero or negative.
        """
        size = resolve_chunk_size(chunk_size, self.default_read_chunk_size)
        raw = await self.stat(path)
        if raw.kind is PathKind.DIRECTORY:
            raise IsADirectoryError(path)
        # explicit close, not `async with`: opendal's AsyncFile.__aexit__
        # stub is mistyped as returning None instead of an awaitable
        try:
            file = await self._op.open(self._key(path), 'rb')
            try:
                while chunk := await file.read(size):
                    yield chunk
            finally:
                await file.close()
        except _OPENDAL_ERRORS as exc:
            raise self._error(exc, path) from exc

    async def write_stream(
        self,
        path: PurePosixPath,
        data: AsyncIterator[bytes],
        *,
        chunk_size: int | None = None,
        mode: EchoMode,
        content_type: str | None,
        metadata: Mapping[str, str] | None = None,
    ) -> None:
        """Write a file from a bounded chunk stream.

        Raises:
            ValueError: If ``chunk_size`` is zero or negative.
        """
        size = resolve_chunk_size(chunk_size, self.default_write_chunk_size)
        try:
            raw = await self.stat(path)
        except PathNotFoundError:
            raw = None
        if raw is not None and raw.kind is PathKind.DIRECTORY:
            raise IsADirectoryError(path)

        key = self._key(path)
        if raw is not None and mode == 'a':
            # ponytail: append is emulated as read + concat + rewrite; few
            # object stores append natively (cap.write_can_append if it matters)
            effective = raw.metadata if metadata is None else metadata
            options = self._write_options(content_type, effective)
            try:
                payload = await self._op.read(key)
                async for chunk in data:
                    payload += chunk
                await self._op.write(key, payload, **options)
            except _OPENDAL_ERRORS as exc:
                raise self._error(exc, path) from exc
            return

        options = self._write_options(content_type, metadata)
        try:
            file = await self._op.open(key, 'wb', **options)
            try:
                async for chunk in batch_chunks(data, size):
                    await file.write(chunk)
            finally:
                await file.close()
        except _OPENDAL_ERRORS as exc:
            raise self._error(exc, path) from exc

    @staticmethod
    def _write_options(
        content_type: str | None, metadata: Mapping[str, str] | None
    ) -> dict[str, Any]:
        """Build opendal write options for the capability-gated arguments."""
        options: dict[str, Any] = {}
        if content_type is not None:
            options['content_type'] = content_type
        if metadata:
            options['user_metadata'] = dict(metadata)
        return options

    async def delete(self, path: PurePosixPath) -> None:
        """Delete a leaf: a file or an *empty* directory.

        The emptiness check is explicit because opendal's delete is
        idempotent and never complains about children; relying on it
        would silently violate the leaf-delete contract.
        """
        raw = await self.stat(path)
        key = self._key(path)
        try:
            if raw.kind is PathKind.DIRECTORY:
                dir_key = self._dir_key(path)
                async for entry in await self._op.list(dir_key):
                    if entry.path.rstrip('/') != key:
                        raise DirectoryNotEmptyError(path)
                await self._op.delete(dir_key)
            else:
                await self._op.delete(key)
        except _OPENDAL_ERRORS as exc:
            raise self._error(exc, path) from exc

    async def list_dir(self, path: PurePosixPath) -> AsyncIterator[Entry]:
        """Yield the direct children of a directory, sizes included.

        List-first: one real child proves a non-empty directory, so the
        hot path is a single request. Only an empty (or failed) listing
        falls back to ``stat`` to tell a missing path and a file from a
        genuinely empty directory.
        """
        key = self._dir_key(path)
        try:
            # materialized snapshot: iteration must tolerate deletions
            listed = [entry async for entry in await self._op.list(key)]
        except _OPENDAL_ERRORS as exc:
            await self._require_directory(path)  # missing/file win over exc
            raise self._error(exc, path) from exc
        entries = [
            entry
            for entry in listed
            # opendal lists the directory itself; the port does not
            if entry.path.rstrip('/') != key.rstrip('/')
        ]
        if not entries:
            await self._require_directory(path)
        for entry in entries:
            is_dir = entry.metadata.is_dir
            yield Entry(
                name=entry.name.rstrip('/'),
                is_dir=is_dir,
                size=None if is_dir else entry.metadata.content_length,
            )

    async def _require_directory(self, path: PurePosixPath) -> None:
        """Stat ``path`` and enforce that it is a directory.

        Raises:
            PathNotFoundError: If nothing lives at ``path``.
            NotADirectoryError: If ``path`` is a file.
        """
        raw = await self.stat(path)
        if raw.kind is PathKind.FILE:
            raise NotADirectoryError(path)

    async def list_tree(self, path: PurePosixPath) -> AsyncIterator[PurePosixPath]:
        """Yield every descendant path via one recursive (delimiter-less) list.

        Streams lazily so the core can stop at its key bound without
        pulling the whole subtree into memory. opendal's directory-form
        keys carry a trailing slash; the port yields slash-free absolute
        paths and never the directory itself.
        """
        await self._require_directory(path)
        prefix = self._dir_key(path)
        try:
            entries = await self._op.list(prefix, recursive=True)
            async for entry in entries:
                key = entry.path.rstrip('/')
                if not key or key == prefix.rstrip('/'):
                    continue  # opendal may list the directory itself
                yield PurePosixPath('/') / key
        except _OPENDAL_ERRORS as exc:
            raise self._error(exc, path) from exc

    async def make_dir(self, path: PurePosixPath, *, parents: bool) -> None:
        """Create a directory (``parents=True`` behaves like mkdir -p).

        opendal's ``create_dir`` is recursive but only materializes the
        leaf marker, and implicit parents evaporate once emptied, so the
        port's contract is enforced explicitly here: plain mkdir checks
        the target and parent itself, and ``parents=True`` creates a
        real marker for every missing level.
        """
        try:
            existing = await self.stat(path)
        except PathNotFoundError:
            existing = None
        if existing is not None:
            if parents and existing.kind is PathKind.DIRECTORY:
                return
            raise AlreadyExistsError(path)

        if parents:
            for ancestor in reversed(path.parents):
                if not self._key(ancestor):
                    continue  # the operator root always exists
                try:
                    ancestor_raw = await self.stat(ancestor)
                except PathNotFoundError:
                    ancestor_raw = None
                if ancestor_raw is None:
                    await self._create_marker(ancestor)
                elif ancestor_raw.kind is not PathKind.DIRECTORY:
                    raise NotADirectoryError(ancestor)
        elif self._key(path.parent):
            parent_raw = await self.stat(path.parent)  # raises PathNotFound(parent)
            if parent_raw.kind is not PathKind.DIRECTORY:
                raise NotADirectoryError(path.parent)

        await self._create_marker(path)

    async def _create_marker(self, path: PurePosixPath) -> None:
        """Create one directory marker, translating opendal failures."""
        try:
            await self._op.create_dir(self._dir_key(path))
        except _OPENDAL_ERRORS as exc:
            raise self._error(exc, path) from exc

    async def set_metadata(
        self, path: PurePosixPath, metadata: Mapping[str, str]
    ) -> None:
        """Replace a file's custom metadata without touching its content.

        opendal has no standalone set-metadata operation, so this
        rewrites the object with its own content and the new metadata.
        """
        if not self.capabilities.custom_metadata:
            raise UnsupportedOperationError(Capability.CUSTOM_METADATA)
        raw = await self.stat(path)
        if raw.kind is PathKind.DIRECTORY:
            raise IsADirectoryError(path)
        key = self._key(path)
        try:
            payload = await self._op.read(key)
            await self._op.write(
                key, payload, user_metadata=dict(metadata) if metadata else None
            )
        except _OPENDAL_ERRORS as exc:
            raise self._error(exc, path) from exc

    async def make_url(
        self, path: PurePosixPath, *, expires_in: int | None = None
    ) -> str:
        """Mint a presigned read URL via opendal's native presign.

        ``None`` applies the storix default lifetime.
        """
        if not self.capabilities.presigned_urls:
            raise UnsupportedOperationError(Capability.PRESIGNED_URLS)
        if expires_in is None:
            expires_in = DEFAULT_URL_EXPIRY_SECONDS
        raw = await self.stat(path)
        if raw.kind is PathKind.DIRECTORY:
            raise IsADirectoryError(path)
        try:
            request = await self._op.presign_read(self._key(path), expires_in)
        except _OPENDAL_ERRORS as exc:
            raise self._error(exc, path) from exc
        return request.url
