"""Tests for Storix repository workflow contracts."""

import re
import tomllib

from pathlib import Path
from typing import Final


_ROOT: Final[Path] = Path(__file__).parents[2]
_WORKFLOW_DIRECTORY: Final[Path] = _ROOT / '.github' / 'workflows'
_CANONICAL_NOTES: Final[Path] = _ROOT / 'website' / 'docs' / 'release-notes.md'
_ACTION_PATTERN: Final[re.Pattern[str]] = re.compile(
    r'(?m)^\s*uses:\s+(?P<action>[^\s]+)'
)


def _workflow(name: str) -> str:
    return (_WORKFLOW_DIRECTORY / name).read_text()


def test_every_third_party_action_uses_a_full_commit_sha() -> None:
    # Given
    workflows = tuple(_WORKFLOW_DIRECTORY.glob('*.yml'))

    # When
    references = [
        match.group('action').rsplit('@', 1)[-1]
        for workflow in workflows
        for match in _ACTION_PATTERN.finditer(workflow.read_text())
        if not match.group('action').startswith('./')
    ]

    # Then
    assert references
    assert all(re.fullmatch(r'[0-9a-f]{40}', reference) for reference in references)


def test_every_workflow_uses_the_same_uv_pin() -> None:
    # Given
    workflows = tuple(_WORKFLOW_DIRECTORY.glob('*.yml'))

    # When
    pins = {
        match.group(1)
        for workflow in workflows
        for match in re.finditer(
            r'uses: astral-sh/setup-uv@[0-9a-f]{40}.*?\n'
            r'(?:.*\n){0,6}?\s+version: "([^"]+)"',
            workflow.read_text(),
        )
    }

    # Then
    assert pins == {'0.11.18'}


def test_draft_release_uses_locked_just() -> None:
    # Given
    project = tomllib.loads((_ROOT / 'pyproject.toml').read_text())
    workflow = _workflow('create-draft-release.yml')

    # When
    development = project['dependency-groups']['dev']

    # Then
    assert any(requirement.startswith('rust-just') for requirement in development)
    assert 'uv run --no-sync just release-check' in workflow


def test_release_entrypoints_are_default_branch_only() -> None:
    # Given
    prepare = _workflow('prepare-release.yml')
    draft = _workflow('create-draft-release.yml')

    # When / Then
    assert 'if: github.ref_name == github.event.repository.default_branch' in prepare
    assert '  workflow_dispatch:\n' in draft
    assert 'github.ref_name == github.event.repository.default_branch' in draft
    assert (
        'github.event.pull_request.base.ref == '
        'github.event.repository.default_branch' in draft
    )
    assert "github.event_name == 'workflow_dispatch' && github.sha" in draft
    assert 'github.event.pull_request.merge_commit_sha' in draft


def test_prepare_stages_only_release_metadata() -> None:
    # Given
    workflow = _workflow('prepare-release.yml')

    # When
    staged = re.search(r'git add -- (?P<files>[^\n]+)', workflow)

    # Then
    assert staged is not None
    assert staged.group('files').split() == [
        'pyproject.toml',
        'uv.lock',
        '"website/docs/release-notes.md"',
    ]
    assert 'uv build' not in workflow
    assert 'uv publish' not in workflow
    assert 'gh release create' not in workflow


def test_canonical_notes_exist_exactly_once() -> None:
    # Given
    notes = _CANONICAL_NOTES.read_text()
    project = tomllib.loads((_ROOT / 'pyproject.toml').read_text())
    helper = (_ROOT / 'release' / 'prepare.py').read_text()

    # When / Then
    assert not (_ROOT / 'release-notes.md').exists()
    assert not re.search(r'(?m)^## Unreleased\s*$', notes)
    assert project['project']['urls']['Changelog'].endswith(
        '/website/docs/release-notes.md'
    )
    assert re.search(r'Path\(\s*["\']website/docs/release-notes\.md["\']\s*\)', helper)


def test_publish_reuses_verified_release_assets() -> None:
    # Given
    workflow = _workflow('release.yml')

    # When / Then
    assert 'uv build' not in workflow
    assert 'gh release verify ' in workflow
    assert 'gh release verify-asset' in workflow
    assert 'gh attestation verify' in workflow
    assert '--signer-workflow' in workflow
    assert '--source-digest' in workflow
    assert '--trusted-publishing always' in workflow
    assert '--check-url https://pypi.org/simple/' in workflow
    assert 'name: pypi' in workflow
    assert 'id-token: write' in workflow
    assert 'RELEASE_AUTHOR: ${{ github.event.release.author.login }}' in workflow
    assert '"github-actions[bot]"' in workflow


