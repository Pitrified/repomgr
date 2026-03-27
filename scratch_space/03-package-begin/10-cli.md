# Phase 6 - CLI Entry Point

## Goal

Provide the Typer CLI that wires all modules together. Thin dispatch layer - no business
logic, just config loading, dep graph building, StateStore instantiation, and delegation.

## File

`src/repomgr/cli.py`

## Entry point

Already declared in `pyproject.toml`:

```toml
[project.scripts]
repomgr = "repomgr.cli:app"
```

## Commands

```
repomgr status              # dashboard across all repos
repomgr fetch               # fetch all, report, auto-merge where configured
repomgr clone-missing       # clone repos not on disk
repomgr update-deps         # run dep update flow across all consumers
repomgr stale-branches      # list and interactively delete stale branches
repomgr dep-graph           # print the dependency tree
```

## Startup sequence (shared by all commands)

Every command needs config and state. Factor into a callback or helper:

```python
app = typer.Typer(name="repomgr", help="Manage a fleet of Python repos.")

# Global option
CONFIG_PATH = typer.Option(
    "repos.toml",
    "--config", "-c",
    help="Path to repos.toml config file.",
)

def _load(config_path: Path) -> tuple[RepomgrTomlConfig, StateStore, dict[str, list[str]]]:
    """Shared startup: load config, build dep graph, init state store."""
    config = load_config(config_path)
    dep_graph = build_dep_graph(config.repos)
    store = StateStore(config.settings.state_file)
    return config, store, dep_graph
```

## Command implementations

### `status`

```python
@app.command()
def status(config_path: Path = CONFIG_PATH) -> None:
    """Show health dashboard for all repos."""
    config, store, dep_graph = _load(config_path)
    manager.status_all(config, store, dep_graph)
```

### `fetch`

```python
@app.command()
def fetch(config_path: Path = CONFIG_PATH) -> None:
    """Fetch all repos, auto-merge where configured."""
    config, store, _dep_graph = _load(config_path)
    manager.fetch_all(config, store)
```

### `clone-missing`

```python
@app.command()
def clone_missing(config_path: Path = CONFIG_PATH) -> None:
    """Clone repos not present on disk."""
    config, _store, _dep_graph = _load(config_path)
    manager.clone_missing(config)
```

### `update-deps`

```python
@app.command()
def update_deps(
    config_path: Path = CONFIG_PATH,
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview changes without writing."),
    no_tests: bool = typer.Option(False, "--no-tests", help="Skip tests, merge unconditionally."),
    repo: str | None = typer.Option(None, "--repo", "-r", help="Update only this repo."),
) -> None:
    """Update git dependencies across consumer repos."""
    config, store, dep_graph = _load(config_path)
    update.update_deps(config, store, dep_graph, dry_run=dry_run, no_tests=no_tests, repo_name=repo)
```

### `stale-branches`

```python
@app.command()
def stale_branches(config_path: Path = CONFIG_PATH) -> None:
    """List and interactively delete stale branches."""
    config, _store, _dep_graph = _load(config_path)
    manager.stale_branches(config)
```

### `dep-graph`

```python
@app.command()
def dep_graph(config_path: Path = CONFIG_PATH) -> None:
    """Print the dependency tree."""
    config, _store, dep_graph = _load(config_path)
    renderer.render_dep_graph(dep_graph)
```

## Error handling

Wrap each command body in a try/except for clean error reporting:

```python
try:
    # ... command logic ...
except FileNotFoundError:
    lg.error(f"Config file not found: {config_path}")
    raise typer.Exit(code=1)
except ValidationError as e:
    lg.error(f"Invalid config: {e}")
    raise typer.Exit(code=1)
```

## Tests

`tests/test_cli.py`

Use Typer's `CliRunner` for integration-style tests.

Fixtures:
- `sample_repos_toml(tmp_path)` - write a valid repos.toml to tmp dir
- `runner` - `CliRunner()`

Test cases:
- `test_status_command` - runs without error
- `test_fetch_command` - runs without error
- `test_clone_missing_command` - runs without error
- `test_update_deps_dry_run` - --dry-run flag works
- `test_dep_graph_command` - prints graph
- `test_missing_config_exits` - exit code 1 when config not found
- `test_invalid_config_exits` - exit code 1 when config invalid
- `test_custom_config_path` - --config flag works

## Dependencies

- `typer` (already a dependency)
- `repomgr.config.repos_config`
- `repomgr.deps`
- `repomgr.state`
- `repomgr.manager`
- `repomgr.update`
- `repomgr.renderer`
- `loguru`
