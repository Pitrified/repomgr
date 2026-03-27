# Phase 3 - Dependency Graph

## Goal

Parse git-sourced dependencies from consumer repos' `pyproject.toml`, resolve latest tags,
build a dependency graph, provide topological ordering, and edit `pyproject.toml` in place.

## File

`src/repomgr/deps.py`

## Background

Repos can depend on other repos via git-sourced dependencies in `pyproject.toml`:

```toml
dependencies = [
    "llm-core[all] @ git+ssh://git@github.com/Pitrified/llm-core.git@v0.3.0",
    "fastapi-tools @ git+ssh://git@github.com/Pitrified/fastapi-tools.git@v0.1.2",
    "requests>=2.28",  # not a git dep, ignored
]
```

The `deps.py` module identifies which of these point to tracked repos (as defined in
`repos.toml`), resolves their latest available tags, and determines if updates are needed.

## Data model

```python
@dataclass
class GitDep:
    name: str             # package name (e.g., "llm-core")
    current_tag: str      # e.g., "v0.3.0"
    extras: str           # e.g., "[all]" or ""
    raw_line: str         # original dependency string for in-place replacement
    repo_name: str        # name of the tracked repo this maps to
    latest_tag: str = ""  # populated after resolution
    needs_update: bool = False  # latest_tag != current_tag
```

## Public API

### Parsing

```python
def parse_git_deps(
    pyproject_path: Path,
    tracked: dict[str, RepoConfig],
) -> list[GitDep]:
    """Extract git-sourced deps from pyproject.toml that match tracked repos.

    Args:
        pyproject_path: Path to a consumer repo's pyproject.toml.
        tracked: Map of repo name to config, from RepomgrTomlConfig.repos_by_name.

    Returns:
        List of GitDep for tracked git deps only. Non-git and untracked deps are skipped.
    """
```

### Tag resolution

```python
def resolve_latest_tags(
    deps: list[GitDep],
    configs: dict[str, RepoConfig],
) -> None:
    """Populate latest_tag and needs_update on each GitDep.

    Reads tags from the local clone of each dependency's source repo.
    Mutates deps in place.
    """
```

### Dependency graph

```python
def build_dep_graph(configs: list[RepoConfig]) -> dict[str, list[str]]:
    """Build {repo_name: [dep_names]} for tracked deps.

    Called once at startup. Populates RepoConfig.deps as a side effect.

    Returns:
        Adjacency list (repo -> its tracked dependencies).
    """
```

### Topological sort

```python
def topological_order(graph: dict[str, list[str]]) -> list[str]:
    """Return repo names in dependency order (sources first, deepest consumers last).

    Raises:
        CyclicDependencyError: If the graph contains a cycle.
    """
```

### In-place editing

```python
def update_pyproject(pyproject_path: Path, dep: GitDep) -> None:
    """Replace the git dep line in pyproject.toml with the updated tag.

    Uses string replacement on raw_line to preserve TOML formatting.
    """
```

## Parsing details

The git dep line format is:

```
<name>[<extras>] @ git+<protocol>://<host>/<owner>/<repo>.git@<tag>
```

Regex to extract components:

```python
GIT_DEP_PATTERN = re.compile(
    r'^(?P<name>[\w-]+)'
    r'(?P<extras>\[[\w,]+\])?'
    r'\s*@\s*git\+'
    r'(?:ssh://git@|https://)'
    r'[\w.-]+/'           # host
    r'[\w.-]+/'           # owner
    r'(?P<repo>[\w.-]+)'
    r'\.git@'
    r'(?P<tag>[\w.]+)'
    r'$'
)
```

Matching tracked repos: the `repo` capture group is compared against `tracked.keys()`.
Package name may differ from repo name (e.g., `llm_core` vs `llm-core`), so we match
on the repo slug from the URL, not the package name.

## Tag resolution details

For each `GitDep`:
1. Look up the source repo's local path via `configs[dep.repo_name].path`
2. Call `git.list_tags(path)` to get sorted tags (descending)
3. Take the first tag as `latest_tag`
4. Set `needs_update = (latest_tag != current_tag)`

## Topological sort details

Standard Kahn's algorithm. The graph is small (< 50 repos typically), so performance
is irrelevant. Raise `CyclicDependencyError` if the graph has a cycle.

## `update_pyproject` details

1. Read `pyproject.toml` as text
2. Find `dep.raw_line` in the text
3. Build `new_line` by replacing `@<current_tag>` with `@<latest_tag>` in `raw_line`
4. Replace and write back

String replacement (not TOML parser + serializer) preserves original formatting,
comments, and ordering.

## Tests

`tests/test_deps.py`

Fixtures:
- `sample_pyproject(tmp_path)` - write a pyproject.toml with known git deps
- `tracked_configs()` - dict of RepoConfig for test repos

Test cases:
- `test_parse_git_deps_basic` - extracts name, tag, extras, raw_line
- `test_parse_git_deps_no_extras` - handles deps without extras
- `test_parse_git_deps_untracked_ignored` - non-tracked git deps skipped
- `test_parse_git_deps_non_git_ignored` - regular PyPI deps skipped
- `test_resolve_latest_tags` - populates latest_tag and needs_update
- `test_resolve_no_update_needed` - needs_update is False when tags match
- `test_build_dep_graph` - correct adjacency list
- `test_topological_order` - sources before consumers
- `test_topological_order_cycle` - raises CyclicDependencyError
- `test_update_pyproject` - in-place replacement preserves formatting
- `test_update_pyproject_with_extras` - handles extras in dep line

## Dependencies

- `re` (stdlib)
- `tomllib` (stdlib)
- `repomgr.git` (for `list_tags`)
- `repomgr.config.repos_config` (for `RepoConfig`)
