"""Dependency update flow for consumer repos.

For each consumer repo, this module detects outdated git-sourced dependencies,
creates an update branch, edits ``pyproject.toml``, optionally runs tests, and
either merges the result to ``main`` or leaves the branch for manual review.

This absorbs and supersedes the standalone ``update_git_deps.py`` script.

Pattern rules:
    All git operations go through ``repomgr.git``.  Dep parsing and in-place
    editing use ``repomgr.deps``.  Terminal output goes through
    ``repomgr.renderer``.  The test command is executed with ``shell=True``
    because it is a freeform string from ``repos.toml``.  The ``uv sync``
    helper uses ``shell=False``.  No ``subprocess`` calls appear outside this
    module.
"""

from datetime import UTC
from datetime import datetime
from pathlib import Path
import subprocess

from loguru import logger as lg

from repomgr import deps as deps_mod
from repomgr import git
from repomgr.config.repos_config import RepoConfig
from repomgr.config.repos_config import RepomgrTomlConfig
from repomgr.config.repos_config import Role
from repomgr.deps import GitDep
from repomgr.renderer import UpdateResult
from repomgr.renderer import render_update_summary
from repomgr.state import StateStore

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class UnknownRepoError(Exception):
    """Raised when the ``repo_name`` argument is not present in the config."""


# ---------------------------------------------------------------------------
# Private helpers - subprocess
# ---------------------------------------------------------------------------


def _branch_name() -> str:
    """Return a timestamped deps-update branch name.

    Returns:
        Branch name in the form ``deps/update_YYYYMMDD_HHMMSS``.
    """
    return f"deps/update_{datetime.now(tz=UTC).strftime('%Y%m%d_%H%M%S')}"


