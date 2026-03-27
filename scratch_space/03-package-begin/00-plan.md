# repomgr - Comprehensive Implementation Plan

## Context

`repomgr` is a local CLI tool for managing a fleet of Python repos on a single Linux box.
It fetches, clones, health-checks, and updates git-sourced dependencies across a set of
tracked repos defined in an external `repos.toml` file.

This plan adapts the original design from `linux-box-cloudflare/scratch_space/vibes/09-repomgr-plan.md`
and `09.1-github-app-auth-guide.md` to the standalone package structure.

## Key adaptations from the original plan

- repomgr is a **standalone package** (not under `linux-box-cloudflare/tools/`)
- Scaffolded from `python-project-template` - the config/params pattern, Singleton,
  BaseModelKwargs, EnvType, and test infrastructure are already in place
- `repos.toml` lives **externally** (e.g., in `linux-box-cloudflare/`) and repomgr
  reads it from a path passed via CLI argument
- GitHub App credentials follow the existing params/config pattern within repomgr
- The existing `config/` directory holds Pydantic shape models; the plan's TOML-reading
  `config.py` becomes `config/repos_config.py` to avoid naming conflicts

## What already exists (scaffold)

| Component | Location | Status |
|-----------|----------|--------|
| `BaseModelKwargs` | `data_models/basemodel_kwargs.py` | Complete |
| `Singleton` metaclass | `metaclasses/singleton.py` | Complete |
| `EnvType` / `EnvStageType` / `EnvLocationType` | `params/env_type.py` | Complete |
| `.env` loader | `params/load_env.py` | Complete |
| `RepomgrParams` singleton | `params/repomgr_params.py` | Complete |
| `RepomgrPaths` | `params/repomgr_paths.py` | Mostly complete (location stubs) |
| `SampleConfig` / `SampleParams` | Reference implementations | Complete |
| Test suite | `tests/` | 21 tests passing |

## New modules to implement

All new modules live directly under `src/repomgr/`:

| Module | File | Depends on | Role |
|--------|------|------------|------|
| Repos config | `config/repos_config.py` | - | TOML schema + Pydantic models + `load_config()` |
| State | `state.py` | - | `StateStore` JSON persistence for `RepoState` |
| Git | `git.py` | - | Pure subprocess layer for all git operations |
| Deps | `deps.py` | `git.py`, `config/repos_config.py` | Dependency graph, tag resolution, pyproject editing |
| Health | `health.py` | `config/repos_config.py`, `state.py` | Traffic-light scoring (GREEN/YELLOW/RED) |
| Renderer | `renderer.py` | `health.py`, `state.py`, `git.py` types | Rich terminal formatting (only `rich` importer) |
| Manager | `manager.py` | `git.py`, `state.py`, `health.py`, `deps.py`, `renderer.py` | Orchestrates fetch, clone, status, stale branches |
| Update | `update.py` | `git.py`, `state.py`, `deps.py`, `renderer.py` | Dep update flow (branch, edit, test, merge) |
| CLI | `cli.py` | All above | Typer entrypoint, thin dispatch layer |
| GitHub Auth | `config/github_app_config.py` + `params/github_app_params.py` | params pattern | Token generation for HTTPS git ops (phase 2) |

## Implementation phases

### Phase 1 - Core foundation (no git operations)

1. **`config/repos_config.py`** - TOML schema, Pydantic models, `load_config()`
2. **`state.py`** - `StateStore` JSON connector, `RepoState` model
3. **`health.py`** - Pure scoring function with mocked inputs

### Phase 2 - Git layer

4. **`git.py`** - Subprocess wrappers for all git operations

### Phase 3 - Dependency management

5. **`deps.py`** - Parse pyproject.toml git deps, resolve tags, build graph

### Phase 4 - Terminal output

6. **`renderer.py`** - Rich formatting for all output types

### Phase 5 - Orchestration

7. **`manager.py`** - fetch, clone, status, stale-branches flows
8. **`update.py`** - Dep update flow (port from `update_git_deps.py`)

### Phase 6 - CLI + integration

9. **`cli.py`** - Typer commands wiring everything together

### Phase 7 - GitHub App auth (optional, deferred)

10. **GitHub App config/params** - Token generation for HTTPS operations

## File structure after completion

```
src/repomgr/
    __init__.py
    cli.py
    state.py
    git.py
    deps.py
    health.py
    renderer.py
    manager.py
    update.py
    config/
        __init__.py
        sample_config.py          # existing reference
        repos_config.py           # NEW: repos.toml schema + loader
        github_app_config.py      # NEW (phase 7): GitHub App config shape
    data_models/
        __init__.py
        basemodel_kwargs.py       # existing
    metaclasses/
        __init__.py
        singleton.py              # existing
    params/
        __init__.py
        env_type.py               # existing
        load_env.py               # existing
        repomgr_params.py         # existing
        repomgr_paths.py          # existing
        sample_params.py          # existing reference
        github_app_params.py      # NEW (phase 7): GitHub App credentials loader
```

## Detailed sub-plans

Each phase has a corresponding detail file:

- `02-repos-config.md` - repos.toml schema, Pydantic models, load function
- `03-state.md` - StateStore, RepoState, JSON persistence
- `04-git.md` - Pure subprocess git layer
- `05-deps.md` - Dependency graph, tag resolution, pyproject editing
- `06-health.md` - Traffic-light scoring rules
- `07-renderer.md` - Rich terminal output functions
- `08-manager.md` - Fetch, clone, status, stale-branches orchestration
- `09-update.md` - Dep update flow
- `10-cli.md` - Typer CLI commands and startup sequence
- `11-github-auth.md` - GitHub App authentication (phase 7)

## Testing strategy

- Each module gets its own test file mirroring `src/` structure
- Foundation modules (`config/repos_config.py`, `state.py`, `health.py`) are fully unit-testable
- `git.py` tests use a temporary git repo fixture
- `deps.py` tests use fixture pyproject.toml files
- `manager.py` and `update.py` tests mock `git.py` calls
- `cli.py` gets integration-style tests via Typer's `CliRunner`

## Deferred / out of scope for v1

- SQLite backend for StateStore (JSON is sufficient; swap later)
- Web/TUI dashboard frontend (renderer.py is the seam for this)
- Cron/scheduled runs (run manually or via shell cron calling `repomgr fetch`)
- GitHub Actions integration
- PyPI publishing
