"""Pure subprocess layer for all git operations.

Every function in this module takes ``cwd: Path`` as its first argument and
delegates directly to ``git`` via ``subprocess.run``.  There is no business
logic, no config objects, and no state here.

Pattern rules:
    All subprocess calls go through ``_run_git()``.  Shell is never used
    (``shell=True`` is never passed) to avoid injection risks.  A ``GitError``
    is raised for any non-zero exit code.
"""

from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
import subprocess

from loguru import logger as lg

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class GitError(Exception):
    """Raised when a git subprocess exits with a non-zero return code.

    Attributes:
        command: The argument list that was executed.
        stderr: Captured standard error from the process.
        returncode: Exit code returned by the process.
    """

    def __init__(self, command: list[str], stderr: str, returncode: int) -> None:
        """Initialise GitError with the failing command details."""
        self.command = command
        self.stderr = stderr
        self.returncode = returncode
        super().__init__(
            f"git command failed (exit {returncode}): {' '.join(command)}\n{stderr}"
        )


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class FetchResult:
    """Outcome of a single ``git fetch`` run.

    Attributes:
        new_tags:
            Tags that did not exist locally before the fetch.
        new_branches:
            Remote tracking branches added during the fetch.
        main_advanced_by:
            Number of new commits on ``origin/main`` since the last fetch.
        new_commit_log:
            Short one-line log entries for those new commits, oldest first.
    """

    new_tags: list[str] = field(default_factory=list)
    new_branches: list[str] = field(default_factory=list)
    main_advanced_by: int = 0
    new_commit_log: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Private helper
# ---------------------------------------------------------------------------


