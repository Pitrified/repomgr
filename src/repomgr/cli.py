"""Typer CLI entry point for repomgr.

This module is a thin dispatch layer. It loads config, builds the dep graph,
creates a StateStore, and delegates to the relevant module for each command.
No business logic lives here.

Pattern rules:
    Every command calls ``_load()`` to obtain the standard trio of
    ``(config, store, dep_graph)``.  Config loading errors are caught and
    reported cleanly before raising ``typer.Exit(code=1)``.
"""

from enum import StrEnum
from pathlib import Path
import sys
from typing import Annotated

from loguru import logger as lg
import typer

from repomgr import deps as deps_mod
from repomgr import manager
from repomgr import renderer
from repomgr import update as update_mod
from repomgr.config.repos_config import RepomgrTomlConfig
from repomgr.config.repos_config import load_config
from repomgr.state import StateStore

app = typer.Typer(name="repomgr", help="Manage a fleet of Python repos.")

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------


class LogLevel(StrEnum):
    """Loguru log levels accepted by the ``--log-level`` option."""

    TRACE = "TRACE"
    DEBUG = "DEBUG"
    INFO = "INFO"
    SUCCESS = "SUCCESS"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


def _configure_logging(level: LogLevel) -> None:
    """Reset loguru to a single stderr sink at the given level.

    Args:
        level: Minimum level for emitted log records.
    """
    lg.remove()
    lg.add(sys.stderr, level=level.value)


# ---------------------------------------------------------------------------
# App callback
# ---------------------------------------------------------------------------


@app.callback()
def main(
    log_level: Annotated[
        LogLevel,
        typer.Option(
            "--log-level",
            help="Logging verbosity for all commands.",
            case_sensitive=False,
        ),
    ] = LogLevel.INFO,
) -> None:
    """Manage a fleet of Python repos."""
    _configure_logging(log_level)


# ---------------------------------------------------------------------------
# Shared option default
# ---------------------------------------------------------------------------

_CONFIG_OPTION = typer.Option(
    "repos.toml",
    "--config",
    "-c",
    envvar="REPOMGR_CONFIG",
    help="Path to repos.toml. Defaults to $REPOMGR_CONFIG, then repos.toml.",
)

# ---------------------------------------------------------------------------
# Shared startup helper
# ---------------------------------------------------------------------------


def _load(
    config_path: Path,
) -> tuple[RepomgrTomlConfig, StateStore, dict[str, list[str]]]:
    """Load config, build dep graph, and initialise the state store.

    Args:
        config_path: Path to the repos.toml file.

    Returns:
        Three-tuple of (config, store, dep_graph).

    Raises:
        typer.Exit: With exit code 1 when the config cannot be loaded.
    """
    try:
        config = load_config(config_path)
    except FileNotFoundError:
        lg.error("Config file not found: {}", config_path)
        raise typer.Exit(code=1) from None
    except Exception as exc:
        lg.error("Failed to load config: {}", exc)
        raise typer.Exit(code=1) from exc

    dep_graph = deps_mod.build_dep_graph(config.repos, config.repos_by_name)
    store = StateStore(config.settings.state_file)
    return config, store, dep_graph


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@app.command()
def status(
    config_path: Path = _CONFIG_OPTION,
) -> None:
    """Show health dashboard for all repos."""
    config, store, dep_graph = _load(config_path)
    manager.status_all(config, store, dep_graph)


@app.command()
def fetch(
    config_path: Path = _CONFIG_OPTION,
) -> None:
    """Fetch all repos, auto-merge where configured."""
    config, store, _dep_graph = _load(config_path)
    manager.fetch_all(config, store)


@app.command()
def clone_missing(
    config_path: Path = _CONFIG_OPTION,
) -> None:
    """Clone repos not present on disk."""
    config, _store, _dep_graph = _load(config_path)
    manager.clone_missing(config)


@app.command()
def update_deps(
    config_path: Path = _CONFIG_OPTION,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Preview changes without writing."),
    ] = False,
    no_tests: Annotated[
        bool,
        typer.Option("--no-tests", help="Skip tests, merge unconditionally."),
    ] = False,
    repo: Annotated[
        str | None,
        typer.Option("--repo", "-r", help="Update only this repo."),
    ] = None,
) -> None:
    """Update git dependencies across consumer repos."""
    try:
        config, store, dep_graph = _load(config_path)
        update_mod.update_deps(
            config,
            store,
            dep_graph,
            dry_run=dry_run,
            no_tests=no_tests,
            repo_name=repo,
        )
    except update_mod.UnknownRepoError as exc:
        lg.error("{}", exc)
        raise typer.Exit(code=1) from exc


@app.command()
def stale_branches(
    config_path: Path = _CONFIG_OPTION,
) -> None:
    """List and interactively delete stale branches."""
    config, _store, _dep_graph = _load(config_path)
    manager.stale_branches(config)


@app.command()
def dep_graph(
    config_path: Path = _CONFIG_OPTION,
) -> None:
    """Print the dependency tree."""
    _config, _store, dep_graph = _load(config_path)
    renderer.render_dep_graph(dep_graph)
