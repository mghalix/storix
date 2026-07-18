# Storix verification tasks. Run `just` to list them.

set shell := ["bash", "-euo", "pipefail", "-c"]

# Tracked Python files are the exact files CI checks. Scratch files stay local.
_py := `git ls-files '*.py' | while IFS= read -r path; do test ! -f "$path" || printf '%q ' "$path"; done`

default:
    @just --list

# Install the complete locked development environment.
setup:
    uv sync --locked --all-extras --all-groups

# Remove caches and build outputs only.
clean:
    ./scripts/clean

# Regenerate the sync source and test trees from their async sources.
gen:
    uv run --no-sync python scripts/unasync.py

# Verify that generated sync files match the async source of truth.
gen-check:
    uv run --no-sync python scripts/unasync.py --check

# Check all tracked Python files with Ruff.
lint:
    uv run --no-sync ruff check {{ _py }}

# Check formatting without changing files.
format-check:
    uv run --no-sync ruff format --check {{ _py }}

# Apply the repository's Ruff fixes and formatting.
fmt:
    uv run --no-sync ruff check {{ _py }} --fix
    uv run --no-sync ruff format {{ _py }}

# Run the offline suite (unit + conformance) with branch coverage. Cloud cases stay opt-in.
test-unit *args:
    uv run --no-sync coverage run --branch --source=storix -m pytest tests/unit tests/conformance {{ args }}
    uv run --no-sync coverage report --fail-under=60

# Real-provider conformance. Auto-loads .env if present (STORIX_ENV_FILE overrides path). Missing creds skip.
test-integration *args:
    #!/usr/bin/env bash
    env_file="${STORIX_ENV_FILE:-.env}"
    if [[ -f "$env_file" ]]; then
        uv run --no-sync --env-file "$env_file" \
            pytest tests/conformance -m integration {{ args }}
    else
        uv run --no-sync pytest tests/conformance -m integration {{ args }}
    fi

# Backward-compatible alias for the previous recipe name.
test-int *args:
    just test-integration {{ args }}

# Test repository and release automation separately from the SDK.
test-automation *args:
    uv run --no-sync pytest -q tests/automation {{ args }}

# Run every local test layer that needs no external credentials.
test: test-unit test-automation

# Check the public package and type-oriented examples with both type checkers.
typing:
    uv run --no-sync basedpyright
    uv run --no-sync mypy src

# Report dead code at the requested confidence threshold.
dead-code confidence="100":
    uv run --no-sync vulture src release scripts/unasync.py --min-confidence {{ confidence }}

# Audit GitHub Actions offline with locked zizmor.
audit-actions persona="pedantic" severity="low":
    uv run --no-sync zizmor --offline --persona={{ persona }} --min-severity={{ severity }} .github/workflows

# Install the repository-managed Conventional Commit hook.
hooks:
    PREK_HOME=.cache/prek uv run --no-sync prek install --hook-type commit-msg

# Validate the hook configuration and run all applicable hooks.
hooks-check:
    PREK_HOME=.cache/prek uv run --no-sync prek validate-config .pre-commit-config.yaml
    PREK_HOME=.cache/prek uv run --no-sync prek run --all-files

# Validate every commit introduced after a base revision.
commits base="origin/main":
    uv run --no-sync cz check --rev-range "{{ base }}..HEAD"

# Run the complete local source and automation gate.
check: lint format-check gen-check typing test

# Run representative offline examples from the documentation.
examples:
    uv run --no-sync python samples/quickstart.py
    uv run --no-sync python samples/quickstart_async.py
    uv run --no-sync python samples/layers/configurable_cache.py
    uv run --no-sync python samples/recipes/custom_layer.py

# Build publishable wheel and source distributions without workspace sources.
build:
    uv build --no-sources
    uv run --no-sync twine check dist/*

# Install the exact wheel and sdist in fresh environments and exercise them.
smoke: build
    uv run --no-sync python tests/smoke/distributions.py dist

# Build the documentation with its locked toolchain and strict checks.
docs-build:
    cd website && uv run --project .. --no-sync zensical build --strict

# Serve the documentation locally with live reload.
docs:
    cd website && uv run --project .. --no-sync zensical serve -o

# Run a sample by repository-relative path, for example `just sample quickstart.py`.
sample path:
    uv run --no-sync python samples/{{ path }}

# Reproduce the complete candidate gate without versioning or publishing.
release-check: clean check dead-code audit-actions hooks-check examples docs-build smoke
