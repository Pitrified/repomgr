"""Tests for the dependency update flow.

All git operations, dep-parsing, and renderer calls are mocked so no real git
repos or file system writes are required beyond the pytest ``tmp_path``
fixture.
"""

from pathlib import Path
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from repomgr.config.repos_config import RepoConfig
from repomgr.config.repos_config import RepomgrTomlConfig
from repomgr.config.repos_config import Role
from repomgr.config.repos_config import Settings
from repomgr.deps import GitDep
from repomgr.git import GitError
from repomgr.state import StateStore
from repomgr.update import UnknownRepoError
from repomgr.update import update_deps

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_repo(
    name: str,
    tmp_path: Path,
    *,
    roles: list[Role] | None = None,
    on_disk: bool = True,
    with_pyproject: bool = True,
) -> RepoConfig:
    path = tmp_path / name
    if on_disk:
        path.mkdir(parents=True, exist_ok=True)
        if with_pyproject:
            (path / "pyproject.toml").write_text('[project]\nname = "test"\n')
    return RepoConfig(
        name=name,
        remote=f"git@github.com:user/{name}.git",
        roles=roles or [Role.CONSUMER],
        auto_merge=False,
        test_cmd="uv run pytest",
        path=path,
    )


def _make_config(repos: list[RepoConfig], tmp_path: Path) -> RepomgrTomlConfig:
    return RepomgrTomlConfig(
        settings=Settings(
            base_path=tmp_path,
            state_file=tmp_path / "repos.state.json",
        ),
        repos=repos,
    )


def _make_git_dep(
    name: str = "source-lib",
    current_tag: str = "v1.0.0",
    latest_tag: str = "v2.0.0",
    *,
    needs_update: bool = True,
) -> GitDep:
    dep = GitDep(
        name=name,
        current_tag=current_tag,
        extras="",
        raw_line=(f"{name} @ git+ssh://git@github.com/user/{name}.git@{current_tag}"),
        repo_name=name,
    )
    dep.latest_tag = latest_tag
    dep.needs_update = needs_update
    return dep


@pytest.fixture
def setup(
    tmp_path: Path,
) -> tuple[RepomgrTomlConfig, StateStore, dict[str, list[str]]]:
    """Two-repo setup: one source, one consumer."""
    source = _make_repo("source-lib", tmp_path, roles=[Role.SOURCE])
    consumer = _make_repo("my-app", tmp_path, roles=[Role.CONSUMER])
    config = _make_config([source, consumer], tmp_path)
    store = StateStore(tmp_path / "repos.state.json")
    dep_graph: dict[str, list[str]] = {
        "source-lib": [],
        "my-app": ["source-lib"],
    }
    return config, store, dep_graph


# ---------------------------------------------------------------------------
# Shared mock context helpers
# ---------------------------------------------------------------------------

_GIT_PATCHES = {
    "repomgr.update.git.current_branch": "main",
    "repomgr.update.git.is_clean": True,
    "repomgr.update.git.is_behind_remote": False,
}


