"""Prepare and validate releases for a standard uv Python project."""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tomllib

from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Final, Literal, cast


if TYPE_CHECKING:
    from collections.abc import Sequence


type Bump = Literal['major', 'minor', 'patch']

_DEFAULT_PROJECT_FILE: Final[Path] = Path('pyproject.toml')
_DEFAULT_RELEASE_NOTES_FILE: Final[Path] = Path('website/docs/release-notes.md')
_DEFAULT_TAG_PREFIX: Final[str] = 'v'
_SEMVER_PATTERN: Final[re.Pattern[str]] = re.compile(r'^(\d+)\.(\d+)\.(\d+)$')
_HEADING_PATTERN: Final[re.Pattern[str]] = re.compile(
    r'(?m)^## (?P<title>[^\r\n]+?)[ \t]*$'
)
_MARKDOWN_HEADING_PATTERN: Final[re.Pattern[str]] = re.compile(
    r'^(?P<marks>#{1,6}) (?P<title>.+)$'
)
_RELEASE_DATE: Final[str] = r'\d{4}-\d{2}-\d{2}'
_PLAIN_RELEASE_PATTERN: Final[re.Pattern[str]] = re.compile(
    rf'^\d+\.\d+\.\d+ - {_RELEASE_DATE}$'
)
_BRACKETED_RELEASE_PATTERN: Final[re.Pattern[str]] = re.compile(
    rf'^\[\d+\.\d+\.\d+\] - {_RELEASE_DATE}$'
)
_PARENTHESIZED_RELEASE_PATTERN: Final[re.Pattern[str]] = re.compile(
    rf'^\d+\.\d+\.\d+ \({_RELEASE_DATE}\)$'
)
_V_PREFIX_RELEASE_PATTERN: Final[re.Pattern[str]] = re.compile(
    rf'^v\d+\.\d+\.\d+ \({_RELEASE_DATE}\)$'
)


class _ReleaseError(RuntimeError):
    """Raised when repository release state is invalid."""


@dataclass(frozen=True)
class _Section:
    """A second-level Markdown section."""

    title: str
    start: int
    body_start: int
    end: int


def _parse_version(version: str) -> tuple[int, int, int]:
    match = _SEMVER_PATTERN.fullmatch(version)
    if match is None:
        message = f'Invalid version {version!r}; expected X.Y.Z'
        raise _ReleaseError(message)
    major, minor, patch = match.groups()
    return int(major), int(minor), int(patch)


def _bump_version(version: str, bump: Bump) -> str:
    major, minor, patch = _parse_version(version)
    if bump == 'major':
        return f'{major + 1}.0.0'
    if bump == 'minor':
        return f'{major}.{minor + 1}.0'
    return f'{major}.{minor}.{patch + 1}'


def _read_project_version(project_file: Path) -> str:
    data = cast('dict[str, object]', tomllib.loads(project_file.read_text()))
    project = data.get('project')
    if not isinstance(project, dict):
        message = f'{project_file} has no [project] table'
        raise _ReleaseError(message)

    project_data = cast('dict[str, object]', project)
    version = project_data.get('version')
    if not isinstance(version, str):
        message = f'{project_file} has no static [project].version'
        raise _ReleaseError(message)

    _parse_version(version)
    return version


def _sections(content: str) -> list[_Section]:
    matches = list(_HEADING_PATTERN.finditer(content))
    return [
        _Section(
            title=match.group('title'),
            start=match.start(),
            body_start=match.end(),
            end=matches[index + 1].start()
            if index + 1 < len(matches)
            else len(content),
        )
        for index, match in enumerate(matches)
    ]


def _version_title_pattern(version: str) -> re.Pattern[str]:
    escaped_version = re.escape(version)
    return re.compile(
        rf'^(?:{escaped_version}|\[{escaped_version}\]) - {_RELEASE_DATE}$'
        rf'|^(?:v?{escaped_version}) \({_RELEASE_DATE}\)$'
    )


def _is_release_title(title: str) -> bool:
    return any(
        pattern.fullmatch(title)
        for pattern in (
            _PLAIN_RELEASE_PATTERN,
            _BRACKETED_RELEASE_PATTERN,
            _PARENTHESIZED_RELEASE_PATTERN,
            _V_PREFIX_RELEASE_PATTERN,
        )
    )


