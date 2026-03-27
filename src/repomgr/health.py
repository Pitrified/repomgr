"""Traffic-light health scoring for tracked repositories.

This module is a pure computation layer: it accepts typed data structures and
returns a ``HealthReport``.  It never calls git, reads files, or writes state.
All inputs are gathered by the caller (``manager.py``) before invoking
``compute_health()``.

Pattern rules:
    RED conditions are checked first.  If the repo is not on disk no further
    checks are meaningful, so the function returns early.  YELLOW conditions
    are all collected before determining the final status; the caller receives
    every reason, not just the first one that triggered.
"""

from dataclasses import dataclass
from dataclasses import field
from enum import StrEnum

from repomgr.config.repos_config import RepoConfig
from repomgr.state import RepoState

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class HealthStatus(StrEnum):
    """Overall traffic-light health level for a repository.

    Attributes:
        GREEN: All checks passed; repo is in good shape.
        YELLOW: At least one advisory condition warrants attention.
        RED: At least one critical condition requires immediate action.
    """

    GREEN = "green"
    YELLOW = "yellow"
    RED = "red"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class LiveRepoStatus:
    """Current git status gathered at check time.

    Populated by cheap git calls in ``manager.py`` immediately before
    ``compute_health()`` is called.

    Attributes:
        repo_exists: Whether the local clone directory is present.
        branch: Name of the currently checked-out branch.
        is_clean: ``True`` when the working tree has no uncommitted changes.
        is_behind: ``True`` when local main is behind the remote tracking branch.
        is_ahead: ``True`` when local main has commits not yet pushed.
        has_diverged: ``True`` when local and remote have both advanced.
    """

    repo_exists: bool
    branch: str = ""
    is_clean: bool = True
    is_behind: bool = False
    is_ahead: bool = False
    has_diverged: bool = False


@dataclass
class HealthReport:
    """Result of a single health evaluation.

    Attributes:
        status: Overall ``HealthStatus`` for the repository.
        reasons: Human-readable explanation for each non-green condition,
            in evaluation order.  Empty when status is GREEN.
    """

    status: HealthStatus
    reasons: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _collect_yellow_reasons(
    config: RepoConfig,
    state: RepoState,
    live: LiveRepoStatus,
    deps_behind: list[str] | None,
) -> list[str]:
    """Return all YELLOW reason strings for a live repo.

    Args:
        config: Repo configuration from ``repos.toml``.
        state: Persisted state from ``StateStore``.
        live: Current git status gathered at check time.
        deps_behind: Names of tracked deps with newer tags available.

    Returns:
        List of human-readable reason strings (may be empty).
    """
    reasons: list[str] = []

    if live.branch and live.branch != "main":
        reasons.append(f"on branch {live.branch}, not main")

    if not live.is_clean:
        reasons.append("uncommitted changes")

    if live.is_behind and not config.auto_merge:
        reasons.append("behind origin/main")

    if live.is_ahead:
        reasons.append("ahead of origin/main (unpushed commits)")

    if state.last_test_passed is False:
        reasons.append("last test run failed")

    if state.last_fetch_at is None:
        reasons.append("never fetched")

    if deps_behind:
        dep_names = ", ".join(deps_behind)
        reasons.append(f"deps behind: {dep_names}")

    return reasons


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def compute_health(
    config: RepoConfig,
    state: RepoState,
    live: LiveRepoStatus,
    deps_behind: list[str] | None = None,
) -> HealthReport:
    """Compute health status for a single repo.

    Evaluation order: RED conditions are checked first (repo missing and
    diverged).  If the repo is not on disk the function returns immediately
    without evaluating remaining conditions.  All YELLOW conditions are
    collected before deriving the final status.

    Args:
        config: Repo configuration from ``repos.toml``.
        state: Persisted state from ``StateStore``.
        live: Current git status gathered at check time.
        deps_behind: Names of tracked deps with newer tags available.
            Pass ``None`` or an empty list when the repo is not a consumer.

    Returns:
        ``HealthReport`` with overall status and list of reasons.
    """
    if not live.repo_exists:
        return HealthReport(status=HealthStatus.RED, reasons=["repo not found on disk"])

    red_reasons: list[str] = []
    if live.has_diverged:
        red_reasons.append("diverged from origin/main")

    yellow_reasons = _collect_yellow_reasons(config, state, live, deps_behind)

    if red_reasons:
        return HealthReport(
            status=HealthStatus.RED,
            reasons=red_reasons + yellow_reasons,
        )

    if yellow_reasons:
        return HealthReport(status=HealthStatus.YELLOW, reasons=yellow_reasons)

    return HealthReport(status=HealthStatus.GREEN)
