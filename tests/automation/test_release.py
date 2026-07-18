"""Tests for repository release automation."""

# pyright: reportPrivateUsage=false

from datetime import date
from pathlib import Path

import pytest

from release.prepare import (
    Bump,
    _ReleaseError,
    _bump_version,
    _normalize_generated_notes,
    _prepare_release,
    _prepend_release,
    _read_project_version,
    _release_notes,
    _verify_tag,
)


@pytest.mark.parametrize(
    ('bump', 'expected'),
    [
        ('patch', '0.1.2'),
        ('minor', '0.2.0'),
        ('major', '1.0.0'),
    ],
)
def test_bump_version_uses_semver(bump: Bump, expected: str) -> None:
    # Given
    current = '0.1.1'

    # When
    actual = _bump_version(current, bump)

    # Then
    assert actual == expected


def test_prepend_release_adds_version_before_existing_history() -> None:
    # Given
    history = '# Release notes\n\nIntro.\n\n## 0.1.1 - 2026-07-16\n\n- Old.\n'

    # When
    actual = _prepend_release(
        history,
        '0.1.2',
        date(2026, 7, 17),
        "## What's Changed\n\n* fix: new behavior.\n",
    )

    # Then
    assert actual == (
        '# Release notes\n\n'
        'Intro.\n\n'
        '## 0.1.2 - 2026-07-17\n\n'
        "### What's Changed\n\n"
        '* fix: new behavior.\n\n'
        '## 0.1.1 - 2026-07-16\n\n'
        '- Old.\n'
    )


def test_prepend_release_rejects_existing_version() -> None:
    # Given
    history = '# Release notes\n\n## 0.1.2 - 2026-07-17\n\n- Existing.\n'

    # When / Then
    with pytest.raises(_ReleaseError, match='already contain'):
        _prepend_release(history, '0.1.2', date(2026, 7, 17), '- New.\n')


def test_normalize_generated_notes_rejects_empty_content() -> None:
    # Given
    generated = (
        '<!-- Release notes generated using configuration in repo -->\n\n'
        "## What's Changed\n\n"
        '**Full Changelog**: https://example.test/v0.1.1...v0.1.2\n'
    )

    # When / Then
    with pytest.raises(_ReleaseError, match='empty'):
        _normalize_generated_notes(generated)


@pytest.mark.parametrize(
    ('history', 'expected_heading'),
    [
        (
            '# Release notes\n\n## [0.4.3] - 2026-07-17\n\n- Old.\n',
            '## [0.4.4] - 2026-07-18',
        ),
        (
            '# Release notes\n\n## 0.4.3 (2026-07-17)\n\n- Old.\n',
            '## 0.4.4 (2026-07-18)',
        ),
        (
            '# Release notes\n\n## v0.4.3 (2026-07-17)\n\n- Old.\n',
            '## v0.4.4 (2026-07-18)',
        ),
    ],
)
def test_prepend_release_preserves_heading_style(
    history: str,
    expected_heading: str,
) -> None:
    # When
    actual = _prepend_release(history, '0.4.4', date(2026, 7, 18), '- New.\n')

    # Then
    assert expected_heading in actual
    assert _release_notes(actual, '0.4.4') == '- New.\n'


def test_prepare_release_updates_uv_project_and_release_notes(tmp_path: Path) -> None:
    # Given
    project = tmp_path / 'pyproject.toml'
    project.write_text(
        '[project]\nname = "demo"\nversion = "0.1.1"\nrequires-python = ">=3.12"\n'
    )
    history = tmp_path / 'release-notes.md'
    history.write_text('# Release notes\n\n## 0.1.1 - 2026-07-16\n\n- Old.\n')
    generated = tmp_path / 'generated.md'
    generated.write_text("## What's Changed\n\n* feat: new release.\n")

    # When
    actual = _prepare_release(
        project,
        history,
        generated,
        'patch',
        date(2026, 7, 17),
    )

    # Then
    assert actual == '0.1.2'
    assert _read_project_version(project) == '0.1.2'
    assert '## 0.1.2 - 2026-07-17' in history.read_text()
    assert (tmp_path / 'uv.lock').is_file()


def test_release_notes_extracts_requested_version() -> None:
    # Given
    history = (
        '# Release notes\n\n'
        '## 0.1.2 - 2026-07-17\n\n'
        '### Fixes\n\n'
        '- New release.\n\n'
        '## 0.1.1 - 2026-07-16\n\n'
        '- Previous release.\n'
    )

    # When
    actual = _release_notes(history, '0.1.2')

    # Then
    assert actual == '### Fixes\n\n- New release.\n'


def test_verify_tag_checks_version_and_release_notes(tmp_path: Path) -> None:
    # Given
    project = tmp_path / 'pyproject.toml'
    project.write_text('[project]\nname = "demo"\nversion = "0.1.2"\n')
    history = tmp_path / 'release-notes.md'
    history.write_text('# Release notes\n\n## 0.1.2 - 2026-07-17\n\n- New release.\n')

    # When
    _verify_tag(project, history, 'v', 'v0.1.2')

    # Then
    assert _read_project_version(project) == '0.1.2'


def test_verify_tag_rejects_mismatched_tag(tmp_path: Path) -> None:
    # Given
    project = tmp_path / 'pyproject.toml'
    project.write_text('[project]\nname = "demo"\nversion = "0.1.2"\n')
    history = tmp_path / 'release-notes.md'
    history.write_text('# Release notes\n')

    # When / Then
    with pytest.raises(_ReleaseError, match='does not match expected tag'):
        _verify_tag(project, history, 'v', 'v0.2.0')
