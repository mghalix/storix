# Releasing

Storix releases are prepared, reviewed, built, tagged, and published by GitHub
Actions. No local task changes the version, creates a tag, or publishes a
release.

## Release flow

```text
Run Prepare release and choose patch, minor, or major
    -> GitHub generates notes from merged pull requests since the last tag
    -> CI updates pyproject.toml, uv.lock, and the website release notes
    -> CI opens a release pull request
    -> curate the generated notes and merge only after Required passes
    -> CI rebuilds and verifies the exact merge commit
    -> CI attests the wheel and sdist and attaches them to a draft release
    -> review and publish the complete draft
    -> GitHub locks the release tag and assets
    -> CI verifies the immutable release and build provenance
    -> approve the protected pypi environment
    -> CI publishes those exact immutable assets through Trusted Publishing
```

There is one active release lane. Preparation stops when another release pull
request or draft release exists.

## Maintainer mental model

The workflow has four deliberate authorization points:

| Action | Meaning | Public effect |
| --- | --- | --- |
| Run `Prepare release` | Ask automation to propose a version and generated notes in a normal pull request. | None. No tag, release, or package exists. |
| Merge the release pull request | Approve the version and curated notes. Automation verifies that exact merge commit, builds it, creates the tag, and attaches attested assets to a draft release. | The versioned notes can reach the website, but the release and package are still private. |
| Publish the draft GitHub Release | Confirm that the tag, notes, wheel, and sdist are the intended public release. GitHub makes them immutable. | The GitHub Release becomes public and triggers the publishing workflow. |
| Approve the `pypi` environment | Authorize Trusted Publishing after the immutable release and provenance checks pass. | The exact reviewed assets become installable from PyPI. |

Preparation is therefore a proposal, not a release. Merging selects the exact
source commit and creates a reviewable candidate. Publishing the complete draft
is the public-release switch; the protected environment is the final package
registry switch.

## One-time repository setup

### Release automation GitHub App

The preparation workflow needs a token that can create a branch and pull
request while still triggering normal pull-request CI. GitHub suppresses most
workflow events created with the default `GITHUB_TOKEN`, so preparation uses a
short-lived GitHub App installation token instead of a personal access token.

Create or reuse a GitHub App with these repository permissions:

- Contents: Read and write
- Pull requests: Read and write

Install it on the repository. Create a GitHub environment named
`release-automation`, then add:

- Environment variable `RELEASE_APP_CLIENT_ID`
- Environment secret `RELEASE_APP_PRIVATE_KEY`

The same App can be installed on other owned repositories. Keep its repository
selection and permissions narrow.

### PyPI publishing

Create a GitHub environment named `pypi` and configure:

- required reviewers
- prevent self-review; this requires a second trusted person
- a deployment tag rule restricted to `v*`

Configure a PyPI Trusted Publisher for:

- repository: `mghalix/storix`
- workflow: `release.yml`
- environment: `pypi`

No PyPI API token belongs in GitHub secrets.

### Immutable releases

Open Settings -> General -> Releases and enable release immutability. This is a
required part of the flow: the publishing workflow rejects a release without a
valid GitHub release attestation.

Release assets are attached while the release is a draft. Publishing then
locks the tag and assets. Never move asset creation back after publication.

### Default branch ruleset

Protect the default branch with:

- require a pull request before merging
- require the single `Required` status check, with the branch up to date
- require conversation resolution
- require the squash merge type and linear history
- block force pushes and deletion

Under Settings -> General -> Pull Requests, allow squash merging only and set
its default commit message to the pull request title. The validated title then
becomes the clean Conventional Commit on the default branch; the pull request
body remains review context instead of automatic commit-message noise.

The `Required` job depends on every supported Python, integration, lower-bound,
automation, documentation, and artifact-smoke job. Requiring one stable check
keeps the ruleset correct when a matrix changes.

GitHub can only offer `Required` after a workflow run reports it. Keep existing
checks until the first run on this workflow completes, then require `Required`
and remove the individual jobs from the ruleset.

Consider a `v*` tag ruleset that blocks updates and deletion. If creation is also
restricted, configure a narrow bypass for the draft-release workflow and test
it with a non-production repository first.

## Release notes

`website/docs/release-notes.md` is the only release-history source. It is also
the page rendered by the documentation site and the URL published in package
metadata. It contains explicit version sections only: there is no rolling
`Unreleased` or `Latest Changes` section. A prepared entry may appear on the
site while its complete draft release awaits maintainer publication; the
GitHub Release and PyPI remain authoritative for whether that version is live.

