# repomgr - Implementation Tracker

Last updated: 2026-03-27 (renderer.py done)

## Phase overview

| Phase | Module | Detail file | Status | Notes |
|-------|--------|-------------|--------|-------|
| 1a | `config/repos_config.py` | `02-repos-config.md` | DONE | TOML schema + Pydantic models + loader; 21 tests |
| 1b | `state.py` | `03-state.md` | DONE | StateStore JSON connector + RepoState; 13 tests |
| 1c | `health.py` | `06-health.md` | DONE | Traffic-light scoring; 17 tests |
| 2 | `git.py` | `04-git.md` | DONE | Subprocess layer, all git operations; 27 tests |
| 3 | `deps.py` | `05-deps.md` | DONE | Dep graph, tag resolution, pyproject editing; 21 tests |
| 4 | `renderer.py` | `07-renderer.md` | DONE | Rich terminal formatting; 19 tests |
| 5a | `manager.py` | `08-manager.md` | NOT STARTED | Fetch, clone, status, stale branches |
| 5b | `update.py` | `09-update.md` | NOT STARTED | Dep update flow |
| 6 | `cli.py` | `10-cli.md` | NOT STARTED | Typer CLI entry point |
| 7 | GitHub Auth | `11-github-auth.md` | DEFERRED | GitHub App tokens (not needed for v1) |

## Scaffold status (already complete)

| Component | File | Status |
|-----------|------|--------|
| `BaseModelKwargs` | `data_models/basemodel_kwargs.py` | DONE |
| `Singleton` | `metaclasses/singleton.py` | DONE |
| `EnvType` enums | `params/env_type.py` | DONE |
| `.env` loader | `params/load_env.py` | DONE |
| `RepomgrParams` | `params/repomgr_params.py` | DONE |
| `RepomgrPaths` | `params/repomgr_paths.py` | DONE (location stubs empty) |
| `SampleConfig` | `config/sample_config.py` | DONE (reference) |
| `SampleParams` | `params/sample_params.py` | DONE (reference) |
| Test suite | `tests/` | DONE (21 tests passing) |

## Dependency chain

Implementation must respect this ordering (items listed above their dependents):

```
config/repos_config.py  (no deps)
state.py                (no deps)
git.py                  (no deps)
    |
    v
health.py               (config, state)
deps.py                 (git, config)
    |
    v
renderer.py             (health, state, git types)
    |
    v
manager.py              (git, state, health, deps, renderer)
update.py               (git, state, deps, renderer)
    |
    v
cli.py                  (all above)
```

Phases 1a, 1b, 1c, and 2 have no interdependencies and can proceed in any order.

## Key decisions log

| Decision | Rationale |
|----------|-----------|
| TOML models in `config/repos_config.py` | Avoids name conflict with `config/` dir; shapes belong in config |
| `repos.toml` path via CLI arg | Keeps repomgr generic; actual config lives externally |
| `RepoState` as dataclass (not Pydantic) | Internal state, not user-facing config |
| `git.py` has no internal imports | Pure subprocess layer, maximum reusability |
| `renderer.py` is sole `rich` importer | Clean display seam for future web/TUI swap |
| GitHub App auth deferred to phase 7 | SSH works for v1; auth adds 3 new dependencies |

## Open questions

- Should `repos.toml` support an `include` directive for splitting large configs?
  Probably not for v1 - keep it simple.
- Should `update.py` create GitHub PRs instead of direct merging?
  Deferred - requires GitHub App auth (phase 7).
- Should `fetch_all` run in parallel (asyncio/threading)?
  Not for v1 - sequential is simpler and sufficient for < 50 repos.

## Verification command

After each implementation step:

```bash
uv run pytest && uv run ruff check . && uv run pyright
```