def _run_git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run a git command in *cwd* and return the completed process.

    Args:
        cwd: Working directory for the git command.
        *args: Arguments appended after ``git``.

    Returns:
        Completed process with captured stdout and stderr.

    Raises:
        GitError: If the process exits with a non-zero return code.
    """
    cmd = ["git", *args]
    lg.debug("git {}", " ".join(args))
    result = subprocess.run(  # noqa: S603
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise GitError(cmd, result.stderr, result.returncode)
    return result


# ---------------------------------------------------------------------------
# Repository inspection
# ---------------------------------------------------------------------------


def current_branch(cwd: Path) -> str:
    """Return the name of the currently checked-out branch.

    Args:
        cwd: Root of the git repository.

    Returns:
        Branch name as a string.

    Raises:
        GitError: If the directory is not a git repository.
    """
    return _run_git(cwd, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()


def is_clean(cwd: Path) -> bool:
    """Return ``True`` if the working tree has no uncommitted changes.

    Args:
        cwd: Root of the git repository.

    Returns:
        ``True`` when the index and working tree are clean.

    Raises:
        GitError: If the directory is not a git repository.
    """
    result = _run_git(cwd, "status", "--porcelain")
    return result.stdout.strip() == ""


def is_behind_remote(cwd: Path, branch: str = "main") -> bool:
    """Return ``True`` if the local branch is behind its remote tracking branch.

    Runs ``git fetch --dry-run`` is NOT called here; callers should have
    already fetched.  This compares ``<branch>`` against
    ``origin/<branch>`` using ``git rev-list``.

    Args:
        cwd: Root of the git repository.
        branch: Branch name to check (default ``"main"``).

    Returns:
        ``True`` if there are commits on the remote not yet on the local branch.

    Raises:
        GitError: If the directory is not a git repository or refs are missing.
    """
    result = _run_git(cwd, "rev-list", "--count", f"{branch}..origin/{branch}")
    return int(result.stdout.strip()) > 0


def is_ahead_of_remote(cwd: Path, branch: str = "main") -> bool:
    """Return ``True`` if the local branch has commits not on the remote.

    Args:
        cwd: Root of the git repository.
        branch: Branch name to check (default ``"main"``).

    Returns:
        ``True`` if there are local commits not yet pushed to the remote.

    Raises:
        GitError: If the directory is not a git repository or refs are missing.
    """
    result = _run_git(cwd, "rev-list", "--count", f"origin/{branch}..{branch}")
    return int(result.stdout.strip()) > 0


def has_diverged(cwd: Path, branch: str = "main") -> bool:
    """Return ``True`` if the local and remote branches have diverged.

    A diverged state means both ``is_behind_remote`` and
    ``is_ahead_of_remote`` are true simultaneously.

    Args:
        cwd: Root of the git repository.
        branch: Branch name to check (default ``"main"``).

    Returns:
        ``True`` if both branches have commits the other does not have.

    Raises:
        GitError: If the directory is not a git repository or refs are missing.
    """
    return is_behind_remote(cwd, branch) and is_ahead_of_remote(cwd, branch)


def get_main_sha(cwd: Path) -> str:
    """Return the full SHA of the current tip of the ``main`` branch.

    Args:
        cwd: Root of the git repository.

    Returns:
        40-character hex SHA string.

    Raises:
        GitError: If ``main`` does not exist.
    """
    return _run_git(cwd, "rev-parse", "main").stdout.strip()


def repo_exists(cwd: Path) -> bool:
    """Return ``True`` if *cwd* contains a valid git repository.

    Args:
        cwd: Directory to check.

    Returns:
        ``True`` when the directory is inside a git working tree.
    """
    try:
        _run_git(cwd, "rev-parse", "--git-dir")
    except (GitError, FileNotFoundError):
        return False
    return True


# ---------------------------------------------------------------------------
# Fetch and merge
# ---------------------------------------------------------------------------


def fetch(cwd: Path) -> FetchResult:
    """Fetch from all remotes and compute what changed.

    Steps:

    1. Record pre-fetch state (tags, remote tracking branches, main SHA).
    2. Run ``git fetch --tags --prune``.
    3. Record post-fetch state.
    4. Diff both snapshots into a ``FetchResult``.
    5. Collect the one-line log for any new commits on ``origin/main``.

    Args:
        cwd: Root of the git repository.

    Returns:
        ``FetchResult`` describing what arrived in this fetch.

    Raises:
        GitError: If the fetch fails.
    """
    pre_tags = set(list_tags(cwd))
    pre_branches = set(_list_remote_tracking_branches(cwd))

    # Capture the main SHA before fetching.  If the ref does not yet exist
    # (e.g. empty repo), treat it as None.
    try:
        pre_main_sha = _run_git(cwd, "rev-parse", "origin/main").stdout.strip()
    except GitError:
        pre_main_sha = None

    _run_git(cwd, "fetch", "--tags", "--prune", "origin")

    post_tags = set(list_tags(cwd))
    post_branches = set(_list_remote_tracking_branches(cwd))

    try:
        post_main_sha = _run_git(cwd, "rev-parse", "origin/main").stdout.strip()
    except GitError:
        post_main_sha = None

    new_tags = sorted(post_tags - pre_tags)
    new_branches = sorted(post_branches - pre_branches)

    # Compute how far main advanced and grab the commit log.
    main_advanced_by = 0
    new_commit_log: list[str] = []
    if pre_main_sha and post_main_sha and pre_main_sha != post_main_sha:
        log_result = _run_git(
            cwd,
            "log",
            "--oneline",
            f"{pre_main_sha}..{post_main_sha}",
        )
        new_commit_log = [
            line for line in log_result.stdout.splitlines() if line.strip()
        ]
        main_advanced_by = len(new_commit_log)

    return FetchResult(
        new_tags=new_tags,
        new_branches=new_branches,
        main_advanced_by=main_advanced_by,
        new_commit_log=new_commit_log,
    )


def fast_forward(cwd: Path, branch: str = "main") -> None:
    """Fast-forward a local branch to its remote tracking branch.

    Args:
        cwd: Root of the git repository.
        branch: Branch to update (default ``"main"``).

    Raises:
        GitError: If the current branch is not *branch*, or a fast-forward
            is not possible.
    """
    _run_git(cwd, "merge", "--ff-only", f"origin/{branch}")


def merge_ff_only(cwd: Path, ref: str) -> None:
    """Merge *ref* into the current branch using fast-forward only.

    Args:
        cwd: Root of the git repository.
        ref: The ref (branch name, SHA, or tag) to merge.

    Raises:
        GitError: If a fast-forward merge is not possible.
    """
    _run_git(cwd, "merge", "--ff-only", ref)


# ---------------------------------------------------------------------------
# Clone
# ---------------------------------------------------------------------------


def clone(remote: str, dest: Path) -> None:
    """Clone a remote repository to *dest*.

    Args:
        remote: Remote URL (SSH or HTTPS).
        dest: Destination path.  The parent directory must exist.

    Raises:
        GitError: If the clone fails.
    """
    _run_git(dest.parent, "clone", remote, str(dest))


# ---------------------------------------------------------------------------
# Tags
# ---------------------------------------------------------------------------


def list_tags(cwd: Path) -> list[str]:
    """Return all tags, sorted by version descending (newest first).

    Args:
        cwd: Root of the git repository.

    Returns:
        List of tag strings in descending version order.

    Raises:
        GitError: If the directory is not a git repository.
    """
    result = _run_git(cwd, "tag", "--sort=-v:refname")
    return [t for t in result.stdout.splitlines() if t.strip()]


# ---------------------------------------------------------------------------
# Branches
# ---------------------------------------------------------------------------


def list_stale_branches(cwd: Path) -> list[str]:
    """Return local branches that are safe to delete.

    A branch is considered stale if:

    - It has been merged into ``main`` (``git branch --merged main``), or
    - Its remote tracking branch is gone (``git branch -vv`` shows
      ``[origin/<name>: gone]``).

    The ``main`` branch itself is never included.

    Args:
        cwd: Root of the git repository.

    Returns:
        Sorted list of stale local branch names.

    Raises:
        GitError: If the directory is not a git repository.
    """
    stale: set[str] = set()

    # Merged into main
    merged_result = _run_git(cwd, "branch", "--merged", "main")
    for line in merged_result.stdout.splitlines():
        name = line.strip().lstrip("* ")
        if name and name != "main":
            stale.add(name)

    # Remote tracking branch gone
    vv_result = _run_git(cwd, "branch", "-vv")
    for line in vv_result.stdout.splitlines():
        stripped = line.strip()
        if ": gone]" in stripped:
            # Branch name is the first token (strip leading "* " for current)
            name = stripped.lstrip("* ").split()[0]
            if name != "main":
                stale.add(name)

    return sorted(stale)


def create_branch(cwd: Path, name: str) -> None:
    """Create a new branch at the current HEAD and check it out.

    Args:
        cwd: Root of the git repository.
        name: Name of the new branch.

    Raises:
        GitError: If the branch already exists.
    """
    _run_git(cwd, "checkout", "-b", name)


def checkout(cwd: Path, ref: str) -> None:
    """Check out an existing branch or ref.

    Args:
        cwd: Root of the git repository.
        ref: Branch name, tag, or SHA to check out.

    Raises:
        GitError: If the ref does not exist.
    """
    _run_git(cwd, "checkout", ref)


def delete_branch(cwd: Path, branch: str) -> None:
    """Delete a local branch.

    Args:
        cwd: Root of the git repository.
        branch: Local branch name to delete.

    Raises:
        GitError: If the branch does not exist or is not fully merged.
    """
    _run_git(cwd, "branch", "-d", branch)


def delete_remote_branch(cwd: Path, branch: str) -> None:
    """Delete a branch on the ``origin`` remote.

    Args:
        cwd: Root of the git repository.
        branch: Remote branch name to delete.

    Raises:
        GitError: If the push fails.
    """
    _run_git(cwd, "push", "origin", "--delete", branch)


# ---------------------------------------------------------------------------
# Commit and push
# ---------------------------------------------------------------------------


def commit(cwd: Path, message: str, paths: list[Path]) -> None:
    """Stage specific paths and create a commit.

    Args:
        cwd: Root of the git repository.
        message: Commit message.
        paths: Files to stage.  Only these paths are added.

    Raises:
        GitError: If staging or committing fails.
    """
    _run_git(cwd, "add", "--", *[str(p) for p in paths])
    _run_git(cwd, "commit", "-m", message)


def push(cwd: Path, branch: str) -> None:
    """Push a local branch to ``origin``.

    Args:
        cwd: Root of the git repository.
        branch: Branch name to push.

    Raises:
        GitError: If the push fails (e.g. not fast-forward, no access).
    """
    _run_git(cwd, "push", "origin", branch)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _list_remote_tracking_branches(cwd: Path) -> list[str]:
    """Return all remote tracking branch names (e.g. ``origin/main``).

    Args:
        cwd: Root of the git repository.

    Returns:
        List of ref names.
    """
    result = _run_git(cwd, "branch", "-r")
    branches = []
    for line in result.stdout.splitlines():
        name = line.strip()
        if name and "->" not in name:
            branches.append(name)
    return branches
