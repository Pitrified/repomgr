# Phase 5b - Update Flow

## Goal

Automate the dependency update workflow: for each consumer repo, detect outdated git deps,
create an update branch, edit `pyproject.toml`, run tests, and merge or leave the branch.

This absorbs and refactors the standalone `update_git_deps.py` script.

## File

`src/repomgr/update.py`

## Public API

```python
def update_deps(
    config: RepomgrTomlConfig,
    store: StateStore,
    dep_graph: dict[str, list[str]],
    *,
    dry_run: bool = False,
    no_tests: bool = False,
    repo_name: str | None = None,
) -> None:
    """Run dependency update flow across consumer repos.

    Args:
        config: Loaded repos.toml config.
        store: State persistence.
        dep_graph: Dependency graph from deps.py.
        dry_run: Print what would change without writing.
        no_tests: Skip test suite, merge unconditionally.
        repo_name: If given, only update this specific repo.
    """
```

## Flow per consumer repo

### Pre-checks

1. Must be on main branch (else skip with warning)
2. Must have clean working tree (else skip)
3. Must not be behind remote (else skip with warning to fetch first)

### Detection

4. `deps.parse_git_deps(pyproject_path, tracked)` - get git deps
5. `deps.resolve_latest_tags(deps, configs)` - populate latest tags
6. Filter to `deps` where `needs_update=True`
7. If nothing needs updating - record `"no_updates"` in state, skip

### Dry run branch

8. If `dry_run`: print what would change via renderer, return

### Execution

9. Create branch `deps/update_<YYYYMMDD_HHMMSS>`
10. For each outdated dep:
    - `deps.update_pyproject(pyproject_path, dep)` - edit in place
11. Run `uv sync` (or equivalent) to update the lockfile
12. Run test command (`config.test_cmd`):
    - If `no_tests`: skip directly to commit+merge
    - **Pass**: proceed to merge
    - **Fail**: commit WIP state to branch, leave branch checked out, continue to next repo

### Merge (on test pass or no_tests)

13. `git.commit(cwd, "deps: update {dep_names}", [pyproject_path, lockfile])`
14. `git.checkout(cwd, "main")`
15. `git.merge_ff_only(cwd, branch_name)`
16. `git.delete_branch(cwd, branch_name)`
17. `git.push(cwd, "main")`

### State update

18. Update `RepoState`:
    - `last_update_run_at` = now
    - `last_update_result` = `"ok"` | `"failed_tests"` | `"no_updates"` | `"skipped"`
    - `last_test_run_at` = now (if tests ran)
    - `last_test_passed` = True/False (if tests ran)
19. `store.save(state)`

### Reporting

20. Collect `UpdateResult` per repo
21. `renderer.render_update_summary(results)` after all repos processed

## Ordering

Repos are processed in `topological_order(dep_graph)` so that source repos are updated
first. If repo A depends on repo B which depends on repo C, the order is C, B, A.
This ensures that when B is updated, C already has its latest tag available.

## Test command execution

The test command is run via `subprocess.run(cmd, shell=True, cwd=path)`:
- `shell=True` because the command is a user-provided string like `"uv run pytest"`
- Capture stdout/stderr for logging
- Return code 0 = pass, non-zero = fail

Security note: `test_cmd` comes from `repos.toml` which is a trusted, local config file.

## Edge cases

- **Lock file**: after editing `pyproject.toml`, run `uv sync` to regenerate `uv.lock`.
  The lock file path is `path / "uv.lock"`. Include it in the commit.
- **Multiple deps in one repo**: all updated in one branch, one commit
- **Partial failure**: if one dep's update fails, the whole repo is left on the branch
- **No pyproject.toml**: skip the repo with a warning

## CLI flags

| Flag | Effect |
|------|--------|
| `--dry-run` | Print what would change, no writes |
| `--no-tests` | Skip test suite, merge unconditionally |
| `--repo NAME` | Run only for the named consumer repo |

## Tests

`tests/test_update.py`

Tests mock `git.py` and `deps.py` to avoid real operations.

Fixtures:
- `consumer_config()` - RepomgrTomlConfig with consumer repos
- `mock_deps` - patches parse_git_deps, resolve_latest_tags, etc.
- `mock_git` - patches git operations

Test cases:
- `test_update_deps_full_flow` - happy path: detect, branch, edit, test, merge
- `test_update_deps_dry_run` - no writes, only prints
- `test_update_deps_no_tests` - merge without testing
- `test_update_deps_test_failure` - leaves on branch, state records failure
- `test_update_deps_no_updates` - skips when deps are current
- `test_update_deps_skip_dirty` - skip repo with dirty tree
- `test_update_deps_skip_not_main` - skip repo not on main
- `test_update_deps_single_repo` - --repo flag filters
- `test_update_deps_topological_order` - processes in correct order
- `test_update_deps_state_updated` - state reflects outcome

## Dependencies

- `subprocess` (stdlib, for test command)
- `repomgr.git`
- `repomgr.state`
- `repomgr.deps`
- `repomgr.renderer`
- `repomgr.config.repos_config`
- `loguru`
