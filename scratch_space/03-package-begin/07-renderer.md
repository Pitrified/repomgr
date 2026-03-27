# Phase 4 - Rich Terminal Renderer

## Goal

Provide all terminal output formatting in a single module. This is the **only** module
that imports `rich`. It takes data structures and formats them - no git calls, no file IO.

## File

`src/repomgr/renderer.py`

## Design principle

`renderer.py` is a pure display layer. Swapping to a web dashboard later means replacing
this one file. All functions receive pre-computed data and return nothing (they print).

## Models (input types)

### `StatusRow`

Flat dataclass assembling everything needed for one dashboard row:

```python
@dataclass
class StatusRow:
    name: str
    health: HealthReport
    live: LiveRepoStatus
    state: RepoState
    deps_behind: list[str]
```

### `UpdateResult`

Summary of one repo's update outcome:

```python
@dataclass
class UpdateResult:
    name: str
    outcome: str          # "updated" | "failed_tests" | "no_updates" | "skipped"
    updated_deps: list[str]
    error: str | None = None
```

## Public API

```python
def render_status(rows: list[StatusRow]) -> None:
    """Print the status dashboard table."""

def render_fetch_result(name: str, result: FetchResult) -> None:
    """Print fetch results for a single repo."""

def render_update_summary(results: list[UpdateResult]) -> None:
    """Print summary table of update-deps results."""

def render_dep_graph(graph: dict[str, list[str]]) -> None:
    """Print the dependency tree."""

def render_stale_branches(repo_name: str, branches: list[str]) -> None:
    """Print stale branches for a repo."""

def render_clone_result(name: str, success: bool, error: str | None = None) -> None:
    """Print clone result for a single repo."""
```

## Status dashboard layout

```
 Repo            Health   Branch   Clean   Behind   Ahead   Last Fetch            Deps Behind
 llm-core        GREEN    main     yes     no       no      2026-03-27 09:14      -
 fastapi-tools   GREEN    main     yes     no       no      2026-03-27 09:14      -
 recipamatic     YELLOW   feat/x   yes     yes      no      2026-03-26 15:00      llm-core
 some-exception  RED      main     no      no       yes     never                 -
```

Use Rich `Table` with color-coded health status:
- GREEN: `[green]GREEN[/green]`
- YELLOW: `[yellow]YELLOW[/yellow]`
- RED: `[red]RED[/red]`

When health is not GREEN, print reasons below the table row (or as a footnote).

## Fetch result layout

```
[bold]llm-core[/bold] - fetched
  New tags: v0.4.0, v0.4.1
  Main advanced by 3 commits:
    abc1234 feat: add new parser
    def5678 fix: handle edge case
    ghi9012 chore: update deps
```

## Dep graph layout

Use Rich `Tree`:

```
Dependency Graph
  llm-core (source)
  fastapi-tools (source)
  recipamatic (consumer)
    <- llm-core
    <- fastapi-tools
  some-exception (consumer)
    <- llm-core
```

## Tests

`tests/test_renderer.py`

Renderer tests are lightweight - mainly verify no crashes with various inputs.
Use `rich.console.Console(file=StringIO())` to capture output.

Test cases:
- `test_render_status_all_green` - no crash, output contains repo names
- `test_render_status_mixed` - handles GREEN + YELLOW + RED
- `test_render_fetch_result_with_tags` - output contains tag names
- `test_render_fetch_result_no_changes` - handles empty fetch
- `test_render_dep_graph` - output contains tree structure
- `test_render_stale_branches_empty` - handles no stale branches
- `test_render_update_summary` - output contains outcomes

## Dependencies

- `rich` (already a dependency)
- Types from `health.py`, `state.py`, `git.py` (FetchResult)
