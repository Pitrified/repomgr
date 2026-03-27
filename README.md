# repomgr

Local CLI tool for managing a fleet of Python repos on a single Linux box. It fetches, clones, health-checks, and updates git-sourced dependencies across a set of tracked repos defined in `repos.toml`.

## Installation

### Setup `uv`

Setup [`uv`](https://docs.astral.sh/uv/getting-started/installation/).

### Install the package

```bash
uv sync --all-groups
```

## Usage

```bash
repomgr status           # dashboard across all repos
repomgr fetch            # fetch all, report, auto-merge where configured
repomgr clone-missing    # clone repos not on disk
repomgr update-deps      # run dep update flow across all consumers
repomgr stale-branches   # list and interactively delete stale branches
repomgr dep-graph        # print the dependency tree
```

## Configuration

Create `repos.toml` in the project root (see plan for schema details).

### Environment Variables

Copy `nokeys.env` to `~/cred/repomgr/.env` and fill in the values:

```bash
GITHUB_APP_ID=12345678
GITHUB_INSTALLATION_ID=99999999
GITHUB_APP_PEM_PATH=~/.config/github-apps/repomgr-bot.pem
```

For VSCode to recognize the environment file, add to the
workspace [settings file](.vscode/settings.json):

```json
"python.envFile": "/home/pmn/cred/repomgr/.env"
```

## Docs

Docs are available at [https://pitrified.github.io/repomgr/](https://pitrified.github.io/repomgr/).

## Development

### Pre-commit

```bash
uv run pre-commit install
uv run pre-commit run --all-files
```

### Verification

```bash
uv run pytest && uv run ruff check . && uv run pyright
```

