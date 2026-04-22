# Template for Agent-Driven Merge Requests

## Description

[Describe the feature / fix logically and objectively]

## Agent Pre-Push Checks (Mandatory)

- [ ] I (C3PO/Agent) have successfully run the local `pre-push` hook (`.git/hooks/pre-push`).
- [ ] Pytest suite passes locally.
- [ ] Ruff format and Ruff check are completely clean.

## Release Plan

- Is this a `[patch]`, `[minor]`, or `[major]`? Specify in commit message if applicable, otherwise leave without prefix to avoid triggering a release.

## Additional Steps

[Any manual testing steps or configuration required]