def _version_section(content: str, version: str) -> _Section:
    title_pattern = _version_title_pattern(version)
    matches = [
        section
        for section in _sections(content)
        if title_pattern.fullmatch(section.title)
    ]
    if len(matches) != 1:
        message = (
            f'Release notes must contain exactly one release section for {version}'
        )
        raise _ReleaseError(message)
    return matches[0]


def _release_title(content: str, version: str, release_date: date) -> str:
    for section in _sections(content):
        if _BRACKETED_RELEASE_PATTERN.fullmatch(section.title):
            return f'[{version}] - {release_date.isoformat()}'
        if _V_PREFIX_RELEASE_PATTERN.fullmatch(section.title):
            return f'v{version} ({release_date.isoformat()})'
        if _PARENTHESIZED_RELEASE_PATTERN.fullmatch(section.title):
            return f'{version} ({release_date.isoformat()})'
        if _PLAIN_RELEASE_PATTERN.fullmatch(section.title):
            break
    return f'{version} - {release_date.isoformat()}'


def _normalize_generated_notes(content: str) -> str:
    normalized: list[str] = []
    has_substantive_content = False
    for line in content.strip().splitlines():
        if line.startswith('<!-- Release notes generated using configuration'):
            continue
        if line.startswith('**Full Changelog**:'):
            continue
        match = _MARKDOWN_HEADING_PATTERN.fullmatch(line)
        if match is None:
            normalized.append(line)
            if line.strip():
                has_substantive_content = True
            continue

        level = max(3, min(len(match.group('marks')) + 1, 6))
        normalized.append(f'{"#" * level} {match.group("title")}')

    notes = '\n'.join(normalized).strip()
    if not notes or not has_substantive_content:
        message = 'Generated release notes are empty'
        raise _ReleaseError(message)
    return notes


def _prepend_release(
    content: str,
    version: str,
    release_date: date,
    generated_notes: str,
) -> str:
    if any(
        _version_title_pattern(version).fullmatch(section.title)
        for section in _sections(content)
    ):
        message = f'Release notes already contain a section for {version}'
        raise _ReleaseError(message)

    notes = _normalize_generated_notes(generated_notes)
    release_sections = [
        section for section in _sections(content) if _is_release_title(section.title)
    ]
    insert_at = release_sections[0].start if release_sections else len(content)
    prefix = content[:insert_at].rstrip()
    suffix = content[insert_at:].lstrip()
    title = _release_title(content, version, release_date)
    prepared = f'{prefix}\n\n## {title}\n\n{notes}\n'
    if suffix:
        prepared = f'{prepared}\n{suffix}'
    return prepared


def _release_notes(content: str, version: str) -> str:
    section = _version_section(content, version)
    notes = content[section.body_start : section.end].strip()
    if not notes:
        message = f'Release notes section for {version} is empty'
        raise _ReleaseError(message)
    return f'{notes}\n'


def _prepare_release(
    project_file: Path,
    release_notes_file: Path,
    generated_notes_file: Path,
    bump: Bump,
    release_date: date,
) -> str:
    if project_file.name != 'pyproject.toml':
        message = 'uv projects must use a pyproject.toml project file'
        raise _ReleaseError(message)

    current_version = _read_project_version(project_file)
    next_version = _bump_version(current_version, bump)
    prepared_notes = _prepend_release(
        release_notes_file.read_text(),
        next_version,
        release_date,
        generated_notes_file.read_text(),
    )

    uv = shutil.which('uv')
    if uv is None:
        message = 'uv is required to prepare a release'
        raise _ReleaseError(message)

    # The version is constrained to numeric SemVer before it reaches uv.
    subprocess.run(  # noqa: S603
        [
            uv,
            'version',
            next_version,
            '--no-sync',
            '--project',
            str(project_file.parent),
        ],
        check=True,
    )
    actual_version = _read_project_version(project_file)
    if actual_version != next_version:
        message = f'uv wrote version {actual_version}, expected {next_version}'
        raise _ReleaseError(message)

    release_notes_file.write_text(prepared_notes)
    return next_version


