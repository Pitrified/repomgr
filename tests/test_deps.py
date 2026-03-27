"""Tests for the deps module."""

from pathlib import Path
import subprocess

import pytest

from repomgr.config.repos_config import RepoConfig
from repomgr.config.repos_config import Role
from repomgr.deps import CyclicDependencyError
from repomgr.deps import GitDep
from repomgr.deps import GitDepNotFoundError
from repomgr.deps import build_dep_graph
from repomgr.deps import parse_git_deps
from repomgr.deps import resolve_latest_tags
from repomgr.deps import topological_order
from repomgr.deps import update_pyproject

# ---------------------------------------------------------------------------
# Helpers & shared data
# ---------------------------------------------------------------------------

_SSH_DEP = "llm-core[all] @ git+ssh://git@github.com/Pitrified/llm-core.git@v0.3.0"
_SSH_DEP_NO_EXTRAS = (
    "fastapi-tools @ git+ssh://git@github.com/Pitrified/fastapi-tools.git@v0.1.2"
)
_HTTPS_DEP = "mylib @ git+https://github.com/Pitrified/mylib.git@v1.0.0"
_PYPI_DEP = "requests>=2.28"
_GIT_UNTRACKED = "other-lib @ git+ssh://git@github.com/Other/other-lib.git@v0.5.0"


def _make_pyproject(tmp_path: Path, deps: list[str]) -> Path:
    """Write a minimal pyproject.toml with the given dependency lines."""
    lines = ["[project]", 'name = "consumer"', 'version = "0.1.0"', "dependencies = ["]
    lines.extend(f'    "{dep}",' for dep in deps)
    lines.append("]")
    p = tmp_path / "pyproject.toml"
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def _make_config(name: str, path: Path | None = None) -> RepoConfig:
    return RepoConfig(
        name=name,
        remote=f"git@github.com:Pitrified/{name}.git",
        roles=[Role.SOURCE],
        test_cmd="uv run pytest",
        path=path or Path(f"/srv/repos/{name}"),
    )


def _tracked(*names: str) -> dict[str, RepoConfig]:
    return {n: _make_config(n) for n in names}


# ---------------------------------------------------------------------------
# Helpers for git repos
# ---------------------------------------------------------------------------


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(  # noqa: S603
        ["git", *args],  # noqa: S607
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


@pytest.fixture
def git_repo_with_tags(tmp_path: Path) -> Path:
    """Create a local git repo with two version tags. Returns repo path."""
    repo = tmp_path / "llm-core"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "test@test.com")
    _git(repo, "config", "user.name", "Test")
    (repo / "README.md").write_text("hello", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "init")
    _git(repo, "tag", "v0.3.0")
    (repo / "README.md").write_text("hello v2", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "v2")
    _git(repo, "tag", "v0.4.0")
    return repo


# ---------------------------------------------------------------------------
# parse_git_deps
# ---------------------------------------------------------------------------


def test_parse_git_deps_basic(tmp_path: Path) -> None:
    """Extracts name, tag, extras, and raw_line from a bracketed ssh dep."""
    pyproject = _make_pyproject(tmp_path, [_SSH_DEP])
    tracked = _tracked("llm-core")
    deps = parse_git_deps(pyproject, tracked)
    assert len(deps) == 1
    d = deps[0]
    assert d.name == "llm-core"
    assert d.current_tag == "v0.3.0"
    assert d.extras == "[all]"
    assert d.raw_line == _SSH_DEP
    assert d.repo_name == "llm-core"
    assert d.latest_tag == ""
    assert d.needs_update is False


def test_parse_git_deps_no_extras(tmp_path: Path) -> None:
    """Handles deps without extras specifier."""
    pyproject = _make_pyproject(tmp_path, [_SSH_DEP_NO_EXTRAS])
    tracked = _tracked("fastapi-tools")
    deps = parse_git_deps(pyproject, tracked)
    assert len(deps) == 1
    assert deps[0].extras == ""
    assert deps[0].name == "fastapi-tools"
    assert deps[0].current_tag == "v0.1.2"


def test_parse_git_deps_https(tmp_path: Path) -> None:
    """Handles https-based git dep URLs."""
    pyproject = _make_pyproject(tmp_path, [_HTTPS_DEP])
    tracked = _tracked("mylib")
    deps = parse_git_deps(pyproject, tracked)
    assert len(deps) == 1
    assert deps[0].current_tag == "v1.0.0"
    assert deps[0].repo_name == "mylib"


