"""Tests for the renderer module.

All tests capture Rich output via a ``Console(file=StringIO())`` instance
passed to each function.  No assertions are made about exact layout; we
verify that the output contains expected names, keywords, and color markers.
"""

from datetime import UTC
from datetime import datetime
from io import StringIO

from rich.console import Console

from repomgr.git import FetchResult
from repomgr.health import HealthReport
from repomgr.health import HealthStatus
from repomgr.renderer import StatusRow
from repomgr.renderer import UpdateResult
from repomgr.renderer import render_clone_result
from repomgr.renderer import render_dep_graph
from repomgr.renderer import render_fetch_result
from repomgr.renderer import render_stale_branches
from repomgr.renderer import render_status
from repomgr.renderer import render_update_summary
from repomgr.state import RepoState

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _console() -> tuple[Console, StringIO]:
    buf = StringIO()
    return Console(file=buf, highlight=False, no_color=True, width=200), buf


def _state(*, fetched: bool = True) -> RepoState:
    return RepoState(
        name="repo",
        last_fetch_at=datetime(2026, 3, 27, 9, 14, tzinfo=UTC) if fetched else None,
    )


def _green_row(name: str) -> StatusRow:
    return StatusRow(
        name=name,
        health=HealthReport(status=HealthStatus.GREEN),
        branch="main",
        is_clean=True,
        is_behind=False,
        is_ahead=False,
        state=_state(),
    )


def _yellow_row(name: str, *, reason: str = "behind origin/main") -> StatusRow:
    return StatusRow(
        name=name,
        health=HealthReport(status=HealthStatus.YELLOW, reasons=[reason]),
        branch="main",
        is_clean=True,
        is_behind=True,
        is_ahead=False,
        state=_state(),
    )


def _red_row(name: str) -> StatusRow:
    return StatusRow(
        name=name,
        health=HealthReport(
            status=HealthStatus.RED,
            reasons=["repo not found on disk"],
        ),
        branch="",
        is_clean=True,
        is_behind=False,
        is_ahead=False,
        state=_state(fetched=False),
    )


# ---------------------------------------------------------------------------
# render_status
# ---------------------------------------------------------------------------


def test_render_status_all_green() -> None:
    """All-green rows print repo names and GREEN status."""
    con, buf = _console()
    rows = [_green_row("llm-core"), _green_row("fastapi-tools")]
    render_status(rows, console=con)
    output = buf.getvalue()
    assert "llm-core" in output
    assert "fastapi-tools" in output
    assert "GREEN" in output


def test_render_status_mixed() -> None:
    """Mixed health rows each show the correct status label."""
    con, buf = _console()
    rows = [
        _green_row("source-a"),
        _yellow_row("consumer-b", reason="behind origin/main"),
        _red_row("broken-c"),
    ]
    render_status(rows, console=con)
    output = buf.getvalue()
    assert "source-a" in output
    assert "consumer-b" in output
    assert "broken-c" in output
    assert "GREEN" in output
    assert "YELLOW" in output
    assert "RED" in output
    # Reason footnote printed below table
    assert "behind origin/main" in output
    assert "repo not found on disk" in output


def test_render_status_with_deps_behind() -> None:
    """Deps-behind names appear in the output."""
    con, buf = _console()
    row = StatusRow(
        name="consumer",
        health=HealthReport(
            status=HealthStatus.YELLOW, reasons=["deps behind: llm-core"]
        ),
        branch="main",
        is_clean=True,
        is_behind=False,
        is_ahead=False,
        state=_state(),
        deps_behind=["llm-core"],
    )
    render_status([row], console=con)
    output = buf.getvalue()
    assert "llm-core" in output


def test_render_status_never_fetched() -> None:
    """Repos never fetched show 'never' in the Last Fetch column."""
    con, buf = _console()
    row = _green_row("fresh-repo")
    row.state = _state(fetched=False)
    render_status([row], console=con)
    output = buf.getvalue()
    assert "never" in output


def test_render_status_empty_rows() -> None:
    """Empty row list renders without error."""
    con, buf = _console()
    render_status([], console=con)
    # Should not raise; output is an empty table
    assert buf.getvalue() is not None


# ---------------------------------------------------------------------------
# render_fetch_result
# ---------------------------------------------------------------------------


def test_render_fetch_result_with_tags() -> None:
    """New tag names appear in fetch output."""
    con, buf = _console()
    result = FetchResult(new_tags=["v0.4.0", "v0.4.1"])
    render_fetch_result("llm-core", result, console=con)
    output = buf.getvalue()
    assert "llm-core" in output
    assert "v0.4.0" in output
    assert "v0.4.1" in output


