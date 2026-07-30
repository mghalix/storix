<!--
Write for a reader with no context beyond this repository. Keep the body
self-contained, neutral, and repository-facing. Delete every section that has
nothing to say, and delete these comments as you go.
-->

## Summary

<!-- One or two sentences: what changed, and the effect on users. -->

## Motivation

<!-- The problem, bug, or limitation this addresses. Link the issue or ADR. -->

## Changes

<!-- The notable changes, not a file-by-file restatement of the diff. -->

## Design decisions

<!-- Optional. Delete this section unless a decision needs recording: a
tradeoff, a constraint, a rejected alternative, or behavior a reviewer would
otherwise question. State decisions neutrally, as project decisions. -->

## Testing

<!-- What covers the change, and anything verified by hand. -->

## Breaking changes

<!-- Optional. Delete this section when the change is backward compatible.
Otherwise: what breaks, and how to migrate. -->

## Checklist

<!-- Applying labels needs write access on this repository; leave those boxes
unchecked otherwise and name the intended labels in the summary. -->

- [ ] The title follows Conventional Commits with a `core`, `cli`, or `repo`
      scope; it becomes the default-branch commit and the release-note entry.
- [ ] The matching area label is applied: `core`, `cli`, or `repo`.
- [ ] Core and CLI behavioral changes are split into separate pull requests, so
      this one carries at most one of the `core` and `cli` labels.
- [ ] A release-note label is applied (`breaking-change`, `feature`, `fix`, or
      `documentation`), or `skip-changelog` for a change that needs no note.
- [ ] Tests cover the changed behavior.
- [ ] Documentation and examples reflect public changes.
- [ ] The body is self-contained and repository-facing.
- [ ] `just check` passes after a locked sync.