def _default_git_patches() -> dict[str, object]:
    return dict(_GIT_PATCHES)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestUpdateDepsFull:
    """Happy-path: detect, branch, edit, test, merge."""

    def test_full_flow(
        self,
        setup: tuple[RepomgrTomlConfig, StateStore, dict[str, list[str]]],
    ) -> None:
        """Full update flow completes and result is 'updated'."""
        config, store, dep_graph = setup
        outdated = [_make_git_dep()]

        with (
            patch("repomgr.update.git.current_branch", return_value="main"),
            patch("repomgr.update.git.is_clean", return_value=True),
            patch("repomgr.update.git.is_behind_remote", return_value=False),
            patch("repomgr.update.git.create_branch"),
            patch("repomgr.update.git.checkout"),
            patch("repomgr.update.git.merge_ff_only"),
            patch("repomgr.update.git.delete_branch"),
            patch("repomgr.update.git.push"),
            patch("repomgr.update.git.commit"),
            patch("repomgr.update.deps_mod.parse_git_deps", return_value=outdated),
            patch("repomgr.update.deps_mod.resolve_latest_tags"),
            patch("repomgr.update.deps_mod.update_pyproject"),
            patch(
                "repomgr.update.deps_mod.topological_order",
                return_value=["source-lib", "my-app"],
            ),
            patch("repomgr.update._run_uv_sync", return_value=True),
            patch("repomgr.update._run_tests", return_value=True),
            patch("repomgr.update.render_update_summary") as mock_render,
        ):
            update_deps(config, store, dep_graph)

        mock_render.assert_called_once()
        results = mock_render.call_args[0][0]
        assert len(results) == 1
        assert results[0].outcome == "updated"
        assert results[0].name == "my-app"
        assert results[0].updated_deps == ["source-lib"]

    def test_state_updated_on_success(
        self,
        setup: tuple[RepomgrTomlConfig, StateStore, dict[str, list[str]]],
    ) -> None:
        """State persists 'ok' outcome and test result after a successful run."""
        config, store, dep_graph = setup
        outdated = [_make_git_dep()]

        with (
            patch("repomgr.update.git.current_branch", return_value="main"),
            patch("repomgr.update.git.is_clean", return_value=True),
            patch("repomgr.update.git.is_behind_remote", return_value=False),
            patch("repomgr.update.git.create_branch"),
            patch("repomgr.update.git.checkout"),
            patch("repomgr.update.git.merge_ff_only"),
            patch("repomgr.update.git.delete_branch"),
            patch("repomgr.update.git.push"),
            patch("repomgr.update.git.commit"),
            patch("repomgr.update.deps_mod.parse_git_deps", return_value=outdated),
            patch("repomgr.update.deps_mod.resolve_latest_tags"),
            patch("repomgr.update.deps_mod.update_pyproject"),
            patch(
                "repomgr.update.deps_mod.topological_order",
                return_value=["source-lib", "my-app"],
            ),
            patch("repomgr.update._run_uv_sync", return_value=True),
            patch("repomgr.update._run_tests", return_value=True),
            patch("repomgr.update.render_update_summary"),
        ):
            update_deps(config, store, dep_graph)

        state = store.get("my-app")
        assert state.last_update_result == "updated"
        assert state.last_update_run_at is not None
        assert state.last_test_run_at is not None
        assert state.last_test_passed is True


class TestUpdateDepsDryRun:
    """Dry-run mode: no git writes, outcome still appears in summary."""

    def test_dry_run_no_git_writes(
        self,
        setup: tuple[RepomgrTomlConfig, StateStore, dict[str, list[str]]],
    ) -> None:
        """No branch is created and no commits are made in dry-run mode."""
        config, store, dep_graph = setup
        outdated = [_make_git_dep()]
        mock_create = MagicMock()

        with (
            patch("repomgr.update.git.current_branch", return_value="main"),
            patch("repomgr.update.git.is_clean", return_value=True),
            patch("repomgr.update.git.is_behind_remote", return_value=False),
            patch("repomgr.update.git.create_branch", mock_create),
            patch("repomgr.update.deps_mod.parse_git_deps", return_value=outdated),
            patch("repomgr.update.deps_mod.resolve_latest_tags"),
            patch(
                "repomgr.update.deps_mod.topological_order",
                return_value=["source-lib", "my-app"],
            ),
            patch("repomgr.update.render_update_summary") as mock_render,
        ):
            update_deps(config, store, dep_graph, dry_run=True)

        mock_create.assert_not_called()
        results = mock_render.call_args[0][0]
        assert results[0].outcome == "updated"

    def test_dry_run_state_not_written(
        self,
        setup: tuple[RepomgrTomlConfig, StateStore, dict[str, list[str]]],
    ) -> None:
        """Dry-run does not persist state."""
        config, store, dep_graph = setup
        outdated = [_make_git_dep()]

        with (
            patch("repomgr.update.git.current_branch", return_value="main"),
            patch("repomgr.update.git.is_clean", return_value=True),
            patch("repomgr.update.git.is_behind_remote", return_value=False),
            patch("repomgr.update.deps_mod.parse_git_deps", return_value=outdated),
            patch("repomgr.update.deps_mod.resolve_latest_tags"),
            patch(
                "repomgr.update.deps_mod.topological_order",
                return_value=["source-lib", "my-app"],
            ),
            patch("repomgr.update.render_update_summary"),
        ):
            update_deps(config, store, dep_graph, dry_run=True)

        state = store.get("my-app")
        assert state.last_update_run_at is None


