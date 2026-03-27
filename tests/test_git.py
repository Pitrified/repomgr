"""Tests for the git subprocess layer."""

from pathlib import Path
import subprocess

import pytest

from repomgr.git import FetchResult
from repomgr.git import GitError
from repomgr.git import _run_git
from repomgr.git import checkout
from repomgr.git import clone
from repomgr.git import commit
from repomgr.git import create_branch
from repomgr.git import current_branch
from repomgr.git import delete_branch
from repomgr.git import fast_forward
from repomgr.git import fetch
from repomgr.git import get_main_sha
from repomgr.git import has_diverged
from repomgr.git import is_ahead_of_remote
from repomgr.git import is_behind_remote
from repomgr.git import is_clean
from repomgr.git import list_stale_branches
from repomgr.git import list_tags
from repomgr.git import push
from repomgr.git import repo_exists

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _git(cwd: Path, *args: str) -> str:
    """Run a raw git command and return stdout."""
    return subprocess.run(  # noqa: S603
        ["git", *args],  # noqa: S607
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """Create a minimal local git repo with one commit on main.

    Returns:
        Path to the repository root.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "test@test.com")
    _git(repo, "config", "user.name", "Test")
    (repo / "README.md").write_text("hello", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "init")
    return repo


@pytest.fixture
def git_repo_with_remote(tmp_path: Path) -> tuple[Path, Path]:
    """Create a bare remote with a local clone and return both paths.

    Returns:
        ``(local_repo, bare_remote)`` tuple.
    """
    bare = tmp_path / "bare.git"
    bare.mkdir()
    _git(bare, "init", "--bare", "-b", "main")

    local = tmp_path / "local"
    local.mkdir()
    # Clone from bare into local
    subprocess.run(  # noqa: S603
        ["git", "clone", str(bare), str(local)],  # noqa: S607
        capture_output=True,
        check=True,
    )
    _git(local, "config", "user.email", "test@test.com")
    _git(local, "config", "user.name", "Test")

    # Create initial commit and push so origin/main exists
    (local / "README.md").write_text("hello", encoding="utf-8")
    _git(local, "add", ".")
    _git(local, "commit", "-m", "init")
    _git(local, "push", "origin", "main")

    return local, bare


# ---------------------------------------------------------------------------
# repo_exists
# ---------------------------------------------------------------------------


def test_repo_exists_true(git_repo: Path) -> None:
    """Return True when the directory contains a git repository."""
    assert repo_exists(git_repo) is True


def test_repo_exists_false(tmp_path: Path) -> None:
    """Return False when the directory is not a git repository."""
    empty = tmp_path / "empty"
    empty.mkdir()
    assert repo_exists(empty) is False


# ---------------------------------------------------------------------------
# current_branch
# ---------------------------------------------------------------------------


def test_current_branch(git_repo: Path) -> None:
    """Return 'main' on a freshly initialised repo."""
    assert current_branch(git_repo) == "main"


# ---------------------------------------------------------------------------
# is_clean
# ---------------------------------------------------------------------------


def test_is_clean_on_clean_repo(git_repo: Path) -> None:
    """Return True when the working tree has no uncommitted changes."""
    assert is_clean(git_repo) is True


def test_is_clean_with_untracked(git_repo: Path) -> None:
    """Return False when untracked files are present."""
    (git_repo / "new.txt").write_text("stuff", encoding="utf-8")
    assert is_clean(git_repo) is False


def test_is_clean_with_modified(git_repo: Path) -> None:
    """Return False when a tracked file has been modified."""
    (git_repo / "README.md").write_text("changed", encoding="utf-8")
    assert is_clean(git_repo) is False


# ---------------------------------------------------------------------------
# get_main_sha
# ---------------------------------------------------------------------------


def test_get_main_sha_is_40_chars(git_repo: Path) -> None:
    """Return a 40-character lowercase hex SHA for the main branch."""
    sha = get_main_sha(git_repo)
    assert len(sha) == 40
    assert all(c in "0123456789abcdef" for c in sha)


# ---------------------------------------------------------------------------
# clone
# ---------------------------------------------------------------------------


def test_clone(tmp_path: Path, git_repo: Path) -> None:
    """Clone a local repo into a destination path and verify the working tree."""
    dest = tmp_path / "cloned"
    clone(str(git_repo), dest)
    assert repo_exists(dest)
    assert (dest / "README.md").exists()


# ---------------------------------------------------------------------------
# list_tags
# ---------------------------------------------------------------------------


def test_list_tags_empty(git_repo: Path) -> None:
    """Return an empty list when no tags exist."""
    assert list_tags(git_repo) == []


def test_list_tags_sorted(git_repo: Path) -> None:
    """Return tags in descending version order (newest first)."""
    for tag in ("v1.0.0", "v1.2.0", "v1.1.0"):
        _git(git_repo, "tag", tag)
    tags = list_tags(git_repo)
    assert tags == ["v1.2.0", "v1.1.0", "v1.0.0"]


# ---------------------------------------------------------------------------
# create_branch / checkout / delete_branch
# ---------------------------------------------------------------------------


def test_create_and_checkout_branch(git_repo: Path) -> None:
    """Create a new branch and verify it becomes the current branch."""
    create_branch(git_repo, "feature/x")
    assert current_branch(git_repo) == "feature/x"


def test_checkout_existing_branch(git_repo: Path) -> None:
    """Check out an existing branch by name and verify the active branch."""
    create_branch(git_repo, "feature/x")
    checkout(git_repo, "main")
    assert current_branch(git_repo) == "main"


def test_delete_branch(git_repo: Path) -> None:
    """Delete a local branch and confirm it no longer exists."""
    create_branch(git_repo, "feature/x")
    checkout(git_repo, "main")
    delete_branch(git_repo, "feature/x")
    branches = _git(git_repo, "branch").splitlines()
    assert not any("feature/x" in b for b in branches)


# ---------------------------------------------------------------------------
# commit
# ---------------------------------------------------------------------------


def test_commit(git_repo: Path) -> None:
    """Stage and commit a file, then verify the message appears in the log."""
    p = git_repo / "new.txt"
    p.write_text("data", encoding="utf-8")
    commit(git_repo, "add new.txt", [p])
    log = _git(git_repo, "log", "--oneline")
    assert "add new.txt" in log


# ---------------------------------------------------------------------------
# push and fetch
# ---------------------------------------------------------------------------


def test_push_and_fetch_no_changes(git_repo_with_remote: tuple[Path, Path]) -> None:
    """Return an all-zero FetchResult when the remote has no new data."""
    local, _bare = git_repo_with_remote
    result = fetch(local)
    assert isinstance(result, FetchResult)
    assert result.new_tags == []
    assert result.new_branches == []
    assert result.main_advanced_by == 0
    assert result.new_commit_log == []


def test_fetch_with_new_commits(
    tmp_path: Path, git_repo_with_remote: tuple[Path, Path]
) -> None:
    """Report new commits when origin/main has advanced since last fetch."""
    local, bare = git_repo_with_remote

    # Create a second clone that pushes new commits
    second = tmp_path / "second"
    subprocess.run(  # noqa: S603
        ["git", "clone", str(bare), str(second)],  # noqa: S607
        capture_output=True,
        check=True,
    )
    _git(second, "config", "user.email", "test@test.com")
    _git(second, "config", "user.name", "Test")
    (second / "extra.txt").write_text("new", encoding="utf-8")
    _git(second, "add", ".")
    _git(second, "commit", "-m", "extra commit")
    _git(second, "push", "origin", "main")

    result = fetch(local)
    assert result.main_advanced_by == 1
    assert len(result.new_commit_log) == 1
    assert "extra commit" in result.new_commit_log[0]


def test_fetch_with_new_tags(
    tmp_path: Path, git_repo_with_remote: tuple[Path, Path]
) -> None:
    """Report newly pushed tags in FetchResult.new_tags."""
    local, bare = git_repo_with_remote

    # Second clone pushes a tag
    second = tmp_path / "second"
    subprocess.run(  # noqa: S603
        ["git", "clone", str(bare), str(second)],  # noqa: S607
        capture_output=True,
        check=True,
    )
    _git(second, "config", "user.email", "test@test.com")
    _git(second, "config", "user.name", "Test")
    _git(second, "tag", "v2.0.0")
    _git(second, "push", "origin", "v2.0.0")

    result = fetch(local)
    assert "v2.0.0" in result.new_tags


# ---------------------------------------------------------------------------
# fast_forward
# ---------------------------------------------------------------------------


def test_fast_forward(tmp_path: Path, git_repo_with_remote: tuple[Path, Path]) -> None:
    """Fast-forward local main to match origin after the remote advances."""
    local, bare = git_repo_with_remote

    # Push a new commit via second clone
    second = tmp_path / "second"
    subprocess.run(  # noqa: S603
        ["git", "clone", str(bare), str(second)],  # noqa: S607
        capture_output=True,
        check=True,
    )
    _git(second, "config", "user.email", "test@test.com")
    _git(second, "config", "user.name", "Test")
    (second / "extra.txt").write_text("new", encoding="utf-8")
    _git(second, "add", ".")
    _git(second, "commit", "-m", "extra")
    _git(second, "push", "origin", "main")

    fetch(local)
    fast_forward(local)

    assert (local / "extra.txt").exists()


# ---------------------------------------------------------------------------
# is_behind_remote / is_ahead_of_remote / has_diverged
# ---------------------------------------------------------------------------


def test_is_behind_remote_false_initially(
    git_repo_with_remote: tuple[Path, Path],
) -> None:
    """Return False when local and remote are in sync after a fresh clone."""
    local, _bare = git_repo_with_remote
    assert is_behind_remote(local) is False


def test_is_behind_remote_true_after_remote_commit(
    tmp_path: Path, git_repo_with_remote: tuple[Path, Path]
) -> None:
    """Return True when origin/main has new commits not yet in local main."""
    local, bare = git_repo_with_remote
    second = tmp_path / "second"
    subprocess.run(  # noqa: S603
        ["git", "clone", str(bare), str(second)],  # noqa: S607
        capture_output=True,
        check=True,
    )
    _git(second, "config", "user.email", "test@test.com")
    _git(second, "config", "user.name", "Test")
    (second / "extra.txt").write_text("x", encoding="utf-8")
    _git(second, "add", ".")
    _git(second, "commit", "-m", "remote commit")
    _git(second, "push", "origin", "main")

    fetch(local)
    assert is_behind_remote(local) is True


def test_is_ahead_of_remote(git_repo_with_remote: tuple[Path, Path]) -> None:
    """Return True when local has commits not yet pushed to origin."""
    local, _bare = git_repo_with_remote
    (local / "ahead.txt").write_text("local only", encoding="utf-8")
    commit(local, "local commit", [local / "ahead.txt"])
    assert is_ahead_of_remote(local) is True


def test_has_diverged(tmp_path: Path, git_repo_with_remote: tuple[Path, Path]) -> None:
    """Return True when both local and remote have commits the other lacks."""
    local, bare = git_repo_with_remote

    # Remote gets a new commit
    second = tmp_path / "second"
    subprocess.run(  # noqa: S603
        ["git", "clone", str(bare), str(second)],  # noqa: S607
        capture_output=True,
        check=True,
    )
    _git(second, "config", "user.email", "test@test.com")
    _git(second, "config", "user.name", "Test")
    (second / "remote.txt").write_text("remote", encoding="utf-8")
    _git(second, "add", ".")
    _git(second, "commit", "-m", "remote")
    _git(second, "push", "origin", "main")

    # Local also gets a new commit (not pushed)
    (local / "local.txt").write_text("local", encoding="utf-8")
    commit(local, "local", [local / "local.txt"])

    fetch(local)
    assert has_diverged(local) is True


# ---------------------------------------------------------------------------
# list_stale_branches
# ---------------------------------------------------------------------------


def test_list_stale_branches_empty(git_repo_with_remote: tuple[Path, Path]) -> None:
    """Return an empty list when no stale branches exist."""
    local, _bare = git_repo_with_remote
    assert list_stale_branches(local) == []


def test_list_stale_branches_merged(git_repo: Path) -> None:
    """Report branches that have been fully merged into main as stale."""
    create_branch(git_repo, "feature/done")
    (git_repo / "done.txt").write_text("done", encoding="utf-8")
    commit(git_repo, "done", [git_repo / "done.txt"])
    checkout(git_repo, "main")
    _git(git_repo, "merge", "--ff-only", "feature/done")
    stale = list_stale_branches(git_repo)
    assert "feature/done" in stale


# ---------------------------------------------------------------------------
# GitError
# ---------------------------------------------------------------------------


def test_git_error_raised_on_bad_command(git_repo: Path) -> None:
    """Raise GitError when the git subcommand is invalid."""
    with pytest.raises(GitError) as exc_info:
        _run_git(git_repo, "no-such-subcommand")
    err = exc_info.value
    assert err.returncode != 0
    assert "no-such-subcommand" in " ".join(err.command)


def test_git_error_str_contains_returncode(git_repo: Path) -> None:
    """Include the exit code in the GitError string representation."""
    with pytest.raises(GitError) as exc_info:
        _run_git(git_repo, "checkout", "nonexistent-branch-xyz")
    assert "exit" in str(exc_info.value)


# ---------------------------------------------------------------------------
# push
# ---------------------------------------------------------------------------


def test_push_sends_commit_to_remote(
    git_repo_with_remote: tuple[Path, Path],
) -> None:
    """Push a local commit to origin and verify it appears in the remote log."""
    local, _bare = git_repo_with_remote
    (local / "push_test.txt").write_text("pushed", encoding="utf-8")
    commit(local, "push test commit", [local / "push_test.txt"])
    push(local, "main")

    # Verify via second clone
    result = _git(local, "log", "--oneline", "origin/main")
    assert "push test commit" in result
