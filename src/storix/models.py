import datetime as dt

from collections.abc import Mapping
from typing import ClassVar, NamedTuple, Self

from pydantic import BaseModel, ConfigDict, SecretStr

from storix._dto import dto
from storix.enums import Capability, PathKind
from storix.types import StorixPath


class Entry(NamedTuple):
    """A single directory-listing entry as reported by a backend.

    Port-level DTO yielded by ``list_dir``. Carries the classification
    alongside the name so the core never issues a per-entry stat call just
    to tell files from directories.
    """

    name: str
    """Entry basename, without any directory components."""

    is_dir: bool
    """True when the entry is a directory."""

    size: int | None = None
    """Size in bytes when the listing provides it for free; else None."""


@dto
class RawStat:
    """Raw stat facts a backend reports for a path.

    Port-level DTO: constructed by backends from trusted OS/SDK data and
    shaped by the core into the user-facing :class:`FileProperties`.
    Deliberately a plain dataclass rather than a pydantic model — it crosses
    the port on every stat call and validating trusted data buys nothing.
    """

    kind: PathKind
    """Whether the path is a file or a directory."""

    size: int
    """Size in bytes. Backend-defined for directories (commonly 0)."""

    created: dt.datetime
    """Creation time as reported by the backend."""

    modified: dt.datetime
    """Last content-modification time."""

    accessed: dt.datetime | None = None
    """Last access time; None on backends without atime (most cloud stores)."""

    metadata: Mapping[str, str] | None = None
    """Custom key/value metadata when the backend supports it; else None."""

    version: str | None = None
    """Opaque validator for the state this stat describes, read from the same
    response as the rest of it (an ETag, a generation); None on backends
    without one. A token to hand back to a conditional write as ``if_match``,
    never to parse, order, or construct (ADR 0033)."""


@dto
class DirEntry:
    """A single directory-listing entry, session-resolved and user-facing.

    Mapped from the port's :class:`Entry` the way :class:`FileProperties`
    maps from :class:`RawStat`: it carries the kind (and any size the
    listing produced for free) so a consumer never stats every entry just
    to tell files from directories. Deliberately a plain ``@dto`` rather
    than a pydantic model - it crosses the port once per entry in a
    listing and validating trusted data buys nothing.
    """

    name: str
    """Entry basename, without any directory components."""

    path: StorixPath
    """Absolute, session-resolved path to the entry."""

    kind: PathKind
    """Whether the entry is a file or a directory (extensible: a future symlink)."""

    size: int | None = None
    """Size in bytes when the listing carried it for free; else None."""

    @property
    def is_dir(self) -> bool:
        """True when the entry is a directory."""
        return self.kind is PathKind.DIRECTORY

    @property
    def is_file(self) -> bool:
        """True when the entry is a file."""
        return self.kind is PathKind.FILE