def _run_uv_sync(cwd: Path) -> bool:
    """Run ``uv sync`` in *cwd* to regenerate the lock file.

    Args:
        cwd: Repository root.

    Returns:
        ``True`` when the command exits with code zero.
    """
    result = subprocess.run(
        ["uv", "sync", "--all-extras", "--all-groups"],  # noqa: S607
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        lg.warning("uv sync failed in {}: {}", cwd, result.stderr)
    return result.returncode == 0


def _run_tests(cwd: Path, cmd: str) -> bool:
    """Run the test command string in *cwd*.

    The command is run with ``shell=True`` because it is a freeform string
    from ``repos.toml``, which is a trusted local config file.

    Args:
        cwd: Repository root.
        cmd: Shell command string, e.g. ``"uv run pytest"``.

    Returns:
        ``True`` when the command exits with code zero.
    """
    result = subprocess.run(  # noqa: S602
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        shell=True,
        check=False,
    )
    if result.returncode != 0:
        lg.warning("tests failed in {}\n{}", cwd, result.stderr[-2000:])
    return result.returncode == 0


def _commit_changes(
    cwd: Path,
    dep_names: list[str],
    pyproject_path: Path,
    lockfile: Path,
) -> None:
    """Stage and commit ``pyproject.toml`` and ``uv.lock``.

    Args:
        cwd: Repository root.
        dep_names: Names of updated dependencies (used in commit message).
        pyproject_path: Path to the updated ``pyproject.toml``.
        lockfile: Path to the lock file (included only if it exists).
    """
    paths: list[Path] = [pyproject_path]
    if lockfile.exists():
        paths.append(lockfile)
    msg = f"deps: update {', '.join(dep_names)}"
    git.commit(cwd, msg, paths)


# ---------------------------------------------------------------------------
# Private helpers - pre-checks
# ---------------------------------------------------------------------------


def _check_git_state(cwd: Path, name: str) -> str | None:
    """Check branch, cleanliness, and remote tracking state.

    Called inside a ``try`` block so ``GitError`` from ``current_branch`` or
    ``is_clean`` is caught by the caller.  A ``GitError`` from
    ``is_behind_remote`` is treated as "unknown, proceed".

    Args:
        cwd: Repository root.
        name: Short repo name (used in log messages only).

    Returns:
        Skip reason string or ``None`` if all checks pass.

    Raises:
        GitError: If the git commands for branch or clean-state fail.
    """
    branch = git.current_branch(cwd)
    if branch != "main":
        return f"not on main branch (currently on '{branch}')"
    if not git.is_clean(cwd):
        return "working tree is dirty"
    try:
        behind = git.is_behind_remote(cwd)
    except git.GitError:
        lg.debug("could not check remote state for '{}', proceeding", name)
        behind = False
    if behind:
        return "local main is behind remote, run fetch first"
    return None


def _check_preconditions(repo_config: RepoConfig) -> str | None:
    """Run all pre-update checks for one repo.

    Checks (in order):

    1. Local clone exists on disk.
    2. ``pyproject.toml`` is present.
    3. Repo is a valid git repository on the ``main`` branch with a clean
       working tree and not behind the remote.

    Args:
        repo_config: Config for the repo to check.

    Returns:
        Failure reason string when a check fails, ``None`` when all pass.
    """
    cwd = repo_config.path
    if not cwd.exists():
        return "path does not exist on disk"
    if not (cwd / "pyproject.toml").exists():
        return "pyproject.toml not found"
    try:
        return _check_git_state(cwd, repo_config.name)
    except git.GitError:
        return "not a git repository"


# ---------------------------------------------------------------------------
# Private helpers - dep detection
# ---------------------------------------------------------------------------


def _find_outdated_deps(
    repo_config: RepoConfig,
    config: RepomgrTomlConfig,
) -> list[GitDep]:
    """Parse and resolve git deps, returning only those that need updating.

    Args:
        repo_config: Consumer repo config.
        config: Full loaded config (provides paths of all tracked repos).

    Returns:
        List of ``GitDep`` instances whose ``needs_update`` flag is ``True``.
    """
    pyproject_path = repo_config.path / "pyproject.toml"
    git_deps = deps_mod.parse_git_deps(pyproject_path, config.repos_by_name)
    deps_mod.resolve_latest_tags(git_deps, config.repos_by_name)
    return [d for d in git_deps if d.needs_update]


# ---------------------------------------------------------------------------
# Private helpers - execution
# ---------------------------------------------------------------------------


def _execute_update(
    repo_config: RepoConfig,
    outdated: list[GitDep],
    *,
    no_tests: bool,
) -> tuple[str, datetime | None, bool | None]:
    """Create a branch, apply dep updates, run tests, and merge or leave.

    Args:
        repo_config: The consumer repo to update.
        outdated: Deps that need a version bump.
        no_tests: When ``True``, skip the test suite and merge unconditionally.

    Returns:
        A 3-tuple of ``(outcome, test_time, tests_passed)``:

        - *outcome* is ``"updated"`` or ``"failed_tests"``.
        - *test_time* is the datetime after tests finished, or ``None`` if
          tests were skipped.
        - *tests_passed* is ``True``/``False`` when tests ran, ``None``
          otherwise.
    """
    cwd = repo_config.path
    branch_name = _branch_name()
    git.create_branch(cwd, branch_name)
    lg.info("{}: created branch {}", repo_config.name, branch_name)

    pyproject_path = cwd / "pyproject.toml"
    for dep in outdated:
        deps_mod.update_pyproject(pyproject_path, dep)
        lg.info(
            "{}: bumped {} {} -> {}",
            repo_config.name,
            dep.name,
            dep.current_tag,
            dep.latest_tag,
        )

    lockfile = cwd / "uv.lock"
    _run_uv_sync(cwd)

    test_time: datetime | None = None
    tests_passed: bool | None = None

    if not no_tests:
        tests_passed = _run_tests(cwd, repo_config.test_cmd)
        test_time = datetime.now(tz=UTC)

    dep_names = [d.name for d in outdated]
    _commit_changes(cwd, dep_names, pyproject_path, lockfile)

    should_merge = no_tests or tests_passed is True
    if should_merge:
        git.checkout(cwd, "main")
        git.merge_ff_only(cwd, branch_name)
        git.delete_branch(cwd, branch_name)
        git.push(cwd, "main")
        lg.info("{}: merged and pushed deps update", repo_config.name)
        return "updated", test_time, tests_passed

    lg.warning(
        "{}: tests failed, leaving on branch {}",
        repo_config.name,
        branch_name,
    )
    return "failed_tests", test_time, tests_passed


# ---------------------------------------------------------------------------
# Private helpers - state recording
# ---------------------------------------------------------------------------


def _record_state(
    store: StateStore,
    name: str,
    now: datetime,
    outcome: str,
    *,
    test_time: datetime | None = None,
    tests_passed: bool | None = None,
) -> None:
    """Write outcome fields back to the state store.

    Args:
        store: Persistence layer.
        name: Repo short name.
        now: Timestamp to record as ``last_update_run_at``.
        outcome: One of ``"updated"``, ``"failed_tests"``,
            ``"no_updates"``, or ``"skipped"``.
        test_time: When the test run completed; ``None`` if no tests ran.
        tests_passed: Test result; ``None`` if no tests ran.
    """
    state = store.get(name)
    state.last_update_run_at = now
    state.last_update_result = outcome
    if test_time is not None:
        state.last_test_run_at = test_time
        state.last_test_passed = tests_passed
    store.save(state)


# ---------------------------------------------------------------------------
# Single-repo orchestration
# ---------------------------------------------------------------------------


def _update_repo(
    repo_config: RepoConfig,
    config: RepomgrTomlConfig,
    store: StateStore,
    *,
    dry_run: bool,
    no_tests: bool,
) -> UpdateResult:
    """Run the full update flow for one consumer repo.

    Args:
        repo_config: Config for the repo to update.
        config: Full loaded config (used to look up dep paths).
        store: State persistence.
        dry_run: Log what would change without making any writes.
        no_tests: Skip the test suite and merge unconditionally.

    Returns:
        ``UpdateResult`` describing the outcome.
    """
    name = repo_config.name
    now = datetime.now(tz=UTC)

    skip_reason = _check_preconditions(repo_config)
    if skip_reason:
        _record_state(store, name, now, "skipped")
        return UpdateResult(name=name, outcome="skipped", error=skip_reason)

    outdated = _find_outdated_deps(repo_config, config)
    dep_names = [d.name for d in outdated]

    if not outdated:
        _record_state(store, name, now, "no_updates")
        return UpdateResult(name=name, outcome="no_updates")

    if dry_run:
        for dep in outdated:
            lg.info(
                "[dry-run] {} would update {} {} -> {}",
                name,
                dep.name,
                dep.current_tag,
                dep.latest_tag,
            )
        return UpdateResult(name=name, outcome="updated", updated_deps=dep_names)

    outcome, test_time, tests_passed = _execute_update(
        repo_config,
        outdated,
        no_tests=no_tests,
    )
    _record_state(
        store, name, now, outcome, test_time=test_time, tests_passed=tests_passed
    )
    return UpdateResult(name=name, outcome=outcome, updated_deps=dep_names)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def update_deps(
    config: RepomgrTomlConfig,
    store: StateStore,
    dep_graph: dict[str, list[str]],
    *,
    dry_run: bool = False,
    no_tests: bool = False,
    repo_name: str | None = None,
) -> None:
    """Run the dependency update flow across consumer repos.

    Repos are processed in topological order (source repos first, deepest
    consumers last) so that when a multi-level dependency chain is present,
    upstream repos are updated before the repos that depend on them.

    For each consumer repo the function:

    1. Validates pre-conditions (on main, clean tree, not behind remote).
    2. Parses git deps and resolves the latest available tag.
    3. Skips repos with nothing to update.
    4. In ``dry_run`` mode, logs intended changes without writing anything.
    5. Creates a ``deps/update_<timestamp>`` branch.
    6. Rewrites the pinned tags in ``pyproject.toml`` and runs ``uv sync``.
    7. Runs ``repo.test_cmd`` unless ``no_tests`` is set.
    8. On success (or ``no_tests``): commits, merges to ``main``, pushes.
    9. On test failure: commits the WIP state and leaves the branch checked out.
    10. Persists the outcome to the state store.

    A summary table is rendered after all repos are processed.

    Args:
        config: Loaded repos config.
        store: State persistence.
        dep_graph: Adjacency list ``{repo_name: [dep_names]}`` as returned
            by ``deps.build_dep_graph``.
        dry_run: Log what would change without making any writes.
        no_tests: Skip the test suite and merge unconditionally.
        repo_name: When given, only process this single repo by name.

    Raises:
        UnknownRepoError: If *repo_name* is not present in the config.
    """
    order = deps_mod.topological_order(dep_graph)

    if repo_name is not None:
        if repo_name not in config.repos_by_name:
            msg = f"unknown repo: {repo_name!r}"
            raise UnknownRepoError(msg)
        order = [n for n in order if n == repo_name]

    results: list[UpdateResult] = []
    for name in order:
        repo_conf = config.repos_by_name.get(name)
        if repo_conf is None:
            continue
        if Role.CONSUMER not in repo_conf.roles:
            continue
        result = _update_repo(
            repo_conf,
            config,
            store,
            dry_run=dry_run,
            no_tests=no_tests,
        )
        results.append(result)

    if results:
        render_update_summary(results)