def test_lower_bounds_cover_every_runtime_extra() -> None:
    # Given
    workflow = _workflow('ci.yml')

    # When / Then
    assert 'uv sync --locked --all-extras --all-groups' in workflow
    assert 'uv pip install --python .venv/bin/python' in workflow
    assert '--resolution lowest-direct --reinstall --refresh' in workflow
    assert '".[all]"' in workflow
    assert (
        'uv pip tree --python .venv/bin/python --package storix --depth 1' in workflow
    )
    assert 'pytest -q --ignore=tests/automation' in workflow
    assert 'uv lock --resolution lowest-direct' not in workflow


def test_artifact_smoke_uses_the_reusable_isolation_boundary() -> None:
    # Given
    runner = _ROOT / 'scripts' / 'smoke'
    orchestrator = (_ROOT / 'tests' / 'smoke' / 'distributions.py').read_text()
    missing_extra = (_ROOT / 'tests' / 'smoke' / 'missing_extra.py').read_text()
    workflow = _workflow('ci.yml')

    # When / Then
    assert runner.stat().st_mode & 0o111
    runner_text = runner.read_text()
    for term in (
        'mktemp -d',
        'uv venv',
        'uv pip install',
        '--refresh',
        '--link-mode copy',
        '-u PYTHONPATH',
        '-u UV_PROJECT_ENVIRONMENT',
        '-u VIRTUAL_ENV',
    ):
        assert term in runner_text
    assert "_ROOT / 'scripts' / 'smoke'" in orchestrator
    assert "('missing-s3', 'missing_extra.py', '-')" in orchestrator
    assert "'storix[s3]'" in missing_extra
    assert 'python tests/smoke/distributions.py dist' in workflow


def test_reviewed_tool_floors_and_typing_scope_are_locked() -> None:
    # Given
    project = tomllib.loads((_ROOT / 'pyproject.toml').read_text())

    # When
    development = project['dependency-groups']['dev']
    typing_paths = project['tool']['basedpyright']['include']

    # Then
    for requirement in (
        'commitizen>=4.16.5',
        'prek>=0.4.10',
        'rust-just>=1.56.0',
        'twine>=6.2.0',
        'vulture>=2.16',
        'zizmor>=1.27.0',
    ):
        assert any(item.startswith(requirement) for item in development)
    assert project['build-system']['requires'] == ['uv_build>=0.10.0,<0.12.0']
    for path in ('src', 'release', 'tests/automation', 'tests/smoke', 'tests/typing'):
        assert path in typing_paths


def test_ci_has_one_stable_required_aggregate() -> None:
    # Given
    workflow = _workflow('ci.yml')

    # When / Then
    assert workflow.count('name: Required') == 1
    assert 'if: always()' in workflow
    for dependency in (
        'core',
        'unit',
        'integration',
        'lower-bounds',
        'typing',
        'automation',
        'docs',
        'artifacts',
    ):
        assert f'      - {dependency}\n' in workflow
        assert f'${{{{ needs.{dependency}.result }}}}' in workflow
    assert 'test "${result}" = "success"' in workflow


def test_ci_preserves_the_async_codegen_contract() -> None:
    # Given
    workflow = _workflow('ci.yml')

    # When / Then
    assert 'scripts/unasync.py --check' in workflow
    matrix = 'python-version:\n          - "3.12"\n          - "3.13"'
    assert workflow.count(matrix) == 2


def test_release_check_is_verification_only_and_complete() -> None:
    # Given
    justfile = (_ROOT / 'justfile').read_text()
    expected_recipe = (
        'release-check: clean check dead-code audit-actions hooks-check '
        'examples docs-build smoke'
    )

    # When / Then
    assert re.search(rf'(?m)^{re.escape(expected_recipe)}$', justfile)
    assert not re.search(r'(?m)^release(?:\s[^-][^:]*)?:', justfile)
    for forbidden in ('git tag', 'git push', 'uv publish', 'gh release create'):
        assert forbidden not in justfile