def _verify_tag(
    project_file: Path,
    release_notes_file: Path,
    prefix: str,
    tag: str,
) -> None:
    version = _read_project_version(project_file)
    expected_tag = f'{prefix}{version}'
    if tag != expected_tag:
        message = f'Release tag {tag!r} does not match expected tag {expected_tag!r}'
        raise _ReleaseError(message)
    _release_notes(release_notes_file.read_text(), version)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prepare and validate a uv project's release metadata."
    )
    parser.add_argument(
        '--project-file',
        type=Path,
        default=_DEFAULT_PROJECT_FILE,
        help='project metadata file (default: pyproject.toml)',
    )
    parser.add_argument(
        '--release-notes-file',
        type=Path,
        default=_DEFAULT_RELEASE_NOTES_FILE,
        help='canonical release notes file',
    )
    parser.add_argument(
        '--tag-prefix',
        default=_DEFAULT_TAG_PREFIX,
        help='release tag prefix (default: v)',
    )

    commands = parser.add_subparsers(dest='command', required=True)
    prepare = commands.add_parser(
        'prepare', help='bump the version and prepend generated release notes'
    )
    prepare.add_argument('bump', choices=('patch', 'minor', 'major'))
    prepare.add_argument(
        '--notes-file',
        type=Path,
        required=True,
        help='generated Markdown notes to add to the release history',
    )
    prepare.add_argument(
        '--date',
        default=datetime.now(UTC).date().isoformat(),
        help='release date in YYYY-MM-DD format (default: today)',
    )
    next_version = commands.add_parser(
        'next-version', help='print the version produced by a SemVer bump'
    )
    next_version.add_argument('bump', choices=('patch', 'minor', 'major'))
    commands.add_parser('current-version', help='print the project version')
    commands.add_parser('release-tag', help='print the expected release tag')
    notes = commands.add_parser('release-notes', help="print one release's notes")
    notes.add_argument('--version', help='version to read (default: current version)')
    verify = commands.add_parser(
        'verify-tag', help='verify a tag against project metadata and release notes'
    )
    verify.add_argument('tag')
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    """Run the release helper command.

    Args:
        arguments: Command arguments without the executable name. Uses
            ``sys.argv`` when omitted.

    Returns:
        Zero on success, or one when release state is invalid.
    """
    namespace = _parser().parse_args(arguments)
    project_file = cast('Path', namespace.project_file)
    release_notes_file = cast('Path', namespace.release_notes_file)
    tag_prefix = cast('str', namespace.tag_prefix)
    command = cast('str', namespace.command)

    try:
        if command == 'prepare':
            bump = cast('Bump', namespace.bump)
            release_date = date.fromisoformat(cast('str', namespace.date))
            prepared_version = _prepare_release(
                project_file,
                release_notes_file,
                cast('Path', namespace.notes_file),
                bump,
                release_date,
            )
            sys.stdout.write(f'{prepared_version}\n')
        elif command == 'next-version':
            next_version = _bump_version(
                _read_project_version(project_file),
                cast('Bump', namespace.bump),
            )
            sys.stdout.write(f'{next_version}\n')
        elif command == 'current-version':
            sys.stdout.write(f'{_read_project_version(project_file)}\n')
        elif command == 'release-tag':
            sys.stdout.write(f'{tag_prefix}{_read_project_version(project_file)}\n')
        elif command == 'release-notes':
            requested_version = cast('str | None', namespace.version)
            version = requested_version or _read_project_version(project_file)
            sys.stdout.write(_release_notes(release_notes_file.read_text(), version))
        elif command == 'verify-tag':
            _verify_tag(
                project_file,
                release_notes_file,
                tag_prefix,
                cast('str', namespace.tag),
            )
        else:  # pragma: no cover - argparse constrains command names.
            sys.stderr.write(f'release: error: unknown command {command!r}\n')
            return 2
    except (OSError, ValueError, subprocess.CalledProcessError, _ReleaseError) as error:
        sys.stderr.write(f'release: error: {error}\n')
        return 1

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