def test_render_fetch_result_with_commits() -> None:
    """Commit log entries appear when main advanced."""
    con, buf = _console()
    result = FetchResult(
        main_advanced_by=2,
        new_commit_log=["abc1234 feat: parser", "def5678 fix: edge case"],
    )
    render_fetch_result("my-repo", result, console=con)
    output = buf.getvalue()
    assert "my-repo" in output
    assert "2" in output
    assert "abc1234" in output
    assert "def5678" in output


def test_render_fetch_result_no_changes() -> None:
    """Empty fetch result prints a 'No changes' message."""
    con, buf = _console()
    result = FetchResult()
    render_fetch_result("stable-repo", result, console=con)
    output = buf.getvalue()
    assert "stable-repo" in output
    assert "No changes" in output


def test_render_fetch_result_with_new_branches() -> None:
    """New branch names appear in fetch output."""
    con, buf = _console()
    result = FetchResult(new_branches=["origin/feature-x"])
    render_fetch_result("branchy", result, console=con)
    output = buf.getvalue()
    assert "origin/feature-x" in output


# ---------------------------------------------------------------------------
# render_clone_result
# ---------------------------------------------------------------------------


def test_render_clone_result_success() -> None:
    """Successful clone prints the repo name."""
    con, buf = _console()
    render_clone_result("new-repo", success=True, console=con)
    output = buf.getvalue()
    assert "new-repo" in output
    assert "cloned" in output.lower() or "new-repo" in output


def test_render_clone_result_failure() -> None:
    """Failed clone prints the repo name and error message."""
    con, buf = _console()
    render_clone_result("broken", success=False, error="auth failed", console=con)
    output = buf.getvalue()
    assert "broken" in output
    assert "auth failed" in output


def test_render_clone_result_failure_no_error() -> None:
    """Failed clone without error message still prints the repo name."""
    con, buf = _console()
    render_clone_result("broken", success=False, console=con)
    output = buf.getvalue()
    assert "broken" in output


# ---------------------------------------------------------------------------
# render_update_summary
# ---------------------------------------------------------------------------


def test_render_update_summary() -> None:
    """All outcomes and their metadata appear in the summary table."""
    con, buf = _console()
    results = [
        UpdateResult("consumer-a", outcome="updated", updated_deps=["llm-core"]),
        UpdateResult("consumer-b", outcome="no_updates"),
        UpdateResult("consumer-c", outcome="failed_tests", error="exit code 1"),
        UpdateResult("consumer-d", outcome="skipped"),
    ]
    render_update_summary(results, console=con)
    output = buf.getvalue()
    assert "consumer-a" in output
    assert "llm-core" in output
    assert "consumer-b" in output
    assert "no_updates" in output
    assert "consumer-c" in output
    assert "exit code 1" in output
    assert "consumer-d" in output


def test_render_update_summary_empty() -> None:
    """Empty results list renders without error."""
    con, buf = _console()
    render_update_summary([], console=con)
    assert buf.getvalue() is not None


# ---------------------------------------------------------------------------
# render_dep_graph
# ---------------------------------------------------------------------------


def test_render_dep_graph() -> None:
    """Dependency graph shows source and consumer labels for each repo."""
    con, buf = _console()
    graph: dict[str, list[str]] = {
        "llm-core": [],
        "fastapi-tools": [],
        "recipamatic": ["llm-core", "fastapi-tools"],
        "some-exception": ["llm-core"],
    }
    render_dep_graph(graph, console=con)
    output = buf.getvalue()
    assert "llm-core" in output
    assert "fastapi-tools" in output
    assert "recipamatic" in output
    assert "some-exception" in output
    assert "source" in output
    assert "consumer" in output


def test_render_dep_graph_sources_only() -> None:
    """Graph with no consumers labels all repos as sources."""
    con, buf = _console()
    graph: dict[str, list[str]] = {"lib-a": [], "lib-b": []}
    render_dep_graph(graph, console=con)
    output = buf.getvalue()
    assert "lib-a" in output
    assert "lib-b" in output
    assert "source" in output


def test_render_dep_graph_empty() -> None:
    """Empty graph renders without error."""
    con, buf = _console()
    render_dep_graph({}, console=con)
    assert buf.getvalue() is not None


# ---------------------------------------------------------------------------
# render_stale_branches
# ---------------------------------------------------------------------------


def test_render_stale_branches_with_branches() -> None:
    """Stale branch names appear in the output panel."""
    con, buf = _console()
    render_stale_branches("my-repo", ["fix/old", "feat/done"], console=con)
    output = buf.getvalue()
    assert "my-repo" in output
    assert "fix/old" in output
    assert "feat/done" in output


def test_render_stale_branches_empty() -> None:
    """Empty stale branch list prints 'no stale branches'."""
    con, buf = _console()
    render_stale_branches("clean-repo", [], console=con)
    output = buf.getvalue()
    assert "clean-repo" in output
    assert "no stale branches" in output
