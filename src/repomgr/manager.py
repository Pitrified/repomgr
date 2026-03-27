"""Orchestration layer for repomgr operations.

This module ties together git, state, health, deps, and renderer to implement
the main CLI workflows: fetch all repos, clone missing repos, display the
health-status dashboard, and manage stale branches.

Pattern rules:
    All git errors are caught per repo so one failing repo does not abort the
    entire batch.  ``status_all`` is read-only - it never writes state.
    Interactive prompting in ``stale_branches`` is acceptable because it is a
    human-facing flow.
"""

from datetime import UTC
from datetime import datetime

from loguru import logger as lg
import typer

from repomgr import deps as _deps
from repomgr import git
from repomgr.config.repos_config import RepoConfig
from repomgr.config.repos_config import RepomgrTomlConfig
from repomgr.config.repos_config import Role
from repomgr.git import GitError
from repomgr.health import LiveRepoStatus
from repomgr.health import compute_health
from repomgr.renderer import StatusRow
from repomgr.renderer import render_clone_result
from repomgr.renderer import render_fetch_result
from repomgr.renderer import render_stale_branches
from repomgr.renderer import render_status
from repomgr.state import StateStore

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def fetch_all(
    config: RepomgrTomlConfig,
    store: StateStore,
) -> None:
    """Fetch all repos, auto-merge where configured, and display results.

    For each tracked repo the function:

    1. Skips with a warning if the local clone is missing.
    2. Runs ``git fetch`` and updates persisted state.
    3. Fast-forwards local ``main`` when ``auto_merge=True`` and the working
       tree is clean and not diverged.
    4. Renders the fetch result to stdout.
    5. Writes updated state to disk.

    Any ``GitError`` for a single repo is logged and processing continues
    with the next repo.

    Args:
        config: Loaded repos config with all repo definitions.
        store: State store for reading and persisting fetch results.
    """
    for repo in config.repos:
        if not repo.path.exists():
            lg.warning("skipping {} - not on disk", repo.name)
            continue

        try:
            result = git.fetch(repo.path)
            state = store.get(repo.name)
            state.last_fetch_at = datetime.now(tz=UTC)
            state.new_tags_since_last_fetch = result.new_tags
            try:
                state.last_seen_main_sha = git.get_main_sha(repo.path)
            except GitError:
                lg.debug("could not read main SHA for {}", repo.name)

            if (
                repo.auto_merge
                and git.current_branch(repo.path) == "main"
                and git.is_clean(repo.path)
                and not git.has_diverged(repo.path)
            ):
                git.fast_forward(repo.path)
                lg.info("fast-forwarded {}", repo.name)

            render_fetch_result(repo.name, result)
            store.save(state)

        except GitError as e:
            lg.warning("skipping {}: {}", repo.name, e)


def clone_missing(config: RepomgrTomlConfig) -> None:
    """Clone repos that are not yet on disk.

    Existing clones are silently skipped.  Clone failures are rendered
    to stdout and processing continues with the next repo.

    Args:
        config: Loaded repos config with all repo definitions.
    """
    for repo in config.repos:
        if repo.path.exists():
            lg.debug("skipping {} - already on disk", repo.name)
            continue

        try:
            git.clone(repo.remote, repo.path)
            render_clone_result(repo.name, success=True)
        except GitError as e:
            render_clone_result(repo.name, success=False, error=str(e))


