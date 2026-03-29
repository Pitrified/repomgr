# Various fixes

## e1

after updating deps, we should install the package again eg `uv sync --all-extras --all-groups` to ensure new git deps are installed,
and only after that we can run the test suite to check everything is working.

### Plan

**File:** `src/repomgr/update.py`, inside `_execute_update()`.

Currently after rewriting `pyproject.toml`, the code calls `uv sync` (no flags).
Change the subprocess call from:
```python
subprocess.run(["uv", "sync"], ...)
```
to:
```python
subprocess.run(["uv", "sync", "--all-extras", "--all-groups"], ...)
```

That is the only change needed. The `shell=False` flag is already correctly set for this call.

---

## e2

for repos marked as `source`, we should check if there are some commits after the last tag, and if so, mark the repo as stale in `status` command

### Plan

Three-step change across `git.py`, `manager.py`, and `health.py`.

**Step 1 - new function in `git.py`:**
Add `commits_after_last_tag(cwd: Path) -> int` that returns the number of commits on HEAD
that are not reachable from the most recent tag. Implementation:
```python
def commits_after_last_tag(cwd: Path) -> int:
    # Get the most recent tag
    result = subprocess.run(
        ["git", "tag", "--sort=-v:refname"],
        cwd=cwd, capture_output=True, text=True, check=True,
    )
    tags = [t for t in result.stdout.splitlines() if t.strip()]
    if not tags:
        return 0  # no tags yet - cannot be stale
    latest_tag = tags[0]
    # Count commits between latest tag and HEAD
    result = subprocess.run(
        ["git", "rev-list", f"{latest_tag}..HEAD", "--count"],
        cwd=cwd, capture_output=True, text=True, check=True,
    )
    return int(result.stdout.strip())
```
Return `0` when there are no tags so repos that have never been tagged are not flagged.

**Step 2 - extend `LiveRepoStatus` and `status_all` in `manager.py`:**
Add a field to `LiveRepoStatus` (in `health.py` or wherever it is defined):
```python
has_unreleased_commits: bool = False
```
In `status_all`, for each repo that has `Role.SOURCE` in its roles, call
`git.commits_after_last_tag(repo.path)` and set
`live.has_unreleased_commits = result > 0`.

**Step 3 - add YELLOW condition in `health.py`:**
```python
if live.has_unreleased_commits:
    warnings.append("unreleased commits since last tag")
```
This produces a YELLOW health status for any source repo with commits not yet tagged.

---

## e3

when test fail while updating this is tracked in the file, but if we manually fix that later, the next `status` call will still show failed tests

### Plan

The root cause: `state.last_test_passed = False` (and `last_update_result = "failed_tests"`)
persist in the JSON state file indefinitely, even after the developer has manually resolved the
situation (e.g., discarded the dep branch, merged it manually, or fixed the tests by hand).

**Detection heuristic:** the dep update flow always leaves the repo on a branch named
`deps/update_<timestamp>` when tests fail (it does NOT merge back to main). Therefore,
if the repo is back on `main` AND the working tree is clean, the user has resolved the
situation manually, and the stale failure record should be cleared.

**Implementation - in `manager.py`'s `status_all`, after collecting `LiveRepoStatus`:**
```python
if (
    state.last_update_result == "failed_tests"
    and live.branch == "main"
    and live.is_clean
):
    state.last_test_passed = None
    state.last_update_result = None
    store.set(state)
```

This auto-clears the stale failure as a side-effect of `repomgr status`. No new command or
manual intervention needed. The write is cheap (one JSON file update per affected repo).

Edge case: if the user is on `main` but the dep branch still exists locally, that is fine -
the detection only looks at the current branch, not at all local branches. If the user switched
back to main without deleting the dep branch it is still safe to clear: `last_test_passed=None`
does not produce a YELLOW warning, and if they later run `update-deps` it will fail the
pre-condition check ("not on main" or "unclean tree") for that branch anyway.
