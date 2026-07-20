# Contributing to Storix

Thanks for considering a contribution to Storix. The project is pre-1.0, so there
is plenty of surface area to improve (from API design to documentation to new
provider backends).

## Ways to contribute

Not every contribution is a pull request. The following are all valuable:

- **Bug reports**: with version, backend, and a minimal reproducer.
- **Workflow descriptions**: tell us what you are building and where Storix
  fits (or does not fit). These shape the API more than any single PR.
- **API design discussions**: start a GitHub Discussion thread.
- **Documentation**: typo fixes, missing examples, clearer explanations.
- **Provider requests**: if you need a backend we do not support yet.
- **Integration ideas**: how Storix could work with other tools in your stack.
- **Performance findings**: benchmarks, profiling results, regressions.
- **Pull requests**: bug fixes, features, refactors, test coverage.

## Development setup

Storix uses [uv](https://docs.astral.sh/uv/) for dependency management and
[just](https://github.com/casey/just) as a command runner.

Clone and set up the repository:

```bash
git clone https://github.com/mghalix/storix.git
cd storix
uv sync --locked --all-extras --all-groups
```

Verify everything works:

```bash
just check
```

The commands below assume `just` is available on your PATH. If it is not
installed globally, run the same recipes through the project environment by
prefixing them with `uv run`, for example: `uv run just check`.

### Useful commands

| Command | What it does |
| --- | --- |
| `just test-unit` | Run unit tests |
| `just typing` | Type-check with BasedPyright and mypy |
| `just fmt` | Auto-format with Ruff |
| `just check` | Full pre-submit gate |
| `just docs-build` | Build documentation site strictly |

## The async-first rule

Storix is async-first. The synchronous API is **generated** from the async
source by running:

```bash
just gen
```

**Edit only files in `_async/` trees.** Never hand-edit anything under `_sync/`.
The unasync script will regenerate the sync code for you.

If your change touches async code, run `just gen` before committing so
the sync tree stays in lockstep.

## Pull request process

1. Fork the repo and create a branch from `main`.
2. Make your changes (see the async-first rule above).
3. Run the full gate before pushing:
   ```bash
   just check
   ```
4. Open a PR against `main`.

### Commit and PR conventions

- Use **conventional commits** (`feat:`, `fix:`, `docs:`, `refactor:`, etc.).
- PRs are **squash-merged**. Your PR title becomes the final commit message, so
  make it descriptive.
- Keep PRs focused. One logical change per PR is easier to review and revert.

## Code style

[Ruff](https://docs.astral.sh/ruff/) handles both formatting and linting.

```bash
just fmt
```

The CI gate enforces style, so running `just fmt` locally saves a round trip.

## Testing

- Tests use **pytest**.
- For unit tests, use `MemoryBackend`: it is fast and requires no credentials
  or external services.
- Storix has a **conformance suite** that runs the same assertions against every
  backend. If you add a new operation, add it to the conformance suite so every
  provider picks it up.

```bash
just test-unit
```

## Community conversations & design discussions

Storix follows a **workflow-first** approach to API design.

- **GitHub Discussions**: Use [Discussions](https://github.com/mghalix/storix/discussions)
  for questions, workflow exploration, integration ideas, provider requests, or design proposals.
- **GitHub Issues**: Use [Issues](https://github.com/mghalix/storix/issues) for confirmed,
  reproducible bugs and already-scoped implementation tasks.

Small, self-contained fixes can go directly to a pull request. For new
workflows, public API changes, providers, integrations, or architectural
changes, start a discussion before investing in an implementation.

## Community norms

Disagreement is welcome. Design challenges are welcome. Both should be
respectful and grounded in real use cases. "I tried to do X and hit wall Y" is
more useful than "this API is wrong."