class TestUpdateDepsNoTests:
    """no_tests=True: skip test suite, merge unconditionally."""

    def test_no_tests_merges_without_running_tests(
        self,
        setup: tuple[RepomgrTomlConfig, StateStore, dict[str, list[str]]],
    ) -> None:
        """Test runner is never called when no_tests is True."""
        config, store, dep_graph = setup
        outdated = [_make_git_dep()]
        mock_tests = MagicMock()

        with (
            patch("repomgr.update.git.current_branch", return_value="main"),
            patch("repomgr.update.git.is_clean", return_value=True),
            patch("repomgr.update.git.is_behind_remote", return_value=False),
            patch("repomgr.update.git.create_branch"),
            patch("repomgr.update.git.checkout"),
            patch("repomgr.update.git.merge_ff_only"),
            patch("repomgr.update.git.delete_branch"),
            patch("repomgr.update.git.push"),
            patch("repomgr.update.git.commit"),
            patch("repomgr.update.deps_mod.parse_git_deps", return_value=outdated),
            patch("repomgr.update.deps_mod.resolve_latest_tags"),
            patch("repomgr.update.deps_mod.update_pyproject"),
            patch(
                "repomgr.update.deps_mod.topological_order",
                return_value=["source-lib", "my-app"],
            ),
            patch("repomgr.update._run_uv_sync", return_value=True),
            patch("repomgr.update._run_tests", mock_tests),
            patch("repomgr.update.render_update_summary") as mock_render,
        ):
            update_deps(config, store, dep_graph, no_tests=True)

        mock_tests.assert_not_called()
        results = mock_render.call_args[0][0]
        assert results[0].outcome == "updated"

    def test_no_tests_state_has_no_test_fields(
        self,
        setup: tuple[RepomgrTomlConfig, StateStore, dict[str, list[str]]],
    ) -> None:
        """State does not record test time or result when no_tests=True."""
        config, store, dep_graph = setup
        outdated = [_make_git_dep()]

        with (
            patch("repomgr.update.git.current_branch", return_value="main"),
            patch("repomgr.update.git.is_clean", return_value=True),
            patch("repomgr.update.git.is_behind_remote", return_value=False),
            patch("repomgr.update.git.create_branch"),
            patch("repomgr.update.git.checkout"),
            patch("repomgr.update.git.merge_ff_only"),
            patch("repomgr.update.git.delete_branch"),
            patch("repomgr.update.git.push"),
            patch("repomgr.update.git.commit"),
            patch("repomgr.update.deps_mod.parse_git_deps", return_value=outdated),
            patch("repomgr.update.deps_mod.resolve_latest_tags"),
            patch("repomgr.update.deps_mod.update_pyproject"),
            patch(
                "repomgr.update.deps_mod.topological_order",
                return_value=["source-lib", "my-app"],
            ),
            patch("repomgr.update._run_uv_sync", return_value=True),
            patch("repomgr.update.render_update_summary"),
        ):
            update_deps(config, store, dep_graph, no_tests=True)

        state = store.get("my-app")
        assert state.last_test_run_at is None
        assert state.last_test_passed is None


