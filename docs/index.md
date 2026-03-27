# repomgr

**repomgr** is a local CLI tool for managing a fleet of Python repos on a single Linux box. It fetches, clones, health-checks, and updates git-sourced dependencies across a set of tracked repos defined in `repos.toml`.

## Features

- **Fleet dashboard** - traffic-light health status across all tracked repos at a glance
- **Fetch and auto-merge** - batch `git fetch` with optional fast-forward for clean repos
- **Dependency updates** - detects outdated git-sourced deps, branches, tests, and merges
- **Stale branch cleanup** - interactive pruning of merged/gone branches
- **Dep graph** - visualises the source-consumer dependency tree

## Quick Start

```bash
# Install
uv sync --all-groups

# Run
repomgr status
repomgr fetch
repomgr update-deps
```

## Project Structure

```
repomgr/
├── repos.toml            # tracked repo definitions (committed)
├── repos.toml.example    # annotated example
├── repos.state.json      # generated state file (gitignored)
└── src/repomgr/
    ├── cli.py            # Typer entrypoint
    ├── config.py         # repos.toml parser -> Pydantic models
    ├── state.py          # StateStore (JSON-backed)
    ├── git.py            # pure subprocess git layer
    ├── deps.py           # dep graph and tag resolution
    ├── health.py         # traffic-light scoring
    ├── renderer.py       # Rich terminal output
    ├── manager.py        # fetch, clone, status orchestration
    └── update.py         # dep update flow
```

## Next Steps

- [Getting Started](getting-started.md) - set up your development environment
- [API Reference](reference/) - explore the codebase

