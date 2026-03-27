# Update

`update.py` implements the dependency update flow for consumer repos. It
detects outdated git-sourced dependencies, creates a timestamped branch,
rewrites pinned tags in `pyproject.toml`, runs the test suite, and either
merges the result to `main` or leaves the branch for manual review.

This module absorbs and supersedes the standalone `update_git_deps.py` script.

## Public API

The single entry point is `update_deps(config, store, dep_graph, ...)`:

```python
from repomgr.update import update_deps

update_deps(
    config,       # RepomgrTomlConfig
    store,        # StateStore
    dep_graph,    # built by deps.build_dep_graph()
    dry_run=False,
    no_tests=False,
    repo_name=None,  # restrict to one repo by name
)
```

## Flow per consumer repo

Repos are processed in topological order (sources first, deepest consumers
last) so that upstream pinned tags are always resolved before the repos that
depend on them.

For each consumer repo the sequence is:

**Pre-checks** - Any failure produces a `"skipped"` outcome:

1. Local clone exists on disk.
2. `pyproject.toml` is present.
3. Currently on `main` branch.
4. Working tree is clean.
5. Local `main` is not behind remote (a `GitError` here is treated as
   "unknown, proceed").

**Detection** - If all pre-checks pass:

6. Parse git deps from `pyproject.toml` via `deps.parse_git_deps`.
7. Resolve the latest available tag for each dep via `deps.resolve_latest_tags`.
8. Filter to deps where `needs_update=True`. If none, record `"no_updates"` and skip.

**Dry run** - If `dry_run=True`:

9. Log intended changes and return `"updated"` without writing anything.

**Execution** - Otherwise:

10. Create branch `deps/update_<YYYYMMDD_HHMMSS>`.
11. Edit `pyproject.toml` in place for each outdated dep.
12. Run `uv sync` to regenerate `uv.lock`.
13. Run `repo.test_cmd` (shell command, e.g. `"uv run pytest"`), unless
    `no_tests=True`.
14. Commit `pyproject.toml` and `uv.lock` together.

**Merge or leave**:

15. If tests passed (or `no_tests`): checkout `main`, fast-forward merge,
    delete the update branch, push.
16. If tests fail: leave the branch checked out for manual review. Outcome
    is `"failed_tests"`.

**State** - Written after every repo regardless of outcome:

- `last_update_run_at` - timestamp
- `last_update_result` - one of `"updated"`, `"failed_tests"`, `"no_updates"`, `"skipped"`
- `last_test_run_at` / `last_test_passed` - populated when tests ran

## CLI flags

| Flag | Effect |
|------|--------|
| `--dry-run` | Log what would change; no writes |
| `--no-tests` | Skip test suite, merge unconditionally |
| `--repo NAME` | Process only the named repo |

Passing an unknown `--repo` value raises `UnknownRepoError`.

## Security note

The test command (`repo.test_cmd`) is executed with `shell=True` because it
is a freeform string such as `"uv run pytest -x"`. This is safe because
`repos.toml` is a trusted, operator-controlled local file.

## Module structure

| Symbol | Role |
|--------|------|
| `update_deps()` | Public entry point |
| `UnknownRepoError` | Raised for unknown `repo_name` argument |
| `_update_repo()` | Orchestrates one repo's flow |
| `_check_preconditions()` | Validates repo state before acting |
| `_find_outdated_deps()` | Parse and resolve; returns outdated-only list |
| `_execute_update()` | Branch, edit, test, merge-or-leave |
| `_record_state()` | Persist outcome to `StateStore` |
| `_run_uv_sync()` | Subprocess wrapper for `uv sync` |
| `_run_tests()` | Subprocess wrapper for the test command |
| `_commit_changes()` | Stage and commit pyproject + lockfile |