@dto
class Capabilities:
    """User-observable optional features a backend supports.

    Consulted by the core to fail loudly (``UnsupportedOperationError``)
    instead of silently dropping arguments a backend cannot honor. Mostly
    does not encode performance traits (native move, batch delete) - those
    are expressed by overriding ``BackendBase`` methods and are invisible
    to users. The deliberate exception is ``bulk_listing`` (ADR 0027): a
    performance trait the core gates on internally, silently taking a fast
    path and falling back when it is absent, never raising. Every field
    defaults to False so adding a capability is non-breaking for existing
    backends.
    """

    content_type: bool = False
    """Can persist a MIME content type alongside written files."""

    custom_metadata: bool = False
    """Can attach arbitrary key/value metadata to paths."""

    presigned_urls: bool = False
    """Can mint time-limited shareable URLs (e.g. SAS) for paths."""

    ranged_reads: bool = False
    """Can fetch a byte range in one request, rather than by skipping
    through a stream from the start. Like ``bulk_listing``, an internal
    speed gate rather than a user-facing feature: every backend answers
    ``read_range`` correctly, and the core consults this only to decide
    whether reading one file through several parallel ranges is worth it
    (ADR 0032). Never raises."""

    bulk_listing: bool = False
    """Can list every descendant of a directory in one cheap operation
    (a single delimiter-less list on object stores). An internal speed
    gate, not a user-facing feature: the core derives a whole listing's
    child emptiness from one request when set, and falls back silently
    when it is not (ADR 0027)."""

    provisioning: bool = False
    """Can create its own storage root on demand - the bucket, container,
    or filesystem the backend is anchored to (a control-plane operation,
    distinct from ``mkdir`` inside the root). Advertised only when the
    backend's engine can do it: the native ADLS SDK and local/memory can;
    the opendal engines (S3/GCS/Azure Blob) are data-plane only and cannot.
    The core gates ``provision`` on this, raising when it is absent
    (ADR 0030)."""

    conditional_writes: bool = False
    """Can write only while the stored object still carries a given
    ``RawStat.version``, comparing and writing as one operation at the service
    (ADR 0033). Advertised only for a real guarantee: there is no emulation,
    because stat-then-compare-then-write reintroduces the race the feature
    exists to close."""

    exclusive_create: bool = False
    """Can write only while nothing exists at the path, as one operation
    (``If-None-Match: *``, ``O_EXCL``). Separate from ``conditional_writes``
    because the two are separate guarantees and a store can offer either
    without the other: local disk creates exclusively but cannot compare a
    version, and an S3-compatible endpoint may take ``If-None-Match`` while
    refusing ``If-Match``. One flag covering both would say yes to a caller
    the write then rejects (ADR 0033)."""

    def supports(self, capability: Capability) -> bool:
        """Whether the given capability is advertised."""
        return bool(getattr(self, capability))


class StorixBaseModel(BaseModel):
    """Base model for storix user-facing data models."""

    # TODO(pydantic): json_encoders is deprecated in pydantic v2 — replace
    # with field_serializer/model_serializer during the 0.2.0 refactor.
    model_config: ClassVar[ConfigDict] = ConfigDict(
        from_attributes=True,
        validate_assignment=True,
        arbitrary_types_allowed=True,
        str_strip_whitespace=True,
        json_encoders={
            # custom output conversion for datetime
            dt.datetime: lambda v: v.strftime('%Y-%m-%dT%H:%M:%S.%fZ') if v else None,
            SecretStr: lambda v: v.get_secret_value() if v else None,
        },
    )


class FileProperties(StorixBaseModel):
    """User-facing stat result for a path.

    Field names follow unix stat vocabulary (Birth/Modify/Access) and
    mirror :class:`RawStat`; ``str()`` renders a stat(1)-style block.
    """

    name: str
    """Path basename."""

    size: int
    """Size in bytes (apparent content bytes, like ``du -sb``)."""

    created: dt.datetime
    """Birth time."""

    modified: dt.datetime
    """Last content-modification time."""

    accessed: dt.datetime | None = None
    """Last access time; None on backends without atime."""

    kind: PathKind
    """Whether the path is a file or a directory."""

    metadata: Mapping[str, str] | None = None
    """Custom key/value metadata when the backend supports it; else None."""

    version: str | None = None
    """Opaque validator for the state this stat describes; None on backends
    without one. Hand it back to a write as ``if_match`` to make that write
    conditional on nothing having changed since (ADR 0033)."""

    @classmethod
    def from_raw(cls, name: str, raw: RawStat) -> Self:
        """Shape a port-level ``RawStat`` into the user-facing model.

        The two models deliberately stay separate: ``RawStat`` is the
        cheap trusted DTO crossing the port on every call; this is the
        validated pydantic surface (serialization, FastAPI responses).
        """
        return cls(
            name=name,
            size=raw.size,
            created=raw.created,
            modified=raw.modified,
            accessed=raw.accessed,
            kind=raw.kind,
            metadata=raw.metadata,
            version=raw.version,
        )

    def __str__(self) -> str:
        lines = [
            f'  File: {self.name}',
            f'  Size: {self.size}\t{self.kind}',
            f'Access: {self.accessed or "-"}',
            f'Modify: {self.modified}',
            f' Birth: {self.created}',
        ]
        if self.metadata:
            pairs = ', '.join(f'{k}={v}' for k, v in sorted(self.metadata.items()))
            lines.append(f'  Meta: {pairs}')
        return '\n'.join(lines)
