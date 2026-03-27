# Manager

`manager.py` is the orchestration layer that wires together `git`, `state`,
`health`, `deps`, and `renderer` to implement the four main CLI workflows.
It is intentionally thin: all git work delegates to `git.py`, display
delegates to `renderer.py`, and scoring delegates to `health.py`.

## Workflows

### fetch_all

`fetch_all(config, store)` iterates every tracked repo, runs `git fetch`,
updates persisted `RepoState`, optionally fast-forwards `main`, and renders
the result for each repo. State is written to disk via `store.save()` after
each successful fetch.

Auto-merge conditions (all must hold):

- `RepoConfig.auto_merge` is `True`
- Current branch is `main`
- Working tree is clean
- Local and remote have not diverged

If any condition fails the fetch still succeeds; only the fast-forward step
is skipped. A `GitError` on one repo is logged as a warning and processing
continues with the next repo.

### clone_missing

`clone_missing(config)` checks every tracked repo and calls `git.clone()`
for any that are not yet on disk. Existing repos are silently skipped.
Clone failures are rendered to stdout and do not abort subsequent repos.

### status_all

`status_all(config, store, dep_graph)` builds a status dashboard. For each
tracked repo it:

1. Calls cheap git inspection functions (`current_branch`, `is_clean`, etc.)
   to assemble a `LiveRepoStatus`.
2. Resolves which tracked deps have newer tags available (consumer repos only)
   by delegating to `deps.parse_git_deps()` and `deps.resolve_latest_tags()`.
3. Computes a `HealthReport` via `health.compute_health()`.
4. Assembles a `StatusRow` and passes all rows to `renderer.render_status()`.

This function is **read-only** - it never writes to the state store.
A `GitError` on any single repo causes that repo to be omitted from the
dashboard; other repos are still shown.

The `dep_graph` parameter is accepted for callers that pre-compute the graph
at startup but is not currently used internally.

### stale_branches

`stale_branches(config)` lists stale branches for each on-disk repo via
`git.list_stale_branches()`, renders the list, and interactively prompts
the user (via `typer.confirm`) whether to delete each branch.

## Error handling pattern

All four functions follow the same pattern: errors from `git.py` are caught
per repo, logged as warnings, and processing continues with the next repo.

```python
for repo in config.repos:
    try:
        # ... operation ...
    except GitError as e:
        lg.warning("skipping {}: {}", repo.name, e)
        continue
```

## Private helpers

`_gather_deps_behind(repo, config)` is an internal helper used by
`status_all` for consumer repos. It parses the repo's `pyproject.toml`,
resolves the latest tags for each tracked git dep, and returns the names of
deps that have a newer tag available. Returns an empty list if
`pyproject.toml` is absent or a parse/resolution error occurs.
