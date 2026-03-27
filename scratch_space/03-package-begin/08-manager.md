# Phase 5a - Manager (Fetch, Clone, Status, Stale Branches)

## Goal

Orchestrate the main operations: fetch all repos, clone missing repos, display status
dashboard, and manage stale branches. Uses `git.py`, `state.py`, `health.py`, `deps.py`,
and `renderer.py`.

## File

`src/repomgr/manager.py`

## Public API

### `fetch_all`

```python
def fetch_all(
    config: RepomgrTomlConfig,
    store: StateStore,
) -> None:
    """Fetch all repos, auto-merge where configured, display results."""
```

Flow per repo:
1. If not on disk - skip with warning via renderer
2. `git.fetch(path)` - get `FetchResult`
3. Update `RepoState`: `last_fetch_at`, `last_seen_main_sha`, `new_tags_since_last_fetch`
4. If `auto_merge=True` AND on main AND clean AND not diverged:
   - `git.fast_forward(path)`
5. `renderer.render_fetch_result(name, result)`
6. `store.save(state)`

Error handling: catch `GitError` per repo, log and continue to next repo.

### `clone_missing`

```python
def clone_missing(config: RepomgrTomlConfig) -> None:
    """Clone repos that are not on disk."""
```

Flow per repo:
1. If `path.exists()` - skip
2. `git.clone(remote, path)`
3. `renderer.render_clone_result(name, success)`

### `status_all`

```python
def status_all(
    config: RepomgrTomlConfig,
    store: StateStore,
    dep_graph: dict[str, list[str]],
) -> None:
    """Display health dashboard for all repos. Read-only - does not write state."""
```

Flow per repo:
1. Gather `LiveRepoStatus`:
   - If not on disk: `LiveRepoStatus(repo_exists=False)`
   - Otherwise: call `git.current_branch()`, `git.is_clean()`, etc.
2. Resolve `deps_behind` via `deps.py` (for consumer repos)
3. `health.compute_health(config, state, live, deps_behind)` - get `HealthReport`
4. Assemble `StatusRow`
5. Pass all rows to `renderer.render_status(rows)`

### `stale_branches`

```python
def stale_branches(config: RepomgrTomlConfig) -> None:
    """List stale branches across all repos, prompt for deletion."""
```

Flow per repo:
1. If not on disk - skip
2. `git.list_stale_branches(path)` - get list
3. If empty - skip
4. `renderer.render_stale_branches(name, branches)`
5. For each branch: prompt user (via `typer.confirm()` or `rich.prompt`)
6. If confirmed: `git.delete_branch(path, branch)`

Interactive prompting is acceptable here since this is a human-facing CLI operation.

## Error handling pattern

All repo operations wrap in try/except per repo:

```python
for repo in config.repos:
    try:
        # ... operation ...
    except GitError as e:
        lg.warning(f"Skipping {repo.name}: {e}")
        continue
```

This ensures one failing repo doesn't abort the entire batch.

## Tests

`tests/test_manager.py`

Tests mock `git.py` functions to avoid real git operations.

Fixtures:
- `sample_config()` - RepomgrTomlConfig with 2-3 repos
- `sample_store(tmp_path)` - StateStore with tmp file
- `mock_git` - patches all git functions

Test cases:
- `test_fetch_all_updates_state` - state written after fetch
- `test_fetch_all_auto_merge` - fast_forward called when conditions met
- `test_fetch_all_skip_auto_merge_dirty` - no fast_forward when dirty
- `test_fetch_all_skip_missing_repo` - skips with warning
- `test_clone_missing_clones` - clone called for missing repos
- `test_clone_missing_skips_existing` - no clone for existing
- `test_status_all_assembles_rows` - renderer receives correct StatusRows
- `test_status_all_read_only` - state file not modified
- `test_stale_branches_deletion` - delete called after confirmation

## Dependencies

- `repomgr.git`
- `repomgr.state`
- `repomgr.health`
- `repomgr.deps`
- `repomgr.renderer`
- `repomgr.config.repos_config`
- `loguru`