GitHub generates a draft from merged pull requests between release tags using
`.github/release.yml`. Create these repository labels once, then apply them
before preparation when a pull request belongs in a specific category:

- `breaking-change`
- `enhancement` or `feature`
- `bug` or `fix`
- `documentation`
- `skip-changelog`

Unmatched pull requests appear under `Other changes`. Conventional pull
request titles keep those entries meaningful even without a label.

Generated notes are a draft, not publish-ready truth. The release pull request
must be curated: remove internal noise, improve wording, confirm breaking
changes, and keep only information users need. The preparation helper rejects
an empty generated release.

## Prepare a release

1. Confirm all intended pull requests are merged and labeled appropriately.
2. Open GitHub Actions -> Prepare release -> Run workflow.
3. Choose the bump:
   - Below 1.0.0, breaking change -> minor.
   - Below 1.0.0, feature or fix -> patch.
   - From 1.0.0, use standard SemVer.
4. Optionally enter a release date. Without one, the runner's current UTC date
   is used.
5. Curate the generated release notes in the release pull request.
6. Merge only after the single `Required` check passes.
7. Wait for CI to build, smoke-test, attest, and attach both distributions to
   the draft GitHub Release.
8. Review the draft assets and notes, then select Publish release.
9. Approve the `pypi` deployment when GitHub requests it.

The helper is `release/prepare.py`. Its read-only commands are:

```text
uv run python release/prepare.py current-version
uv run python release/prepare.py next-version patch
uv run python release/prepare.py release-tag
uv run python release/prepare.py release-notes
uv run python release/prepare.py verify-tag vX.Y.Z
```

Its `prepare` command mutates version metadata and is reserved for the
preparation workflow. Local release checks remain side-effect-free:

```text
uv run --no-sync just release-check
```

## What the workflows verify

Before publication, the workflows require all of the following:

- the release pull request came from this repository's `release/` branch
- an automatic release target is the merged release pull-request commit
- a manual recovery target is the exact default-branch commit running the
  workflow
- no release tag or draft already existed
- the tag equals `v` plus `[project].version`
- the canonical release notes have a non-empty section for that version
- the tagged commit remains in default-branch history
- tests, types, lint, examples, strict docs, metadata checks, and isolated
  wheel and source-distribution smoke tests pass
- the draft contains the exact wheel and sdist built from the release target
- both distributions have GitHub Actions build-provenance attestations
- the published GitHub Release is immutable
- its release attestation covers the downloaded assets
- the build-provenance signer and source commit match the draft workflow and
  release target

The draft builder has no PyPI identity. Only the protected publishing job has
OIDC permission for PyPI, and it publishes the immutable assets downloaded
from the reviewed GitHub Release.

## Dependency maintenance and compatibility

Dependabot opens grouped monthly updates for GitHub Actions and uv dependencies
after a seven-day cooldown. Its pull request titles use Conventional Commit
prefixes and pass the normal policy.

Normal CI tests the lockfile across every supported Python. A separate job
replaces only the public runtime dependencies with their declared lower bounds
and runs the relevant suites without allowing uv to restore the lock.

## Recovery

- Bad release pull request -> close it without merging, fix labels or merged
  changes, and run Prepare release again.
- Bad generated notes -> edit and curate them in the open release pull request.
- Failed candidate build before a tag or draft exists -> fix through a normal
  pull request. After it merges, open GitHub Actions -> Create draft release,
  select the default branch, and run the workflow manually. The recovery path
  releases that exact default-branch commit and refuses any other branch.
- Bad draft -> do not publish it. Delete the draft and associated tag, fix the
  problem through a pull request, and prepare again.
- Published release -> never replace its artifacts or tag. Fix the problem in
  a new version.

## Architecture assumptions

The release assumptions are intentionally explicit:

- static SemVer in `[project].version`
- a uv lockfile
- one canonical versioned Markdown history without a rolling pending section
- release headings supported as `X.Y.Z - DATE`, `[X.Y.Z] - DATE`,
  `X.Y.Z (DATE)`, or `vX.Y.Z (DATE)`
- release tags prefixed with `v`
- Conventional pull request titles
- GitHub-generated notes reviewed in a release pull request
- immutable GitHub Releases and PyPI Trusted Publishing

Keep project-specific build/test commands, smoke tests, runtime lower bounds,
Trusted Publisher identity, and environment configuration synchronized with
the workflows. Keep Action references and uv pinned to reviewed immutable
versions.
