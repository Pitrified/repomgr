"""Tests for the manager orchestration module.

All git operations are mocked so no real git repos are required.  The
``render_*`` calls are also patched to prevent Rich output from appearing
during the test run.
"""

from pathlib import Path
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from repomgr.config.repos_config import RepoConfig
from repomgr.config.repos_config import RepomgrTomlConfig
from repomgr.config.repos_config import Role
from repomgr.config.repos_config import Settings
from repomgr.git import FetchResult
from repomgr.git import GitError
from repomgr.health import HealthStatus
from repomgr.manager import clone_missing
from repomgr.manager import fetch_all
from repomgr.manager import stale_branches
from repomgr.manager import status_all
from repomgr.state import StateStore

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_repo(
    name: str,
    tmp_path: Path,
    *,
    roles: list[Role] | None = None,
    auto_merge: bool = False,
    on_disk: bool = True,
) -> RepoConfig:
    path = tmp_path / name
    if on_disk:
        path.mkdir(parents=True, exist_ok=True)
    return RepoConfig(
        name=name,
        remote=f"git@github.com:user/{name}.git",
        roles=roles or [Role.SOURCE],
        auto_merge=auto_merge,
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


@pytest.fixture
def two_repos(tmp_path: Path) -> tuple[RepomgrTomlConfig, StateStore]:
    """Return a config with two repos and a fresh state store."""
    repo_a = _make_repo("repo-a", tmp_path)
    repo_b = _make_repo("repo-b", tmp_path, auto_merge=True)
    config = _make_config([repo_a, repo_b], tmp_path)
    store = StateStore(tmp_path / "repos.state.json")
    return config, store


# ---------------------------------------------------------------------------
# fetch_all
# ---------------------------------------------------------------------------


class TestFetchAll:
    """Tests for fetch_all()."""

    def test_fetch_all_updates_state(
        self,
        two_repos: tuple[RepomgrTomlConfig, StateStore],
    ) -> None:
        """State is written after a successful fetch."""
        config, store = two_repos
        fetch_result = FetchResult(new_tags=["v1.1.0"])

        with (
            patch("repomgr.manager.git.fetch", return_value=fetch_result),
            patch("repomgr.manager.git.get_main_sha", return_value="abc123"),
            patch("repomgr.manager.git.current_branch", return_value="main"),
            patch("repomgr.manager.git.is_clean", return_value=True),
            patch("repomgr.manager.git.has_diverged", return_value=False),
            patch("repomgr.manager.git.fast_forward"),
            patch("repomgr.manager.render_fetch_result"),
        ):
            fetch_all(config, store)

        state_a = store.get("repo-a")
        assert state_a.last_fetch_at is not None
        assert state_a.last_seen_main_sha == "abc123"
        assert state_a.new_tags_since_last_fetch == ["v1.1.0"]

    def test_fetch_all_auto_merge(
        self,
        two_repos: tuple[RepomgrTomlConfig, StateStore],
    ) -> None:
        """fast_forward is called for repo-b which has auto_merge=True."""
        config, store = two_repos
        fast_forward_mock = MagicMock()

        with (
            patch("repomgr.manager.git.fetch", return_value=FetchResult()),
            patch("repomgr.manager.git.get_main_sha", return_value="sha1"),
            patch("repomgr.manager.git.current_branch", return_value="main"),
            patch("repomgr.manager.git.is_clean", return_value=True),
            patch("repomgr.manager.git.has_diverged", return_value=False),
            patch("repomgr.manager.git.fast_forward", fast_forward_mock),
            patch("repomgr.manager.render_fetch_result"),
        ):
            fetch_all(config, store)

        # repo-b has auto_merge=True; repo-a does not
        fast_forward_mock.assert_called_once_with(config.repos[1].path)

    def test_fetch_all_skip_auto_merge_dirty(
        self,
        two_repos: tuple[RepomgrTomlConfig, StateStore],
    ) -> None:
        """fast_forward is not called when working tree is dirty."""
        config, store = two_repos
        fast_forward_mock = MagicMock()

        with (
            patch("repomgr.manager.git.fetch", return_value=FetchResult()),
            patch("repomgr.manager.git.get_main_sha", return_value="sha1"),
            patch("repomgr.manager.git.current_branch", return_value="main"),
            patch("repomgr.manager.git.is_clean", return_value=False),
            patch("repomgr.manager.git.has_diverged", return_value=False),
            patch("repomgr.manager.git.fast_forward", fast_forward_mock),
            patch("repomgr.manager.render_fetch_result"),
        ):
            fetch_all(config, store)

        fast_forward_mock.assert_not_called()

    def test_fetch_all_skip_missing_repo(
        self,
        tmp_path: Path,
    ) -> None:
        """Repos not on disk are skipped; other repos still processed."""
        repo_missing = _make_repo("missing", tmp_path, on_disk=False)
        repo_present = _make_repo("present", tmp_path)
        config = _make_config([repo_missing, repo_present], tmp_path)
        store = StateStore(tmp_path / "repos.state.json")

        fetch_mock = MagicMock(return_value=FetchResult())

        with (
            patch("repomgr.manager.git.fetch", fetch_mock),
            patch("repomgr.manager.git.get_main_sha", return_value="sha1"),
            patch("repomgr.manager.git.current_branch", return_value="main"),
            patch("repomgr.manager.git.is_clean", return_value=True),
            patch("repomgr.manager.git.has_diverged", return_value=False),
            patch("repomgr.manager.git.fast_forward"),
            patch("repomgr.manager.render_fetch_result"),
        ):
            fetch_all(config, store)

        # fetch only called for the present repo
        fetch_mock.assert_called_once_with(repo_present.path)

    def test_fetch_all_git_error_continues(
        self,
        two_repos: tuple[RepomgrTomlConfig, StateStore],
    ) -> None:
        """A GitError on one repo does not abort; subsequent repos are processed."""
        config, store = two_repos

        def _fail_first(cwd: Path) -> FetchResult:
            if cwd == config.repos[0].path:
                raise GitError(["git", "fetch"], "network error", 1)
            return FetchResult()

        render_mock = MagicMock()

        with (
            patch("repomgr.manager.git.fetch", side_effect=_fail_first),
            patch("repomgr.manager.git.get_main_sha", return_value="sha1"),
            patch("repomgr.manager.git.current_branch", return_value="main"),
            patch("repomgr.manager.git.is_clean", return_value=True),
            patch("repomgr.manager.git.has_diverged", return_value=False),
            patch("repomgr.manager.git.fast_forward"),
            patch("repomgr.manager.render_fetch_result", render_mock),
        ):
            fetch_all(config, store)

        # Only repo-b renders (repo-a errored)
        render_mock.assert_called_once_with("repo-b", FetchResult())


# ---------------------------------------------------------------------------
# clone_missing
# ---------------------------------------------------------------------------


class TestCloneMissing:
    """Tests for clone_missing()."""

    def test_clone_missing_clones(self, tmp_path: Path) -> None:
        """clone() is called for repos not yet on disk."""
        repo = _make_repo("new-repo", tmp_path, on_disk=False)
        config = _make_config([repo], tmp_path)

        clone_mock = MagicMock()
        render_mock = MagicMock()

        with (
            patch("repomgr.manager.git.clone", clone_mock),
            patch("repomgr.manager.render_clone_result", render_mock),
        ):
            clone_missing(config)

        clone_mock.assert_called_once_with(repo.remote, repo.path)
        render_mock.assert_called_once_with("new-repo", success=True)

    def test_clone_missing_skips_existing(self, tmp_path: Path) -> None:
        """No clone is performed for repos that already exist on disk."""
        repo = _make_repo("existing", tmp_path, on_disk=True)
        config = _make_config([repo], tmp_path)

        clone_mock = MagicMock()

        with patch("repomgr.manager.git.clone", clone_mock):
            clone_missing(config)

        clone_mock.assert_not_called()

    def test_clone_missing_renders_failure(self, tmp_path: Path) -> None:
        """Clone failure is rendered without aborting remaining repos."""
        repo_fail = _make_repo("fail-repo", tmp_path, on_disk=False)
        repo_ok = _make_repo("ok-repo", tmp_path, on_disk=False)
        config = _make_config([repo_fail, repo_ok], tmp_path)

        def _clone_side(remote: str, dest: Path) -> None:
            if dest == repo_fail.path:
                raise GitError(["git", "clone"], "auth error", 128)

        render_mock = MagicMock()

        with (
            patch("repomgr.manager.git.clone", side_effect=_clone_side),
            patch("repomgr.manager.render_clone_result", render_mock),
        ):
            clone_missing(config)

        assert render_mock.call_count == 2
        render_mock.assert_any_call(
            "fail-repo",
            success=False,
            error=str(GitError(["git", "clone"], "auth error", 128)),
        )
        render_mock.assert_any_call("ok-repo", success=True)


# ---------------------------------------------------------------------------
# status_all
# ---------------------------------------------------------------------------


class TestStatusAll:
    """Tests for status_all()."""

    def test_status_all_assembles_rows(
        self,
        two_repos: tuple[RepomgrTomlConfig, StateStore],
    ) -> None:
        """render_status receives a StatusRow for each repo."""
        config, store = two_repos
        render_mock = MagicMock()

        with (
            patch("repomgr.manager.git.current_branch", return_value="main"),
            patch("repomgr.manager.git.is_clean", return_value=True),
            patch("repomgr.manager.git.is_behind_remote", return_value=False),
            patch("repomgr.manager.git.is_ahead_of_remote", return_value=False),
            patch("repomgr.manager.render_status", render_mock),
        ):
            status_all(config, store, dep_graph={})

        render_mock.assert_called_once()
        rows = render_mock.call_args[0][0]
        assert len(rows) == 2
        assert rows[0].name == "repo-a"
        assert rows[1].name == "repo-b"

    def test_status_all_missing_repo_is_red(
        self,
        tmp_path: Path,
    ) -> None:
        """A repo not on disk produces a RED health row."""
        repo = _make_repo("gone", tmp_path, on_disk=False)
        config = _make_config([repo], tmp_path)
        store = StateStore(tmp_path / "repos.state.json")

        render_mock = MagicMock()

        with patch("repomgr.manager.render_status", render_mock):
            status_all(config, store, dep_graph={})

        rows = render_mock.call_args[0][0]
        assert len(rows) == 1
        assert rows[0].health.status == HealthStatus.RED

    def test_status_all_read_only(
        self,
        two_repos: tuple[RepomgrTomlConfig, StateStore],
        tmp_path: Path,
    ) -> None:
        """State file is not modified by status_all."""
        config, store = two_repos
        state_file = tmp_path / "repos.state.json"

        with (
            patch("repomgr.manager.git.current_branch", return_value="main"),
            patch("repomgr.manager.git.is_clean", return_value=True),
            patch("repomgr.manager.git.is_behind_remote", return_value=False),
            patch("repomgr.manager.git.is_ahead_of_remote", return_value=False),
            patch("repomgr.manager.render_status"),
        ):
            status_all(config, store, dep_graph={})

        # State file should not exist (nothing written)
        assert not state_file.exists()

    def test_status_all_behind_sets_is_behind(
        self,
        tmp_path: Path,
    ) -> None:
        """StatusRow reflects is_behind=True when git reports the repo is behind."""
        repo = _make_repo("behind-repo", tmp_path)
        config = _make_config([repo], tmp_path)
        store = StateStore(tmp_path / "repos.state.json")

        render_mock = MagicMock()

        with (
            patch("repomgr.manager.git.current_branch", return_value="main"),
            patch("repomgr.manager.git.is_clean", return_value=True),
            patch("repomgr.manager.git.is_behind_remote", return_value=True),
            patch("repomgr.manager.git.is_ahead_of_remote", return_value=False),
            patch("repomgr.manager.render_status", render_mock),
        ):
            status_all(config, store, dep_graph={})

        rows = render_mock.call_args[0][0]
        assert rows[0].is_behind is True

    def test_status_all_git_error_skips_repo(
        self,
        two_repos: tuple[RepomgrTomlConfig, StateStore],
    ) -> None:
        """A GitError on one repo causes it to be omitted; others appear."""
        config, store = two_repos
        render_mock = MagicMock()

        def _branch_side(cwd: Path) -> str:
            if cwd == config.repos[0].path:
                raise GitError(["git", "rev-parse"], "detached HEAD", 128)
            return "main"

        with (
            patch("repomgr.manager.git.current_branch", side_effect=_branch_side),
            patch("repomgr.manager.git.is_clean", return_value=True),
            patch("repomgr.manager.git.is_behind_remote", return_value=False),
            patch("repomgr.manager.git.is_ahead_of_remote", return_value=False),
            patch("repomgr.manager.render_status", render_mock),
        ):
            status_all(config, store, dep_graph={})

        rows = render_mock.call_args[0][0]
        # repo-a errored, only repo-b appears
        assert len(rows) == 1
        assert rows[0].name == "repo-b"


# ---------------------------------------------------------------------------
# stale_branches
# ---------------------------------------------------------------------------


class TestStaleBranches:
    """Tests for stale_branches()."""

    def test_stale_branches_deletion(self, tmp_path: Path) -> None:
        """delete_branch is called after user confirms."""
        repo = _make_repo("my-repo", tmp_path)
        config = _make_config([repo], tmp_path)

        delete_mock = MagicMock()

        with (
            patch("repomgr.manager.git.list_stale_branches", return_value=["old-feat"]),
            patch("repomgr.manager.render_stale_branches"),
            patch("repomgr.manager.typer.confirm", return_value=True),
            patch("repomgr.manager.git.delete_branch", delete_mock),
        ):
            stale_branches(config)

        delete_mock.assert_called_once_with(repo.path, "old-feat")

    def test_stale_branches_skips_on_deny(self, tmp_path: Path) -> None:
        """delete_branch is not called when user declines the prompt."""
        repo = _make_repo("my-repo", tmp_path)
        config = _make_config([repo], tmp_path)

        delete_mock = MagicMock()

        with (
            patch("repomgr.manager.git.list_stale_branches", return_value=["old-feat"]),
            patch("repomgr.manager.render_stale_branches"),
            patch("repomgr.manager.typer.confirm", return_value=False),
            patch("repomgr.manager.git.delete_branch", delete_mock),
        ):
            stale_branches(config)

        delete_mock.assert_not_called()

    def test_stale_branches_skips_missing_repo(self, tmp_path: Path) -> None:
        """Repos not on disk are silently skipped."""
        repo = _make_repo("gone", tmp_path, on_disk=False)
        config = _make_config([repo], tmp_path)

        list_mock = MagicMock(return_value=["stale"])

        with patch("repomgr.manager.git.list_stale_branches", list_mock):
            stale_branches(config)

        list_mock.assert_not_called()

    def test_stale_branches_no_branches_skips_prompt(self, tmp_path: Path) -> None:
        """When no stale branches exist, confirm is never called."""
        repo = _make_repo("clean-repo", tmp_path)
        config = _make_config([repo], tmp_path)

        confirm_mock = MagicMock()

        with (
            patch("repomgr.manager.git.list_stale_branches", return_value=[]),
            patch("repomgr.manager.typer.confirm", confirm_mock),
        ):
            stale_branches(config)

        confirm_mock.assert_not_called()

    def test_stale_branches_prompts_per_branch(self, tmp_path: Path) -> None:
        """Confirm is called once per stale branch."""
        repo = _make_repo("my-repo", tmp_path)
        config = _make_config([repo], tmp_path)

        confirm_mock = MagicMock(return_value=False)

        with (
            patch(
                "repomgr.manager.git.list_stale_branches",
                return_value=["b1", "b2", "b3"],
            ),
            patch("repomgr.manager.render_stale_branches"),
            patch("repomgr.manager.typer.confirm", confirm_mock),
            patch("repomgr.manager.git.delete_branch"),
        ):
            stale_branches(config)

        assert confirm_mock.call_count == 3

    def test_stale_branches_git_error_listing(self, tmp_path: Path) -> None:
        """GitError during branch listing is logged; processing continues."""
        repo_err = _make_repo("err-repo", tmp_path)
        repo_ok = _make_repo("ok-repo", tmp_path)
        config = _make_config([repo_err, repo_ok], tmp_path)

        confirm_mock = MagicMock(return_value=False)

        def _list_side(cwd: Path) -> list[str]:
            if cwd == repo_err.path:
                raise GitError(["git", "branch"], "error", 1)
            return ["stale"]

        with (
            patch("repomgr.manager.git.list_stale_branches", side_effect=_list_side),
            patch("repomgr.manager.render_stale_branches"),
            patch("repomgr.manager.typer.confirm", confirm_mock),
            patch("repomgr.manager.git.delete_branch"),
        ):
            stale_branches(config)

        # confirm called for ok-repo's branch only
        confirm_mock.assert_called_once()