def status_all(
    config: RepomgrTomlConfig,
    store: StateStore,
    dep_graph: dict[str, list[str]],  # noqa: ARG001 - reserved for future use
) -> None:
    """Display the health dashboard for all repos.

    This function is read-only - it never modifies persisted state.

    For each tracked repo the function:

    1. Collects a ``LiveRepoStatus`` (cheap git calls) when the clone exists.
    2. Resolves which tracked deps have newer tags (consumer repos only).
    3. Computes a ``HealthReport`` via ``health.compute_health()``.
    4. Assembles a ``StatusRow`` and passes all rows to
       ``renderer.render_status()``.

    Any ``GitError`` for a single repo is logged and that repo is omitted from
    the dashboard rather than aborting the whole run.

    Args:
        config: Loaded repos config with all repo definitions.
        store: State store for reading persisted state.
        dep_graph: Adjacency list of tracked deps.  Reserved for callers that
            want to pre-compute the graph; not currently used internally.
    """
    rows: list[StatusRow] = []

    for repo in config.repos:
        state = store.get(repo.name)

        if not repo.path.exists():
            live = LiveRepoStatus(repo_exists=False)
            health = compute_health(repo, state, live)
            rows.append(
                StatusRow(
                    name=repo.name,
                    health=health,
                    branch="",
                    is_clean=True,
                    is_behind=False,
                    is_ahead=False,
                    state=state,
                )
            )
            continue

        try:
            branch = git.current_branch(repo.path)
            clean = git.is_clean(repo.path)
            behind = git.is_behind_remote(repo.path)
            ahead = git.is_ahead_of_remote(repo.path)
            diverged = behind and ahead

            live = LiveRepoStatus(
                repo_exists=True,
                branch=branch,
                is_clean=clean,
                is_behind=behind,
                is_ahead=ahead,
                has_diverged=diverged,
            )

            deps_behind: list[str] = []
            if Role.CONSUMER in repo.roles:
                deps_behind = _gather_deps_behind(repo, config)

            health = compute_health(repo, state, live, deps_behind)
            rows.append(
                StatusRow(
                    name=repo.name,
                    health=health,
                    branch=branch,
                    is_clean=clean,
                    is_behind=behind,
                    is_ahead=ahead,
                    state=state,
                    deps_behind=deps_behind,
                )
            )

        except GitError as e:
            lg.warning("error reading status for {}: {}", repo.name, e)

    render_status(rows)


def stale_branches(config: RepomgrTomlConfig) -> None:
    """List stale branches across all repos and prompt for deletion.

    For each tracked repo the function:

    1. Skips repos not on disk.
    2. Calls ``git.list_stale_branches()`` to find candidates.
    3. Renders the list and prompts the user to confirm deletion per branch.
    4. Deletes confirmed branches via ``git.delete_branch()``.

    Prompting via ``typer.confirm()`` is intentional - this is an interactive
    human-facing operation.

    Args:
        config: Loaded repos config with all repo definitions.
    """
    for repo in config.repos:
        if not repo.path.exists():
            continue

        try:
            branches = git.list_stale_branches(repo.path)
        except GitError as e:
            lg.warning("could not list branches for {}: {}", repo.name, e)
            continue

        if not branches:
            continue

        render_stale_branches(repo.name, branches)

        for branch in branches:
            confirmed = typer.confirm(
                f"Delete branch '{branch}' from {repo.name}?",
                default=False,
            )
            if confirmed:
                try:
                    git.delete_branch(repo.path, branch)
                    lg.info("deleted branch {} from {}", branch, repo.name)
                except GitError as e:
                    lg.warning("could not delete {}: {}", branch, e)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _gather_deps_behind(
    repo: RepoConfig,
    config: RepomgrTomlConfig,
) -> list[str]:
    """Return names of tracked deps with a newer tag available.

    Args:
        repo: Config for the consumer repo being evaluated.
        config: Full repos config used to look up source repo paths.

    Returns:
        List of dep repo names that have a newer tag than currently pinned.
        Returns an empty list if ``pyproject.toml`` is absent or unreadable.
    """
    pyproject = repo.path / "pyproject.toml"
    if not pyproject.exists():
        return []

    try:
        git_deps = _deps.parse_git_deps(pyproject, config.repos_by_name)
        _deps.resolve_latest_tags(git_deps, config.repos_by_name)
    except Exception:  # noqa: BLE001
        lg.warning("could not resolve deps for {}", repo.name)
        return []

    return [d.repo_name for d in git_deps if d.needs_update]