class TestUpdateDepsTestFailure:
    """Test failure: leave on branch, state records the failure."""

    def test_test_failure_leaves_on_branch(
        self,
        setup: tuple[RepomgrTomlConfig, StateStore, dict[str, list[str]]],
    ) -> None:
        """On test failure the branch is committed but not merged."""
        config, store, dep_graph = setup
        outdated = [_make_git_dep()]
        mock_push = MagicMock()

        with (
            patch("repomgr.update.git.current_branch", return_value="main"),
            patch("repomgr.update.git.is_clean", return_value=True),
            patch("repomgr.update.git.is_behind_remote", return_value=False),
            patch("repomgr.update.git.create_branch"),
            patch("repomgr.update.git.checkout"),
            patch("repomgr.update.git.merge_ff_only"),
            patch("repomgr.update.git.delete_branch"),
            patch("repomgr.update.git.push", mock_push),
            patch("repomgr.update.git.commit"),
            patch("repomgr.update.deps_mod.parse_git_deps", return_value=outdated),
            patch("repomgr.update.deps_mod.resolve_latest_tags"),
            patch("repomgr.update.deps_mod.update_pyproject"),
            patch(
                "repomgr.update.deps_mod.topological_order",
                return_value=["source-lib", "my-app"],
            ),
            patch("repomgr.update._run_uv_sync", return_value=True),
            patch("repomgr.update._run_tests", return_value=False),
            patch("repomgr.update.render_update_summary") as mock_render,
        ):
            update_deps(config, store, dep_graph)

        mock_push.assert_not_called()
        results = mock_render.call_args[0][0]
        assert results[0].outcome == "failed_tests"

    def test_test_failure_state_records_failure(
        self,
        setup: tuple[RepomgrTomlConfig, StateStore, dict[str, list[str]]],
    ) -> None:
        """State persists 'failed_tests' and last_test_passed=False."""
        config, store, dep_graph = setup
        outdated = [_make_git_dep()]

        with (
            patch("repomgr.update.git.current_branch", return_value="main"),
            patch("repomgr.update.git.is_clean", return_value=True),
            patch("repomgr.update.git.is_behind_remote", return_value=False),
            patch("repomgr.update.git.create_branch"),
            patch("repomgr.update.git.checkout"),
            patch("repomgr.update.git.merge_ff_only"),
            patch("repomgr.update.git.delete_branch"),
            patch("repomgr.update.git.push"),
            patch("repomgr.update.git.commit"),
            patch("repomgr.update.deps_mod.parse_git_deps", return_value=outdated),
            patch("repomgr.update.deps_mod.resolve_latest_tags"),
            patch("repomgr.update.deps_mod.update_pyproject"),
            patch(
                "repomgr.update.deps_mod.topological_order",
                return_value=["source-lib", "my-app"],
            ),
            patch("repomgr.update._run_uv_sync", return_value=True),
            patch("repomgr.update._run_tests", return_value=False),
            patch("repomgr.update.render_update_summary"),
        ):
            update_deps(config, store, dep_graph)

        state = store.get("my-app")
        assert state.last_update_result == "failed_tests"
        assert state.last_test_passed is False


class TestUpdateDepsNoUpdates:
    """Nothing outdated: record no_updates and skip git operations."""

    def test_no_updates_skips_branch(
        self,
        setup: tuple[RepomgrTomlConfig, StateStore, dict[str, list[str]]],
    ) -> None:
        """No branch is created when deps are current."""
        config, store, dep_graph = setup
        current_dep = _make_git_dep(needs_update=False)
        current_dep.latest_tag = current_dep.current_tag
        mock_create = MagicMock()

        with (
            patch("repomgr.update.git.current_branch", return_value="main"),
            patch("repomgr.update.git.is_clean", return_value=True),
            patch("repomgr.update.git.is_behind_remote", return_value=False),
            patch("repomgr.update.git.create_branch", mock_create),
            patch(
                "repomgr.update.deps_mod.parse_git_deps",
                return_value=[current_dep],
            ),
            patch("repomgr.update.deps_mod.resolve_latest_tags"),
            patch(
                "repomgr.update.deps_mod.topological_order",
                return_value=["source-lib", "my-app"],
            ),
            patch("repomgr.update.render_update_summary") as mock_render,
        ):
            update_deps(config, store, dep_graph)

        mock_create.assert_not_called()
        results = mock_render.call_args[0][0]
        assert results[0].outcome == "no_updates"

    def test_no_updates_state_recorded(
        self,
        setup: tuple[RepomgrTomlConfig, StateStore, dict[str, list[str]]],
    ) -> None:
        """State records 'no_updates' when deps are current."""
        config, store, dep_graph = setup
        current_dep = _make_git_dep(needs_update=False)
        current_dep.latest_tag = current_dep.current_tag

        with (
            patch("repomgr.update.git.current_branch", return_value="main"),
            patch("repomgr.update.git.is_clean", return_value=True),
            patch("repomgr.update.git.is_behind_remote", return_value=False),
            patch(
                "repomgr.update.deps_mod.parse_git_deps",
                return_value=[current_dep],
            ),
            patch("repomgr.update.deps_mod.resolve_latest_tags"),
            patch(
                "repomgr.update.deps_mod.topological_order",
                return_value=["source-lib", "my-app"],
            ),
            patch("repomgr.update.render_update_summary"),
        ):
            update_deps(config, store, dep_graph)

        state = store.get("my-app")
        assert state.last_update_result == "no_updates"


