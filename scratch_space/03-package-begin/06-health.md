# Phase 1c - Health Scoring

## Goal

Provide a pure function that takes repo config, persisted state, and live git status,
and returns a traffic-light health assessment (GREEN/YELLOW/RED) with human-readable reasons.

## File

`src/repomgr/health.py`

## Design

Health computation is a pure function with no side effects - no git calls, no file IO.
All inputs are provided by the caller. This makes it trivially testable.

## Models

### `HealthStatus` enum

```python
class HealthStatus(StrEnum):
    GREEN = "green"
    YELLOW = "yellow"
    RED = "red"
```

### `LiveRepoStatus`

Populated by cheap git calls at status-check time (done in `manager.py`):

```python
@dataclass
class LiveRepoStatus:
    repo_exists: bool
    branch: str = ""
    is_clean: bool = True
    is_behind: bool = False
    is_ahead: bool = False
    has_diverged: bool = False
```

### `HealthReport`

```python
@dataclass
class HealthReport:
    status: HealthStatus
    reasons: list[str]
```

## Public API

```python
def compute_health(
    config: RepoConfig,
    state: RepoState,
    live: LiveRepoStatus,
    deps_behind: list[str] | None = None,
) -> HealthReport:
    """Compute health status for a single repo.

    Args:
        config: Repo configuration from repos.toml.
        state: Persisted state from StateStore.
        live: Current git status gathered at check time.
        deps_behind: Names of tracked deps with newer tags available.

    Returns:
        HealthReport with overall status and list of reasons.
    """
```

## Scoring rules

| Condition | Status | Reason text |
|-----------|--------|-------------|
| Repo not on disk | RED | "repo not found on disk" |
| Diverged from remote | RED | "diverged from origin/main" |
| Not on main branch | YELLOW | "on branch {branch}, not main" |
| Dirty working tree | YELLOW | "uncommitted changes" |
| Behind remote (auto_merge=false) | YELLOW | "behind origin/main" |
| Ahead of remote | YELLOW | "ahead of origin/main (unpushed commits)" |
| Last test failed | YELLOW | "last test run failed" |
| Never fetched | YELLOW | "never fetched" |
| Deps behind latest (consumer) | YELLOW | "deps behind: {dep_names}" |
| All clear | GREEN | (empty reasons) |

### Evaluation order

1. Check RED conditions first (short-circuit if repo doesn't exist)
2. Collect all YELLOW conditions
3. Final status: RED if any RED; YELLOW if any YELLOW; else GREEN

## Tests

`tests/test_health.py`

All tests construct inputs directly - no git repos or files needed.

Test cases:
- `test_green_all_clear` - perfectly healthy repo
- `test_red_not_on_disk` - repo_exists=False
- `test_red_diverged` - has_diverged=True
- `test_yellow_not_on_main` - branch != "main"
- `test_yellow_dirty` - is_clean=False
- `test_yellow_behind` - is_behind=True, auto_merge=False
- `test_yellow_ahead` - is_ahead=True
- `test_yellow_test_failed` - last_test_passed=False
- `test_yellow_never_fetched` - last_fetch_at=None
- `test_yellow_deps_behind` - deps_behind=["llm-core"]
- `test_red_overrides_yellow` - diverged + dirty = RED
- `test_multiple_yellow_reasons` - collects all reasons

## Dependencies

- No external dependencies
- Imports only types from `config/repos_config.py` and `state.py`
