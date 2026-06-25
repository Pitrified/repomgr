---
status: draft
---

# Phase 2 - Sweep `remote` consumers + fixtures

## Overview

After the schema lands (phase 1), make the rest of the codebase and test suite
green. Runtime impact is expected to be near-zero because `repo.remote` is now a
computed property, but the test fixtures that construct `RepoConfig(remote=...)`
or write `remote =` in TOML must be migrated.

Context: [`00-start.md`](00-start.md) (hidden problem 1), depends on
[`01_schema.md`](01_schema.md).

## Goals (draft)

1. Confirm `manager.py:112` (`git.clone(repo.remote, ...)`) needs no change.
2. Migrate the direct-construction / fixture references found in
   `tests/test_health.py:22`, `tests/test_cli.py:36`, `tests/test_update.py:44`,
   `tests/test_manager.py:45,225`, `tests/test_deps.py:45`.
3. Full `uv run pytest` green.

## Done when (draft)

- No `remote=`/`remote =` references remain outside the derived-URL tests.
- `uv run pytest` (whole suite) passes; ruff/pre-commit clean.

Detail this phase fully before starting it.
