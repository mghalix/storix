import dataclasses
import datetime as dt

from collections.abc import Mapping
from typing import ClassVar, NamedTuple, Self

from pydantic import BaseModel, ConfigDict, SecretStr

from storix.enums import Capability, PathKind


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


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
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


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class Capabilities:
    """User-observable optional features a backend supports.

    Consulted by the core to fail loudly (``UnsupportedOperationError``)
    instead of silently dropping arguments a backend cannot honor. Never
    encodes performance traits (native move, batch delete) — those are
    expressed by overriding ``BackendBase`` methods and are invisible to
    users. Every field defaults to False so adding a capability is
    non-breaking for existing backends.
    """

    content_type: bool = False
    """Can persist a MIME content type alongside written files."""

    custom_metadata: bool = False
    """Can attach arbitrary key/value metadata to paths."""

    presigned_urls: bool = False
    """Can mint time-limited shareable URLs (e.g. SAS) for paths."""

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
