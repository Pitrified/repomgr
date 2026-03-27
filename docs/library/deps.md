# Dependency Graph

`deps.py` is responsible for three related tasks: parsing git-sourced
dependencies from consumer repos' `pyproject.toml` files, resolving the
latest available tag for each dependency from its local clone, and building
and querying the dependency graph across all tracked repos.

## Git dep format

A git-sourced dependency in `pyproject.toml` looks like this:

```toml
dependencies = [
    "llm-core[all] @ git+ssh://git@github.com/Pitrified/llm-core.git@v0.3.0",
    "fastapi-tools @ git+ssh://git@github.com/Pitrified/fastapi-tools.git@v0.1.2",
    "requests>=2.28",   # plain PyPI dep - ignored by deps.py
]
```

Both SSH (`git+ssh://git@...`) and HTTPS (`git+https://...`) URLs are
supported. The repo slug from the URL is matched against tracked repo names
from `repos.toml`. Package names and repo slugs may differ (e.g. `llm_core`
vs `llm-core`); the match is always performed on the URL slug.

## GitDep dataclass

`parse_git_deps()` returns a list of `GitDep` instances, one per tracked git
dep found:

```
GitDep
  name:         package name  (e.g. "llm-core")
  current_tag:  pinned tag    (e.g. "v0.3.0")
  extras:       extras spec   (e.g. "[all]" or "")
  raw_line:     original dep string, used for in-place replacement
  repo_name:    matched tracked repo name
  latest_tag:   newest tag available; empty until resolve_latest_tags() runs
  needs_update: True when latest_tag differs from current_tag
```

## Public API

### Parsing

`parse_git_deps(pyproject_path, tracked)` reads a single `pyproject.toml`
and returns only deps that match a tracked repo. Untracked git deps and
plain PyPI deps are silently skipped.

### Tag resolution

`resolve_latest_tags(deps, configs)` mutates each `GitDep` in place by
calling `git.list_tags()` on the local clone of each dependency's source
repo and recording the newest tag. Repos with no tags produce a warning and
leave `latest_tag` empty.

### Dependency graph

`build_dep_graph(configs, tracked)` iterates over all tracked repos, parses
each `pyproject.toml` present on disk, and returns an adjacency list:

```python
{
    "app":      ["mid"],
    "mid":      ["base"],
    "base":     [],
}
```

As a side effect it populates `RepoConfig.deps` for each repo. Repos not
yet on disk or lacking a `pyproject.toml` are included with an empty dep
list so they still appear in the graph.

### Topological ordering

`topological_order(graph)` runs Kahn's algorithm on the reverse adjacency
(a node's in-degree equals the number of dependencies it has, not the number
of consumers). Source repos - those with no dependencies - emerge first;
deepest consumers appear last. This ordering drives the update flow in
`update.py` so that a dependency is always updated before its consumers.

`CyclicDependencyError` is raised if the graph contains a cycle, with the
cycle node names listed in the exception.

### In-place editing

`update_pyproject(pyproject_path, dep)` replaces the pinned tag in a
`pyproject.toml` with `dep.latest_tag`. It uses plain string replacement on
`dep.raw_line` rather than a TOML round-trip, preserving original formatting,
comments, and key ordering. `GitDepNotFoundError` is raised if `dep.raw_line`
is not found verbatim in the file.
