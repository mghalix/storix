# storix task runner. Run `just` (or `just default`) to list everything.
# Recipes mirror CI, so `just check` locally == the push gate.

# tracked python files, space-joined — exactly what CI lints (excludes scratch)
_py := `git ls-files '*.py' | tr '\n' ' '`

# Show available recipes. Start here when you forget the command.
default:
    @just --list

# One-time dev setup after cloning: sync deps (all extras + dev).
setup:
    uv sync --all-extras --dev

# Regenerate the sync tree from the async source of truth.
# Run after ANY edit under src/storix/_async/ — never edit _sync/ by hand.
gen:
    uv run python scripts/unasync.py

# Lint with Ruff (the CI lint gate).
lint:
    uv run ruff check {{ _py }}

# Auto-fix lint + format in place.
fmt:
    uv run ruff check {{ _py }} --fix
    uv run ruff format {{ _py }}

# Run the tests. Unit only by default (integration is opt-in);
# pass args through: `just test -k cache -x`.
test *args:
    uv run pytest {{ args }}

# Run the azure integration suite (needs STORIX_AZURE_* / ADLSG2_* creds).
test-int *args:
    uv run pytest -m integration {{ args }}

# Coverage report + open the HTML.
cov:
    ./scripts/coverage

# Build the wheel + sdist.
build:
    uv build

# Every CI gate locally, before pushing: lint, format, codegen drift, tests.
check:
    uv run ruff check {{ _py }}
    uv run ruff format --check {{ _py }}
    uv run python scripts/unasync.py --check
    uv run pytest -q

# Release preflight — the full gate incl. build, no side effects.
release-check:
    uv run python scripts/release.py check

# Guarded release: gate, verify main is ready, then tag + push (confirms first).
release:
    uv run python scripts/release.py tag

# Remove python caches + build artifacts.
clean:
    ./scripts/clean

# Run a sample by path: `just sample layers/configurable_cache.py`.
sample path:
    uv run python samples/{{ path }}

# Serve the docs site locally with live reload (opens the browser).
docs:
    cd website && uvx zensical serve -o

# Build the docs site into website/site.
docs-build:
    cd website && uvx zensical build --strict

# Install generated brand assets. Optionally pass a source directory.
brand *args:
    ./scripts/brand {{ args }}