def test_parse_git_deps_untracked_ignored(tmp_path: Path) -> None:
    """Git deps for untracked repos are silently skipped."""
    pyproject = _make_pyproject(tmp_path, [_SSH_DEP, _GIT_UNTRACKED])
    tracked = _tracked("llm-core")
    deps = parse_git_deps(pyproject, tracked)
    assert len(deps) == 1
    assert deps[0].repo_name == "llm-core"


def test_parse_git_deps_non_git_ignored(tmp_path: Path) -> None:
    """Regular PyPI deps are skipped."""
    pyproject = _make_pyproject(tmp_path, [_PYPI_DEP, _SSH_DEP])
    tracked = _tracked("llm-core")
    deps = parse_git_deps(pyproject, tracked)
    assert len(deps) == 1
    assert deps[0].name == "llm-core"


def test_parse_git_deps_empty(tmp_path: Path) -> None:
    """Returns empty list when there are no dependencies."""
    pyproject = _make_pyproject(tmp_path, [])
    deps = parse_git_deps(pyproject, _tracked("llm-core"))
    assert deps == []


def test_parse_git_deps_multiple(tmp_path: Path) -> None:
    """Returns all matching deps when multiple tracked deps are present."""
    pyproject = _make_pyproject(tmp_path, [_SSH_DEP, _SSH_DEP_NO_EXTRAS])
    tracked = _tracked("llm-core", "fastapi-tools")
    deps = parse_git_deps(pyproject, tracked)
    assert len(deps) == 2
    names = {d.repo_name for d in deps}
    assert names == {"llm-core", "fastapi-tools"}


# ---------------------------------------------------------------------------
# resolve_latest_tags
# ---------------------------------------------------------------------------


def test_resolve_latest_tags(tmp_path: Path, git_repo_with_tags: Path) -> None:
    """Populates latest_tag and sets needs_update=True when tags differ."""
    dep = GitDep(
        name="llm-core",
        current_tag="v0.3.0",
        extras="[all]",
        raw_line=_SSH_DEP,
        repo_name="llm-core",
    )
    config = _make_config("llm-core", path=git_repo_with_tags)
    resolve_latest_tags([dep], {"llm-core": config})
    assert dep.latest_tag == "v0.4.0"
    assert dep.needs_update is True


def test_resolve_no_update_needed(tmp_path: Path, git_repo_with_tags: Path) -> None:
    """needs_update is False when the current tag matches the latest."""
    dep = GitDep(
        name="llm-core",
        current_tag="v0.4.0",
        extras="[all]",
        raw_line=_SSH_DEP,
        repo_name="llm-core",
    )
    config = _make_config("llm-core", path=git_repo_with_tags)
    resolve_latest_tags([dep], {"llm-core": config})
    assert dep.latest_tag == "v0.4.0"
    assert dep.needs_update is False


def test_resolve_no_tags(tmp_path: Path) -> None:
    """Dep with no tags in source repo keeps latest_tag empty."""
    repo = tmp_path / "empty-repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "t@t.com")
    _git(repo, "config", "user.name", "T")
    (repo / "f").write_text("x", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "init")
    dep = GitDep(
        name="empty-repo",
        current_tag="v0.1.0",
        extras="",
        raw_line="empty-repo @ git+ssh://git@github.com/X/empty-repo.git@v0.1.0",
        repo_name="empty-repo",
    )
    config = _make_config("empty-repo", path=repo)
    resolve_latest_tags([dep], {"empty-repo": config})
    assert dep.latest_tag == ""
    assert dep.needs_update is False


# ---------------------------------------------------------------------------
# build_dep_graph
# ---------------------------------------------------------------------------


def test_build_dep_graph(tmp_path: Path) -> None:
    """Correct adjacency list built from consumer pyproject.toml."""
    # consumer depends on llm-core
    consumer_path = tmp_path / "consumer"
    consumer_path.mkdir()
    _make_pyproject(consumer_path, [_SSH_DEP])

    source_path = tmp_path / "llm-core"
    source_path.mkdir()

    consumer = _make_config("consumer", path=consumer_path)
    source = _make_config("llm-core", path=source_path)
    tracked = {"consumer": consumer, "llm-core": source}
    configs = [consumer, source]

    graph = build_dep_graph(configs, tracked)
    assert graph["consumer"] == ["llm-core"]
    assert graph["llm-core"] == []
    assert consumer.deps == ["llm-core"]


