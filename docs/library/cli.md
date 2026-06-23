# CLI

`cli.py` is the Typer entry point for `repomgr`. It is a thin dispatch layer
with no business logic - it loads config, builds the dependency graph,
initialises the state store, and delegates to the relevant module for each
command.

## Entry point

Declared in `pyproject.toml`:

```toml
[project.scripts]
repomgr = "repomgr.cli:app"
```

## Commands

| Command | Delegates to |
|---|---|
| `repomgr status` | `manager.status_all` |
| `repomgr fetch` | `manager.fetch_all` |
| `repomgr clone-missing` | `manager.clone_missing` |
| `repomgr update-deps` | `update.update_deps` |
| `repomgr stale-branches` | `manager.stale_branches` |
| `repomgr dep-graph` | `renderer.render_dep_graph` |

All commands accept `--config` / `-c` to specify a custom path to `repos.toml`.
The path is resolved in this order: the `--config` flag, the `REPOMGR_CONFIG`
environment variable, then `repos.toml` in the working directory.

## Global options

`--log-level` is a global option handled by the app callback (`main`). It sets
the loguru verbosity for the whole process and must be placed **before** the
subcommand:

```
repomgr --log-level DEBUG status
```

Accepted values are the loguru levels `TRACE`, `DEBUG`, `INFO`, `SUCCESS`,
`WARNING`, `ERROR`, `CRITICAL` (case-insensitive). The default is `INFO`. The
callback calls `_configure_logging`, which resets loguru to a single `stderr`
sink at the requested level.

## Startup sequence

Every command calls the shared `_load(config_path)` helper, which:

1. Calls `load_config(config_path)` - raises `typer.Exit(code=1)` on
   `FileNotFoundError` or any other load error.
2. Calls `deps.build_dep_graph(config.repos, config.repos_by_name)` to build
   the adjacency list used by `update-deps` and `status`.
3. Constructs a `StateStore` pointed at `config.settings.state_file`.

## `update-deps` options

```
repomgr update-deps [OPTIONS]

Options:
  --config    / -c         Path to repos.toml (env: REPOMGR_CONFIG, default: repos.toml)
  --dry-run                Preview changes without writing
  --no-tests               Skip tests, merge unconditionally
  --repo / -r              Update only the named repo
```

An `UnknownRepoError` (when `--repo` names a repo not in the config) is
caught and reported as exit code 1.

## Error handling

Config load failures print a loguru error and exit with code 1. Downstream
errors (e.g. git failures) are handled inside the delegated modules and do not
propagate to the CLI layer.
