# User Guide

**repomgr** tracks a fleet of local Python repos, keeps them up to date, and automatically bumps git-sourced dependencies across consumers.

---

## Prerequisites

- Linux, Python 3.14+
- [uv](https://docs.astral.sh/uv/) package manager

---

## Setup

### 1. Install

```bash
uv sync
```

### 2. Create repos.toml

Copy the annotated example and edit it:

```bash
cp repos.toml.example repos.toml
```

The file has two sections: a global `[settings]` block and one `[[repo]]` entry per tracked repo.

```toml
[settings]
base_path        = "~/repos"
default_test_cmd = "uv run pytest"
state_file       = "./repos.state.json"

[[repo]]
name   = "my-lib"
remote = "git@github.com:you/my-lib.git"
roles  = ["source"]
auto_merge = true

[[repo]]
name   = "my-app"
remote = "git@github.com:you/my-app.git"
roles  = ["consumer"]
```

See [repos.toml.example](https://github.com/Pitrified/repomgr/blob/main/repos.toml.example) for a fully annotated reference.

### 3. Clone any repos not yet on disk

```bash
repomgr clone-missing
```

### 4. Verify the dashboard

```bash
repomgr status
```

---

## repos.toml reference

### [settings]

| Key | Default | Description |
|-----|---------|-------------|
| `base_path` | `~/repos` | Root directory for clones. Each repo lands at `base_path/<name>` unless overridden. |
| `default_test_cmd` | `uv run pytest` | Test command used when a repo does not define `test_cmd`. |
| `state_file` | `./repos.state.json` | Path to the generated state file. Relative paths are resolved from the directory containing `repos.toml`. |

### [[repo]]

| Key | Required | Description |
|-----|----------|-------------|
| `name` | yes | Unique short identifier - used in commands and the dep graph. |
| `remote` | yes | Git remote URL (SSH or HTTPS). |
| `roles` | yes | `["source"]`, `["consumer"]`, or `["source", "consumer"]`. |
| `auto_merge` | no | `true` to fast-forward merge and push after a successful dep update. Default `false`. |
| `path` | no | Explicit clone location. Defaults to `base_path/name`. |
| `test_cmd` | no | Per-repo test command. Defaults to `settings.default_test_cmd`. |

**Roles** control how repomgr treats each repo:

- `source` - the repo produces versioned releases (tags) that other repos pin.
- `consumer` - the repo has git-sourced deps in its `pyproject.toml` pointing at tracked source repos.

A mid-layer repo that both produces and consumes can have both roles.

---

## Commands

All commands accept `--config` / `-c` to specify an alternative path to `repos.toml` (default: `repos.toml` in the working directory).

---

### `repomgr status`

```bash
repomgr status
```

Prints a traffic-light health dashboard across all tracked repos. For each repo it shows:

- Current branch and working-tree cleanliness
- Whether the local branch is ahead of, behind, or in sync with remote
- Which tracked git deps have a newer version available (consumer repos)
- An overall `GREEN` / `YELLOW` / `RED` health score

This command is read-only - it never modifies any repo.

---

### `repomgr fetch`

```bash
repomgr fetch
```

Runs `git fetch` on every tracked repo. After fetching, if a repo meets all of the following conditions, it is fast-forward merged automatically:

- `auto_merge = true` in `repos.toml`
- Currently on the `main` branch
- Working tree is clean
- Local and remote have not diverged

Repos that fail any condition are fetched but not merged; a note is printed. Failures on individual repos are logged as warnings and do not stop the others.

---

### `repomgr clone-missing`

```bash
repomgr clone-missing
```

Iterates all tracked repos and clones any that are not yet on disk. Repos that already exist are silently skipped.

---

### `repomgr update-deps`

```bash
repomgr update-deps [OPTIONS]
```

The main automation command. For each `consumer` repo (in topological order, sources first) it:

1. Checks preconditions - clean working tree, on `main`, not behind remote.
2. Parses git-sourced deps from `pyproject.toml` and resolves the latest available tag for each.
3. If at least one dep is outdated, creates a timestamped branch (`deps/update_YYYYMMDD_HHMMSS`), rewrites the pinned tags, runs `uv sync`, and runs the test suite.
4. On success - merges to `main` and pushes (if `auto_merge = true`), or leaves the branch for review.
5. On test failure - leaves the update branch checked out for manual inspection.

State (last run time, outcome, test result) is persisted to `repos.state.json` after each repo regardless of outcome.

**Options**

| Flag | Description |
|------|-------------|
| `--dry-run` | Print what would change without writing anything. |
| `--no-tests` | Skip the test suite; merge unconditionally on dep update. |
| `--repo NAME` / `-r NAME` | Restrict the run to a single repo by its `name`. |

```bash
# Preview what would be bumped
repomgr update-deps --dry-run

# Update only one consumer
repomgr update-deps --repo my-app

# Skip tests (useful when tests are slow or broken for other reasons)
repomgr update-deps --no-tests
```

---

### `repomgr stale-branches`

```bash
repomgr stale-branches
```

Lists branches that are merged or whose remote tracking ref is gone, for every on-disk repo. You are prompted interactively for each branch - press `y` to delete it locally, `n` to keep it.

---

### `repomgr dep-graph`

```bash
repomgr dep-graph
```

Prints the source-to-consumer dependency tree for all tracked repos. Useful for understanding update order and spotting circular deps.

---

## Typical daily workflow

```bash
# 1. Bring everything up to date from remotes
repomgr fetch

# 2. Check the fleet at a glance
repomgr status

# 3. Bump outdated git deps across all consumers
repomgr update-deps

# 4. Clean up old update branches
repomgr stale-branches
```

---

## Troubleshooting

**`Config file not found`** - Run commands from the directory that contains `repos.toml`, or pass `--config path/to/repos.toml`.

**Repo is skipped during `update-deps`** - The most common reasons are: not on `main`, dirty working tree, or local `main` is behind remote. Run `repomgr status` to see which condition applies, then fix it manually.

**`update-deps` leaves a branch instead of merging** - Either `auto_merge` is `false` for that repo, or the test suite failed. Inspect the branch, fix the issue, and merge manually, or rerun with `--no-tests` if the failure is unrelated.
