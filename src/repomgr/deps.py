"""Dependency graph, tag resolution, and pyproject.toml editing.

This module parses git-sourced dependencies from consumer repos' ``pyproject.toml``
files, resolves the latest available tag for each dependency from its local clone,
builds an adjacency-list dependency graph across all tracked repos, and edits
``pyproject.toml`` in place when an update is needed.

Pattern rules:
    Only ``repomgr.git`` is used for git operations.  No subprocess calls appear
    here directly.  ``tomllib`` reads pyproject files; ``re`` handles line-level
    parsing and replacement.  The ``update_pyproject`` function uses string
    replacement (not TOML round-trip) to preserve original formatting and comments.
"""

from collections import deque
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
import re
import tomllib

from loguru import logger as lg

from repomgr import git
from repomgr.config.repos_config import RepoConfig

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class CyclicDependencyError(Exception):
    """Raised when the dependency graph contains a cycle.

    Attributes:
        cycle_nodes: Names of repos involved in the cycle.
    """

    def __init__(self, cycle_nodes: list[str]) -> None:
        """Initialise with the set of nodes that form the cycle."""
        self.cycle_nodes = cycle_nodes
        super().__init__(f"cyclic dependency detected among: {cycle_nodes}")


class GitDepNotFoundError(Exception):
    """Raised when a dep's raw_line cannot be located in pyproject.toml."""

    def __init__(self, raw_line: str, pyproject_path: Path) -> None:
        """Initialise with the missing line and the file it was expected in."""
        super().__init__(f"dep line not found in {pyproject_path}:\n  {raw_line!r}")


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

# Regex to parse a git-sourced dependency line of the form:
#   <name>[<extras>] @ git+ssh://git@<host>/<owner>/<repo>.git@<tag>
# or
#   <name>[<extras>] @ git+https://<host>/<owner>/<repo>.git@<tag>
_GIT_DEP_PATTERN = re.compile(
    r"^(?P<name>[\w-]+)"
    r"(?P<extras>\[[\w,]+\])?"
    r"\s*@\s*git\+"
    r"(?:ssh://git@|https://)"
    r"[\w.-]+"  # host
    r"/[\w.-]+"  # owner
    r"/(?P<repo>[\w.-]+)"
    r"\.git@"
    r"(?P<tag>[\w.+-]+)"
    r"\s*$",
    re.ASCII,
)


@dataclass
class GitDep:
    """A git-sourced dependency found in a consumer repo's ``pyproject.toml``.

    Attributes:
        name: Package name (e.g. ``"llm-core"``).
        current_tag: Tag currently pinned (e.g. ``"v0.3.0"``).
        extras: Extras specifier including brackets (e.g. ``"[all]"``) or ``""``.
        raw_line: Original dependency string, used for in-place replacement.
        repo_name: Name of the tracked repo this dependency maps to.
        latest_tag: Newest tag available on the local clone.  Empty until resolved.
        needs_update: ``True`` when ``latest_tag`` differs from ``current_tag``.
    """

    name: str
    current_tag: str
    extras: str
    raw_line: str
    repo_name: str
    latest_tag: str = field(default="")
    needs_update: bool = field(default=False)


# ---------------------------------------------------------------------------
# Public API - parsing
# ---------------------------------------------------------------------------


def parse_git_deps(
    pyproject_path: Path,
    tracked: dict[str, RepoConfig],
) -> list[GitDep]:
    """Extract git-sourced deps from ``pyproject.toml`` that match tracked repos.

    Only dependencies that both look like git-sourced URLs and point to a repo
    whose slug appears in *tracked* are returned.  Plain PyPI deps and git deps
    for untracked repos are silently skipped.

    Args:
        pyproject_path: Path to a consumer repo's ``pyproject.toml``.
        tracked: Map of repo name to config, from ``RepomgrTomlConfig.repos_by_name``.

    Returns:
        List of ``GitDep`` for each tracked git dep found.
    """
    raw = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    dep_lines: list[str] = raw.get("project", {}).get("dependencies", [])

    result: list[GitDep] = []
    for line in dep_lines:
        m = _GIT_DEP_PATTERN.match(line.strip())
        if m is None:
            continue
        repo_slug = m.group("repo")
        # Strip a trailing ".git" embedded in the slug (should not happen but guard)
        repo_slug = repo_slug.removesuffix(".git")
        if repo_slug not in tracked:
            lg.debug("skipping untracked git dep repo '{}'", repo_slug)
            continue
        result.append(
            GitDep(
                name=m.group("name"),
                current_tag=m.group("tag"),
                extras=m.group("extras") or "",
                raw_line=line,
                repo_name=repo_slug,
            )
        )
    lg.debug("parsed {} tracked git deps from {}", len(result), pyproject_path)
    return result


# ---------------------------------------------------------------------------
# Public API - tag resolution
# ---------------------------------------------------------------------------