class TestUpdateDepsSkip:
    """Various pre-check failures that produce 'skipped' outcomes."""

    def test_skip_dirty_working_tree(
        self,
        setup: tuple[RepomgrTomlConfig, StateStore, dict[str, list[str]]],
    ) -> None:
        """Repo with dirty working tree is skipped."""
        config, store, dep_graph = setup
        mock_create = MagicMock()

        with (
            patch("repomgr.update.git.current_branch", return_value="main"),
            patch("repomgr.update.git.is_clean", return_value=False),
            patch("repomgr.update.git.is_behind_remote", return_value=False),
            patch("repomgr.update.git.create_branch", mock_create),
            patch(
                "repomgr.update.deps_mod.topological_order",
                return_value=["source-lib", "my-app"],
            ),
            patch("repomgr.update.render_update_summary") as mock_render,
        ):
            update_deps(config, store, dep_graph)

        mock_create.assert_not_called()
        results = mock_render.call_args[0][0]
        assert results[0].outcome == "skipped"

    def test_skip_not_on_main(
        self,
        setup: tuple[RepomgrTomlConfig, StateStore, dict[str, list[str]]],
    ) -> None:
        """Repo not on main branch is skipped."""
        config, store, dep_graph = setup

        with (
            patch(
                "repomgr.update.git.current_branch",
                return_value="feature/something",
            ),
            patch("repomgr.update.git.is_clean", return_value=True),
            patch("repomgr.update.git.is_behind_remote", return_value=False),
            patch(
                "repomgr.update.deps_mod.topological_order",
                return_value=["source-lib", "my-app"],
            ),
            patch("repomgr.update.render_update_summary") as mock_render,
        ):
            update_deps(config, store, dep_graph)

        results = mock_render.call_args[0][0]
        assert results[0].outcome == "skipped"
        assert "main" in (results[0].error or "")

    def test_skip_behind_remote(
        self,
        setup: tuple[RepomgrTomlConfig, StateStore, dict[str, list[str]]],
    ) -> None:
        """Repo behind remote is skipped."""
        config, store, dep_graph = setup

        with (
            patch("repomgr.update.git.current_branch", return_value="main"),
            patch("repomgr.update.git.is_clean", return_value=True),
            patch("repomgr.update.git.is_behind_remote", return_value=True),
            patch(
                "repomgr.update.deps_mod.topological_order",
                return_value=["source-lib", "my-app"],
            ),
            patch("repomgr.update.render_update_summary") as mock_render,
        ):
            update_deps(config, store, dep_graph)

        results = mock_render.call_args[0][0]
        assert results[0].outcome == "skipped"
        assert "behind" in (results[0].error or "")

    def test_skip_no_pyproject(
        self,
        tmp_path: Path,
    ) -> None:
        """Repo with no pyproject.toml is skipped."""
        source = _make_repo("source-lib", tmp_path, roles=[Role.SOURCE])
        consumer = _make_repo(
            "my-app",
            tmp_path,
            roles=[Role.CONSUMER],
            with_pyproject=False,
        )
        config = _make_config([source, consumer], tmp_path)
        store = StateStore(tmp_path / "repos.state.json")
        dep_graph: dict[str, list[str]] = {
            "source-lib": [],
            "my-app": ["source-lib"],
        }

        with (
            patch(
                "repomgr.update.deps_mod.topological_order",
                return_value=["source-lib", "my-app"],
            ),
            patch("repomgr.update.render_update_summary") as mock_render,
        ):
            update_deps(config, store, dep_graph)

        results = mock_render.call_args[0][0]
        assert results[0].outcome == "skipped"
        assert "pyproject" in (results[0].error or "")

    def test_skip_path_not_on_disk(
        self,
        tmp_path: Path,
    ) -> None:
        """Repo whose path does not exist is skipped."""
        source = _make_repo("source-lib", tmp_path, roles=[Role.SOURCE])
        consumer = _make_repo(
            "my-app",
            tmp_path,
            roles=[Role.CONSUMER],
            on_disk=False,
        )
        config = _make_config([source, consumer], tmp_path)
        store = StateStore(tmp_path / "repos.state.json")
        dep_graph: dict[str, list[str]] = {
            "source-lib": [],
            "my-app": ["source-lib"],
        }

        with (
            patch(
                "repomgr.update.deps_mod.topological_order",
                return_value=["source-lib", "my-app"],
            ),
            patch("repomgr.update.render_update_summary") as mock_render,
        ):
            update_deps(config, store, dep_graph)

        results = mock_render.call_args[0][0]
        assert results[0].outcome == "skipped"

    def test_skip_source_only_repos(
        self,
        setup: tuple[RepomgrTomlConfig, StateStore, dict[str, list[str]]],
    ) -> None:
        """Repos with only the SOURCE role are not processed."""
        config, store, dep_graph = setup

        with (
            patch(
                "repomgr.update.deps_mod.topological_order",
                return_value=["source-lib", "my-app"],
            ),
            patch("repomgr.update.git.current_branch", return_value="main"),
            patch("repomgr.update.git.is_clean", return_value=True),
            patch("repomgr.update.git.is_behind_remote", return_value=False),
            patch(
                "repomgr.update.deps_mod.parse_git_deps",
                return_value=[],
            ),
            patch("repomgr.update.deps_mod.resolve_latest_tags"),
            patch("repomgr.update.render_update_summary") as mock_render,
        ):
            update_deps(config, store, dep_graph)

        # Only the consumer "my-app" should appear in results
        results = mock_render.call_args[0][0]
        names = [r.name for r in results]
        assert "source-lib" not in names
        assert "my-app" in names


