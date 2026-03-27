"""Tests for the health module."""

from datetime import UTC
from datetime import datetime
from pathlib import Path

from repomgr.config.repos_config import RepoConfig
from repomgr.config.repos_config import Role
from repomgr.health import HealthStatus
from repomgr.health import LiveRepoStatus
from repomgr.health import compute_health
from repomgr.state import RepoState

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(*, auto_merge: bool = False) -> RepoConfig:
    return RepoConfig(
        name="my-repo",
        remote="git@github.com:user/my-repo.git",
        roles=[Role.SOURCE],
        auto_merge=auto_merge,
        test_cmd="uv run pytest",
        path=Path("/srv/repos/my-repo"),
    )


def _make_state(
    *,
    last_fetch_at: datetime | None = datetime(2026, 3, 27, tzinfo=UTC),
    last_test_passed: bool | None = True,
) -> RepoState:
    return RepoState(
        name="my-repo",
        last_fetch_at=last_fetch_at,
        last_test_passed=last_test_passed,
    )


def _live(
    *,
    repo_exists: bool = True,
    branch: str = "main",
    is_clean: bool = True,
    is_behind: bool = False,
    is_ahead: bool = False,
    has_diverged: bool = False,
) -> LiveRepoStatus:
    return LiveRepoStatus(
        repo_exists=repo_exists,
        branch=branch,
        is_clean=is_clean,
        is_behind=is_behind,
        is_ahead=is_ahead,
        has_diverged=has_diverged,
    )


# ---------------------------------------------------------------------------
# GREEN
# ---------------------------------------------------------------------------


def test_green_all_clear() -> None:
    """Perfectly healthy repo returns GREEN with no reasons."""
    report = compute_health(_make_config(), _make_state(), _live())
    assert report.status == HealthStatus.GREEN
    assert report.reasons == []


# ---------------------------------------------------------------------------
# RED conditions
# ---------------------------------------------------------------------------


def test_red_not_on_disk() -> None:
    """Repo not on disk returns RED immediately."""
    report = compute_health(_make_config(), _make_state(), _live(repo_exists=False))
    assert report.status == HealthStatus.RED
    assert "repo not found on disk" in report.reasons


def test_red_not_on_disk_short_circuits() -> None:
    """No other reasons are collected when the repo is not on disk."""
    live = _live(repo_exists=False, is_clean=False, has_diverged=True)
    report = compute_health(_make_config(), _make_state(), live)
    assert report.status == HealthStatus.RED
    assert report.reasons == ["repo not found on disk"]


def test_red_diverged() -> None:
    """Diverged from remote returns RED."""
    report = compute_health(_make_config(), _make_state(), _live(has_diverged=True))
    assert report.status == HealthStatus.RED
    assert "diverged from origin/main" in report.reasons


# ---------------------------------------------------------------------------
# YELLOW conditions
# ---------------------------------------------------------------------------


def test_yellow_not_on_main() -> None:
    """On a non-main branch returns YELLOW."""
    report = compute_health(_make_config(), _make_state(), _live(branch="feature/wip"))
    assert report.status == HealthStatus.YELLOW
    assert "on branch feature/wip, not main" in report.reasons


def test_yellow_dirty() -> None:
    """Uncommitted changes returns YELLOW."""
    report = compute_health(_make_config(), _make_state(), _live(is_clean=False))
    assert report.status == HealthStatus.YELLOW
    assert "uncommitted changes" in report.reasons


def test_yellow_behind_no_auto_merge() -> None:
    """Behind remote with auto_merge=False returns YELLOW."""
    report = compute_health(
        _make_config(auto_merge=False), _make_state(), _live(is_behind=True)
    )
    assert report.status == HealthStatus.YELLOW
    assert "behind origin/main" in report.reasons


def test_behind_with_auto_merge_not_yellow() -> None:
    """Being behind remote is not flagged when auto_merge=True."""
    report = compute_health(
        _make_config(auto_merge=True), _make_state(), _live(is_behind=True)
    )
    assert report.status == HealthStatus.GREEN
    assert not any("behind" in r for r in report.reasons)


def test_yellow_ahead() -> None:
    """Unpushed commits returns YELLOW."""
    report = compute_health(_make_config(), _make_state(), _live(is_ahead=True))
    assert report.status == HealthStatus.YELLOW
    assert "ahead of origin/main (unpushed commits)" in report.reasons


def test_yellow_test_failed() -> None:
    """Last test run failed returns YELLOW."""
    state = _make_state(last_test_passed=False)
    report = compute_health(_make_config(), state, _live())
    assert report.status == HealthStatus.YELLOW
    assert "last test run failed" in report.reasons


def test_yellow_never_fetched() -> None:
    """Never fetched returns YELLOW."""
    state = _make_state(last_fetch_at=None)
    report = compute_health(_make_config(), state, _live())
    assert report.status == HealthStatus.YELLOW
    assert "never fetched" in report.reasons


def test_yellow_deps_behind() -> None:
    """Consumer with stale deps returns YELLOW."""
    report = compute_health(
        _make_config(), _make_state(), _live(), deps_behind=["llm-core"]
    )
    assert report.status == HealthStatus.YELLOW
    assert "deps behind: llm-core" in report.reasons


def test_yellow_deps_behind_multiple() -> None:
    """Multiple stale deps are joined in the reason string."""
    report = compute_health(
        _make_config(), _make_state(), _live(), deps_behind=["lib-a", "lib-b"]
    )
    assert report.status == HealthStatus.YELLOW
    assert "deps behind: lib-a, lib-b" in report.reasons


def test_deps_behind_empty_list_is_green() -> None:
    """An empty deps_behind list does not add a YELLOW reason."""
    report = compute_health(_make_config(), _make_state(), _live(), deps_behind=[])
    assert report.status == HealthStatus.GREEN


def test_deps_behind_none_is_green() -> None:
    """deps_behind=None (default) does not add a YELLOW reason."""
    report = compute_health(_make_config(), _make_state(), _live(), deps_behind=None)
    assert report.status == HealthStatus.GREEN


# ---------------------------------------------------------------------------
# Precedence and multi-reason
# ---------------------------------------------------------------------------


def test_red_overrides_yellow() -> None:
    """Diverged + dirty = RED (RED takes precedence over YELLOW)."""
    live = _live(has_diverged=True, is_clean=False)
    report = compute_health(_make_config(), _make_state(), live)
    assert report.status == HealthStatus.RED
    assert "diverged from origin/main" in report.reasons
    assert "uncommitted changes" in report.reasons


def test_multiple_yellow_reasons() -> None:
    """All YELLOW conditions are collected, not just the first."""
    live = _live(branch="dev", is_clean=False, is_ahead=True)
    state = _make_state(last_fetch_at=None, last_test_passed=False)
    report = compute_health(_make_config(), state, live, deps_behind=["lib-x"])
    assert report.status == HealthStatus.YELLOW
    assert len(report.reasons) >= 5
    assert "on branch dev, not main" in report.reasons
    assert "uncommitted changes" in report.reasons
    assert "ahead of origin/main (unpushed commits)" in report.reasons
    assert "last test run failed" in report.reasons
    assert "never fetched" in report.reasons
    assert "deps behind: lib-x" in report.reasons
