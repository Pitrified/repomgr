# Getting Started

This guide covers setting up your development environment for repomgr.

## Prerequisites

- Python 3.14+
- [uv](https://docs.astral.sh/uv/) package manager

## Installation

### 1. Clone the Repository

```bash
git clone https://github.com/Pitrified/repomgr.git
cd repomgr
```

### 2. Install Dependencies

```bash
uv sync --group dev
```

### 3. Configure Credentials

Copy `nokeys.env` to `~/cred/repomgr/.env` and fill in the values:

```bash
GITHUB_APP_ID=12345678
GITHUB_INSTALLATION_ID=99999999
GITHUB_APP_PEM_PATH=~/.config/github-apps/repomgr-bot.pem
```

See `nokeys.env` for all required keys. For GitHub App setup details, refer to the plan in `scratch_space/vibes/09.1-github-app-auth-guide.md`.

### 4. Create `repos.toml`

Create `repos.toml` next to the installed package (see `scratch_space/vibes/09-repomgr-plan.md` for the full schema):

```toml
[settings]
base_path        = "~/repos"
default_test_cmd = "uv run pytest"
state_file       = "./repos.state.json"

[[repo]]
name       = "my-lib"
remote     = "git@github.com:you/my-lib.git"
roles      = ["source"]
auto_merge = true
```

### 5. Verify Installation

```bash
uv run pytest
uv run ruff check .
uv run pyright
```

## Development Workflow

### Running Tests

```bash
uv run pytest
uv run pytest -v
uv run pytest tests/config/
```

### Code Quality

```bash
uv run ruff check .
uv run ruff format .
uv run pyright
```

### Pre-commit Hooks

```bash
uv run pre-commit install
uv run pre-commit run --all-files
```

## Building Documentation

```bash
uv sync --group docs
uv run mkdocs serve
uv run mkdocs build
```