class TestUpdateDepsSingleRepo:
    """--repo flag filters to one repo."""

    def test_single_repo_processes_only_that_repo(
        self,
        setup: tuple[RepomgrTomlConfig, StateStore, dict[str, list[str]]],
    ) -> None:
        """Only the named repo is processed when repo_name is given."""
        config, store, dep_graph = setup
        outdated = [_make_git_dep()]
        processed: list[str] = []

        def _branch_side(cwd: Path, name: str) -> None:
            processed.append(name)

        with (
            patch("repomgr.update.git.current_branch", return_value="main"),
            patch("repomgr.update.git.is_clean", return_value=True),
            patch("repomgr.update.git.is_behind_remote", return_value=False),
            patch(
                "repomgr.update.git.create_branch",
                side_effect=_branch_side,
            ),
            patch("repomgr.update.git.checkout"),
            patch("repomgr.update.git.merge_ff_only"),
            patch("repomgr.update.git.delete_branch"),
            patch("repomgr.update.git.push"),
            patch("repomgr.update.git.commit"),
            patch("repomgr.update.deps_mod.parse_git_deps", return_value=outdated),
            patch("repomgr.update.deps_mod.resolve_latest_tags"),
            patch("repomgr.update.deps_mod.update_pyproject"),
            patch(
                "repomgr.update.deps_mod.topological_order",
                return_value=["source-lib", "my-app"],
            ),
            patch("repomgr.update._run_uv_sync", return_value=True),
            patch("repomgr.update._run_tests", return_value=True),
            patch("repomgr.update.render_update_summary") as mock_render,
        ):
            update_deps(config, store, dep_graph, repo_name="my-app")

        results = mock_render.call_args[0][0]
        assert len(results) == 1
        assert results[0].name == "my-app"

    def test_unknown_repo_raises(
        self,
        setup: tuple[RepomgrTomlConfig, StateStore, dict[str, list[str]]],
    ) -> None:
        """UnknownRepoError is raised for a repo name not in the config."""
        config, store, dep_graph = setup

        with (
            patch(
                "repomgr.update.deps_mod.topological_order",
                return_value=["source-lib", "my-app"],
            ),
            pytest.raises(UnknownRepoError, match="ghost-repo"),
        ):
            update_deps(config, store, dep_graph, repo_name="ghost-repo")