def resolve_latest_tags(
    deps: list[GitDep],
    configs: dict[str, RepoConfig],
) -> None:
    """Populate ``latest_tag`` and ``needs_update`` on each ``GitDep``.

    Reads tags from the local clone of each dependency's source repo via
    ``git.list_tags``.  Mutates *deps* in place.  Deps whose source repo has
    no tags are left with an empty ``latest_tag`` and ``needs_update=False``.

    Args:
        deps: List of ``GitDep`` instances to resolve.  Modified in place.
        configs: Map of repo name to ``RepoConfig`` (paths must be populated).
    """
    for dep in deps:
        config = configs[dep.repo_name]
        tags = git.list_tags(config.path)
        if not tags:
            lg.warning("no tags found in repo '{}' at {}", dep.repo_name, config.path)
            continue
        dep.latest_tag = tags[0]
        dep.needs_update = dep.latest_tag != dep.current_tag
        lg.debug(
            "dep '{}': current={}, latest={}, needs_update={}",
            dep.name,
            dep.current_tag,
            dep.latest_tag,
            dep.needs_update,
        )


# ---------------------------------------------------------------------------
# Public API - dependency graph
# ---------------------------------------------------------------------------


def build_dep_graph(
    configs: list[RepoConfig],
    tracked: dict[str, RepoConfig],
) -> dict[str, list[str]]:
    """Build ``{repo_name: [dep_repo_names]}`` for tracked deps.

    For each consumer repo on disk, parses its ``pyproject.toml`` and
    identifies which of its git-sourced dependencies are also tracked repos.
    Populates ``RepoConfig.deps`` as a side effect.

    Repos whose local clone does not exist or whose ``pyproject.toml`` is
    absent are included in the graph with an empty dep list.

    Args:
        configs: All tracked ``RepoConfig`` instances.
        tracked: Map of repo name to config for O(1) lookup.

    Returns:
        Adjacency list mapping each repo name to its list of tracked dep names.
    """
    graph: dict[str, list[str]] = {}
    for config in configs:
        pyproject = config.path / "pyproject.toml"
        if not config.path.exists() or not pyproject.exists():
            graph[config.name] = []
            continue
        deps = parse_git_deps(pyproject, tracked)
        dep_names = [d.repo_name for d in deps]
        config.deps = dep_names
        graph[config.name] = dep_names
        lg.debug("repo '{}' tracked deps: {}", config.name, dep_names)
    return graph


# ---------------------------------------------------------------------------
# Public API - topological sort
# ---------------------------------------------------------------------------


def topological_order(graph: dict[str, list[str]]) -> list[str]:
    """Return repo names in dependency order (sources first, consumers last).

    Uses Kahn's algorithm on the *reverse* adjacency: a node's in-degree is
    the number of dependencies it has.  Source repos (no deps) have in-degree
    zero and therefore appear first; deepest consumers appear last.

    Args:
        graph: Adjacency list ``{repo_name: [dep_names]}`` as returned by
            ``build_dep_graph``.

    Returns:
        Ordered list of repo names.

    Raises:
        CyclicDependencyError: If the graph contains a cycle.
    """
    # in_degree = number of dependencies each node has (= out-degree in original)
    in_degree: dict[str, int] = {node: len(deps) for node, deps in graph.items()}

    # Reverse edges: dep -> [consumers that depend on it]
    reverse: dict[str, list[str]] = {node: [] for node in graph}
    for node, deps in graph.items():
        for dep in deps:
            if dep in reverse:
                reverse[dep].append(node)

    queue: deque[str] = deque(
        sorted(node for node, deg in in_degree.items() if deg == 0)
    )
    order: list[str] = []

    while queue:
        node = queue.popleft()
        order.append(node)
        for consumer in sorted(reverse[node]):
            in_degree[consumer] -= 1
            if in_degree[consumer] == 0:
                queue.append(consumer)

    if len(order) != len(graph):
        cycle_nodes = sorted(node for node, deg in in_degree.items() if deg > 0)
        raise CyclicDependencyError(cycle_nodes)

    return order


# ---------------------------------------------------------------------------
# Public API - in-place editing
# ---------------------------------------------------------------------------


def update_pyproject(pyproject_path: Path, dep: GitDep) -> None:
    """Replace the git dep line in ``pyproject.toml`` with the updated tag.

    Uses string replacement on ``dep.raw_line`` to preserve TOML formatting,
    comments, and key ordering.  The only change made is substituting the
    pinned tag with ``dep.latest_tag``.

    Args:
        pyproject_path: Path to the ``pyproject.toml`` to update.
        dep: ``GitDep`` whose ``latest_tag`` should replace ``current_tag``.

    Raises:
        GitDepNotFoundError: If ``dep.raw_line`` is not found verbatim in the file.
    """
    content = pyproject_path.read_text(encoding="utf-8")
    if dep.raw_line not in content:
        raise GitDepNotFoundError(dep.raw_line, pyproject_path)

    new_line = dep.raw_line.replace(
        f"@{dep.current_tag}",
        f"@{dep.latest_tag}",
        1,
    )
    updated = content.replace(dep.raw_line, new_line, 1)
    pyproject_path.write_text(updated, encoding="utf-8")
    lg.info(
        "updated '{}' in {}: {} -> {}",
        dep.name,
        pyproject_path,
        dep.current_tag,
        dep.latest_tag,
    )
