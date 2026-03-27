# Phase 2 - Git Subprocess Layer

## Goal

Provide a pure subprocess layer for all git operations. Every function takes `cwd: Path`
as its first argument. No business logic, no config objects, no state.

## File

`src/repomgr/git.py`

## Design principles

- **Pure functions**: each function runs one or a small sequence of git commands
- **No internal imports**: `git.py` does not import from other repomgr modules
- **Explicit errors**: define `GitError` for subprocess failures with command + stderr
- **No shell=True**: all commands via `subprocess.run(list)` for safety

## Data models (in this module)

```python
@dataclass
class FetchResult:
    new_tags: list[str]
    new_branches: list[str]
    main_advanced_by: int          # number of new commits on origin/main
    new_commit_log: list[str]      # short log lines of those commits
```

```python
class GitError(Exception):
    """Raised when a git subprocess fails."""
    def __init__(self, command: list[str], stderr: str, returncode: int) -> None: ...
```

## Functions

### Repository inspection

```python
def current_branch(cwd: Path) -> str: ...
def is_clean(cwd: Path) -> bool: ...
def is_behind_remote(cwd: Path, branch: str = "main") -> bool: ...
def is_ahead_of_remote(cwd: Path, branch: str = "main") -> bool: ...
def has_diverged(cwd: Path, branch: str = "main") -> bool: ...
def get_main_sha(cwd: Path) -> str: ...
def repo_exists(cwd: Path) -> bool: ...
```

### Fetch and merge

```python
def fetch(cwd: Path) -> FetchResult: ...
def fast_forward(cwd: Path, branch: str = "main") -> None: ...
def merge_ff_only(cwd: Path, ref: str) -> None: ...
```

### Clone

```python
def clone(remote: str, dest: Path) -> None: ...
```

### Tags

```python
def list_tags(cwd: Path) -> list[str]: ...  # sorted by version descending
```

### Branches

```python
def list_stale_branches(cwd: Path) -> list[str]: ...
def create_branch(cwd: Path, name: str) -> None: ...
def checkout(cwd: Path, ref: str) -> None: ...
def delete_branch(cwd: Path, branch: str) -> None: ...
def delete_remote_branch(cwd: Path, branch: str) -> None: ...
```

### Commit and push

```python
def commit(cwd: Path, message: str, paths: list[Path]) -> None: ...
def push(cwd: Path, branch: str) -> None: ...
```

## Implementation notes

### `fetch()` implementation

`fetch()` needs to compute a diff before/after:

1. Record pre-fetch state: tags, branches, main SHA
2. Run `git fetch --tags --prune`
3. Record post-fetch state
4. Diff to build `FetchResult`
5. Get commit log for new main commits via `git log --oneline <old_sha>..<new_sha>`

### `list_tags()` sorting

Use `git tag --sort=-v:refname` for natural version sorting (descending).
Fall back to Python-side `packaging.version` sorting if git version is too old.

### `list_stale_branches()` logic

A branch is "stale" if:
- It has been merged into main: `git branch --merged main` (exclude main itself)
- Its remote tracking branch is gone: `git branch -vv` and grep for `: gone]`

### Subprocess helper

Private `_run_git(cwd, *args) -> subprocess.CompletedProcess`:
- Runs `["git", *args]` with `cwd=cwd`, `capture_output=True`, `text=True`
- Raises `GitError` on non-zero return code
- Logs command via loguru at debug level

## Tests

`tests/test_git.py`

Testing strategy: create temporary git repos with known state.

Fixtures:
- `git_repo(tmp_path)` - init a repo with an initial commit on main
- `git_repo_with_remote(tmp_path)` - bare remote + local clone

Test cases:
- `test_current_branch` - returns "main" on fresh repo
- `test_is_clean_dirty` - clean vs uncommitted changes
- `test_clone` - clone from a bare remote
- `test_fetch_no_changes` - FetchResult with all zeros
- `test_fetch_with_new_commits` - main_advanced_by > 0
- `test_fetch_with_new_tags` - new_tags populated
- `test_list_tags_sorted` - version order descending
- `test_create_and_checkout_branch` - branch operations
- `test_fast_forward` - merge new commits on main
- `test_list_stale_branches` - detects merged branches
- `test_commit_and_push` - commit + push to remote
- `test_git_error` - non-zero exit raises GitError

## Dependencies

- `subprocess` (stdlib)
- `loguru` (already a dependency)
- No other repomgr imports