class TestUpdateDepsTopologicalOrder:
    """Repos are processed in topological (source-first) order."""

    def test_topological_order_respected(
        self,
        tmp_path: Path,
    ) -> None:
        """Consumer repos are processed after their sources."""
        lib_a = _make_repo("lib-a", tmp_path, roles=[Role.SOURCE])
        app_b = _make_repo("app-b", tmp_path, roles=[Role.CONSUMER])
        app_c = _make_repo("app-c", tmp_path, roles=[Role.CONSUMER])
        config = _make_config([lib_a, app_b, app_c], tmp_path)
        store = StateStore(tmp_path / "repos.state.json")
        dep_graph: dict[str, list[str]] = {
            "lib-a": [],
            "app-b": ["lib-a"],
            "app-c": ["app-b"],
        }
        # Expected topological order: lib-a, app-b, app-c
        topo_order = ["lib-a", "app-b", "app-c"]
        processed: list[str] = []

        def _fake_pre_check(repo_config: RepoConfig) -> None:
            processed.append(repo_config.name)

        outdated = [_make_git_dep()]

        with (
            patch(
                "repomgr.update.deps_mod.topological_order",
                return_value=topo_order,
            ),
            patch(
                "repomgr.update._check_preconditions",
                side_effect=_fake_pre_check,
            ),
            patch(
                "repomgr.update._find_outdated_deps",
                return_value=outdated,
            ),
            patch(
                "repomgr.update._execute_update",
                return_value=("updated", None, None),
            ),
            patch("repomgr.update._record_state"),
            patch("repomgr.update.render_update_summary"),
        ):
            update_deps(config, store, dep_graph)

        # lib-a is source-only, skipped; app-b and app-c processed in order
        assert processed == ["app-b", "app-c"]


class TestUpdateDepsGitErrorHandling:
    """Edge cases around GitError during pre-checks."""

    def test_is_behind_remote_git_error_proceeds(
        self,
        setup: tuple[RepomgrTomlConfig, StateStore, dict[str, list[str]]],
    ) -> None:
        """GitError from is_behind_remote is treated as 'not behind'."""
        config, store, dep_graph = setup
        outdated = [_make_git_dep()]

        with (
            patch("repomgr.update.git.current_branch", return_value="main"),
            patch("repomgr.update.git.is_clean", return_value=True),
            patch(
                "repomgr.update.git.is_behind_remote",
                side_effect=GitError(["git", "rev-list"], "no remote", 128),
            ),
            patch("repomgr.update.git.create_branch"),
            patch("repomgr.update.git.checkout"),
            patch("repomgr.update.git.merge_ff_only"),
            patch("repomgr.update.git.delete_branch"),
            patch("repomgr.update.git.push"),
            patch("repomgr.update.git.commit"),
            patch("repomgr.update.deps_mod.parse_git_deps", return_value=outdated),
            patch("repomgr.update.deps_mod.resolve_latest_tags"),
            patch("repomgr.update.deps_mod.update_pyproject"),
            patch(
                "repomgr.update.deps_mod.topological_order",
                return_value=["source-lib", "my-app"],
            ),
            patch("repomgr.update._run_uv_sync", return_value=True),
            patch("repomgr.update._run_tests", return_value=True),
            patch("repomgr.update.render_update_summary") as mock_render,
        ):
            update_deps(config, store, dep_graph)

        results = mock_render.call_args[0][0]
        assert results[0].outcome == "updated"

    def test_not_a_git_repo_is_skipped(
        self,
        setup: tuple[RepomgrTomlConfig, StateStore, dict[str, list[str]]],
    ) -> None:
        """GitError from current_branch causes 'skipped' outcome."""
        config, store, dep_graph = setup

        with (
            patch(
                "repomgr.update.git.current_branch",
                side_effect=GitError(["git", "rev-parse"], "fatal", 128),
            ),
            patch(
                "repomgr.update.deps_mod.topological_order",
                return_value=["source-lib", "my-app"],
            ),
            patch("repomgr.update.render_update_summary") as mock_render,
        ):
            update_deps(config, store, dep_graph)

        results = mock_render.call_args[0][0]
        assert results[0].outcome == "skipped"
