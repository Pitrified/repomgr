# Fixes

## Overview

running

```bash
(repomgr) pmn@pmn-G7:~/repos/repomgr (main)$ uv run repomgr status --config ~/repos/linux-box-cloudflare/configs/repomgr/repos.toml
```

to have actual data available

## e1: last fetch

last fetch column is `never` for all repos, which sounds weird as we are currently developing all of them

### Root cause

`repomgr status` loads `last_fetch_at` from `repos.state.json`, which is resolved relative to the config file (i.e. `~/repos/linux-box-cloudflare/configs/repomgr/repos.state.json`). That file does **not exist** - it is only created when `repomgr fetch` is run with this specific config. Any git fetches done from VS Code, the CLI, or any other tool outside of repomgr are invisible to the state file entirely.

### Proposed fix

In `manager.py`'s `collect_status()` (or wherever `RepoState` is assembled for the status row), fall back to reading the mtime of each repo's `.git/FETCH_HEAD` file when `state.last_fetch_at is None`. Git itself updates that file every time any `git fetch` runs, regardless of who triggered it.

```python
from datetime import UTC, datetime
from pathlib import Path

def _last_fetch_time(repo_path: Path, state: RepoState) -> datetime | None:
    if state.last_fetch_at is not None:
        return state.last_fetch_at
    fetch_head = repo_path / ".git" / "FETCH_HEAD"
    if fetch_head.exists():
        return datetime.fromtimestamp(fetch_head.stat().st_mtime, tz=UTC)
    return None
```

Pass the result into `StatusRow` instead of `state` directly, or add it as a separate field alongside `state`. The renderer's `_fetch_label()` already handles `None` gracefully.

No state-file write is needed: this is purely a read-time enrichment.

**e1 - last fetch** (manager.py): Added `_enrich_fetch_time()` helper that reads FETCH_HEAD mtime as a fallback when `state.last_fetch_at` is `None`. Called in `status_all()` before the `StatusRow` is built.

---

## e2: tracked git deps

all repos show `0` tracked git deps, which is also wrong - at least `media-downloader` should show 2 tracked deps (`llm-core` and `fastapi-tools`)
check the regex, add more comprehensive test cases for it, looking at real `pyproject.toml` files from the repos

### Root cause - three compounding bugs in `deps.py`

**Bug A: wrong TOML section read**

`parse_git_deps` reads only `project.dependencies`:

```python
dep_lines: list[str] = raw.get("project", {}).get("dependencies", [])
```

But in `media-downloader` (and other repos) every git dep lives under `project.optional-dependencies`, which is a dict of group-name -> list. For example:

```toml
[project.optional-dependencies]
webapp = [
    "fastapi-tools @ git+https://github.com/Pitrified/fastapi-tools@v0.1.0",
]
llm-core-base = [
    "llm-core @ git+https://github.com/Pitrified/llm-core@v0.1.0",
]
```

`project.dependencies` contains only plain PyPI deps. Result: parse returns `[]` for every repo.

**Fix A:** Flatten all optional-dependency groups and append to the dep lines:

```python
opt_deps: dict[str, list[str]] = raw.get("project", {}).get("optional-dependencies", {})
for group_lines in opt_deps.values():
    dep_lines.extend(group_lines)
```

---

**Bug B: `.git` suffix not present in actual URLs**

The regex requires a literal `.git` before the `@tag`:

```python
r"/(?P<repo>[\w.-]+)"
r"\.git@"          # ← mandatory .git
r"(?P<tag>[\w.+-]+)"
```

Actual URLs in the repos:

```
git+https://github.com/Pitrified/llm-core@v0.1.0
                                          ↑ no .git
```

The `.git` suffix is never present, so every line is rejected outright.

**Fix B:** Make `.git` optional:

```python
r"/(?P<repo>[\w.-]+)"
r"(?:\.git)?@"     # ← optional .git
r"(?P<tag>[\w.+-]+)"
```

---

**Bug C: hyphens not allowed in the extras character class**

The extras group uses `[\w,]+`, which excludes `-`. A dep like:

```
llm-core[faster-whisper] @ git+...
```

fails to match the extras `[faster-whisper]` because of the hyphen. Since extras is optional (`?`), the regex backtracks and tries matching `\s*@\s*git\+` starting at `[faster-whisper]...`, which also fails. The whole line is rejected.

**Fix C:** Add `-` to the extras character class:

```python
r"(?P<extras>\[[\w,-]+\])?"   # ← hyphen added
```

---

### Combined fix (all three)

```python
_GIT_DEP_PATTERN = re.compile(
    r"^(?P<name>[\w-]+)"
    r"(?P<extras>\[[\w,-]+\])?"   # hyphen allowed in extras
    r"\s*@\s*git\+"
    r"(?:ssh://git@|https://)"
    r"[\w.-]+"                    # host
    r"/[\w.-]+"                   # owner
    r"/(?P<repo>[\w.-]+)"
    r"(?:\.git)?@"                # .git suffix is optional
    r"(?P<tag>[\w.+-]+)"
    r"\s*$",
    re.ASCII,
)
```

And in `parse_git_deps`:

```python
raw = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
project = raw.get("project", {})
dep_lines: list[str] = list(project.get("dependencies", []))
opt_deps: dict[str, list[str]] = project.get("optional-dependencies", {})
for group_lines in opt_deps.values():
    dep_lines.extend(group_lines)
```

### Test cases to add

Add tests in `tests/test_deps.py` covering:

- dep in `project.dependencies` with no `.git` suffix (Bug B)
- dep in `project.optional-dependencies` (Bug A)
- dep with extras containing a hyphen, e.g. `[faster-whisper]` (Bug C)
- dep with extras containing no hyphen, e.g. `[whisper]`
- dep with no extras
- dep pinned on a `.git`-suffixed URL (should still work after Bug B fix)
- non-git PyPI dep (must be silently skipped)
- git dep pointing to an untracked repo (must be silently skipped)

Use `media-downloader`'s actual `pyproject.toml` as the reference fixture.

**e2 - tracked git deps** (deps.py):
- **Bug A**: `parse_git_deps` now also flattens all `project.optional-dependencies` groups into the dep lines list.
- **Bug B**: `_GIT_DEP_PATTERN` regex now uses `(?:\.git)?@` - the .git suffix is optional.
- **Bug C**: Extras char class changed from `[\w,]+` to `[\w,-]+` - hyphens (e.g. `[faster-whisper]`) are now accepted.