def test_build_dep_graph_missing_clone(tmp_path: Path) -> None:
    """Repo not on disk gets empty dep list, no error raised."""
    config = _make_config("ghost", path=tmp_path / "ghost")
    graph = build_dep_graph([config], {"ghost": config})
    assert graph["ghost"] == []


def test_build_dep_graph_no_pyproject(tmp_path: Path) -> None:
    """Repo on disk but without pyproject.toml gets empty dep list."""
    repo_path = tmp_path / "bare-repo"
    repo_path.mkdir()
    config = _make_config("bare-repo", path=repo_path)
    graph = build_dep_graph([config], {"bare-repo": config})
    assert graph["bare-repo"] == []


# ---------------------------------------------------------------------------
# topological_order
# ---------------------------------------------------------------------------


def test_topological_order_simple() -> None:
    """Sources appear before consumers in topological order."""
    graph = {
        "consumer": ["llm-core"],
        "llm-core": [],
    }
    order = topological_order(graph)
    assert order.index("llm-core") < order.index("consumer")


def test_topological_order_chain() -> None:
    """Multi-level chain is ordered correctly."""
    graph = {
        "app": ["mid"],
        "mid": ["base"],
        "base": [],
    }
    order = topological_order(graph)
    assert order.index("base") < order.index("mid") < order.index("app")


def test_topological_order_no_deps() -> None:
    """Repos with no dependencies all appear in the result."""
    graph = {"a": [], "b": [], "c": []}
    order = topological_order(graph)
    assert sorted(order) == ["a", "b", "c"]


def test_topological_order_cycle() -> None:
    """Cycle raises CyclicDependencyError."""
    graph = {
        "a": ["b"],
        "b": ["a"],
    }
    with pytest.raises(CyclicDependencyError) as exc_info:
        topological_order(graph)
    assert "a" in exc_info.value.cycle_nodes or "b" in exc_info.value.cycle_nodes


def test_topological_order_single_node() -> None:
    """Single repo with no deps returns a one-element list."""
    order = topological_order({"solo": []})
    assert order == ["solo"]


# ---------------------------------------------------------------------------
# update_pyproject
# ---------------------------------------------------------------------------


def test_update_pyproject(tmp_path: Path) -> None:
    """In-place replacement updates the tag and preserves surroundings."""
    pyproject = _make_pyproject(tmp_path, [_SSH_DEP_NO_EXTRAS, _PYPI_DEP])
    dep = GitDep(
        name="fastapi-tools",
        current_tag="v0.1.2",
        extras="",
        raw_line=_SSH_DEP_NO_EXTRAS,
        repo_name="fastapi-tools",
        latest_tag="v0.2.0",
    )
    update_pyproject(pyproject, dep)
    content = pyproject.read_text(encoding="utf-8")
    assert "v0.2.0" in content
    assert "v0.1.2" not in content
    # Unrelated dep is untouched
    assert _PYPI_DEP in content


def test_update_pyproject_with_extras(tmp_path: Path) -> None:
    """Handles dep lines that include extras in the package name."""
    pyproject = _make_pyproject(tmp_path, [_SSH_DEP])
    dep = GitDep(
        name="llm-core",
        current_tag="v0.3.0",
        extras="[all]",
        raw_line=_SSH_DEP,
        repo_name="llm-core",
        latest_tag="v0.4.0",
    )
    update_pyproject(pyproject, dep)
    content = pyproject.read_text(encoding="utf-8")
    assert "v0.4.0" in content
    assert "v0.3.0" not in content
    assert "[all]" in content


def test_update_pyproject_line_not_found(tmp_path: Path) -> None:
    """Raises GitDepNotFoundError when raw_line is absent from the file."""
    pyproject = _make_pyproject(tmp_path, [_PYPI_DEP])
    dep = GitDep(
        name="llm-core",
        current_tag="v0.3.0",
        extras="[all]",
        raw_line=_SSH_DEP,
        repo_name="llm-core",
        latest_tag="v0.4.0",
    )
    with pytest.raises(GitDepNotFoundError):
        update_pyproject(pyproject, dep)
