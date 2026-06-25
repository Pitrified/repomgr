"""Tests for the CLI entry point.

Uses Typer's ``CliRunner`` for integration-style tests. All module-level
functions are mocked so no real git repos or file system writes are needed
beyond a minimal ``repos.toml``.
"""

from pathlib import Path
import textwrap
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from repomgr.cli import LogLevel
from repomgr.cli import app
from repomgr.config.repos_config import load_config
from repomgr.update import UnknownRepoError

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def runner() -> CliRunner:
    """Return a Typer CliRunner."""
    return CliRunner()


def _write_toml(tmp_path: Path, content: str = "") -> Path:
    """Write a minimal (or custom) repos.toml and return its path."""
    default = """
        [[repo]]
        name   = "repo-a"
        owner  = "user"
        roles  = ["source"]
    """
    p = tmp_path / "repos.toml"
    p.write_text(textwrap.dedent(content or default))
    return p


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------


class TestStatusCommand:
    """Tests for the ``status`` command."""

    def test_status_command_runs(self, runner: CliRunner, tmp_path: Path) -> None:
        """``status`` exits 0 and delegates to manager.status_all."""
        toml = _write_toml(tmp_path)
        with (
            patch("repomgr.cli.deps_mod.build_dep_graph", return_value={"repo-a": []}),
            patch("repomgr.cli.manager.status_all") as mock_status,
        ):
            result = runner.invoke(app, ["status", "--config", str(toml)])

        assert result.exit_code == 0
        mock_status.assert_called_once()

    def test_status_custom_config_path(self, runner: CliRunner, tmp_path: Path) -> None:
        """``--config`` flag is accepted and the command succeeds."""
        toml = _write_toml(tmp_path)
        with (
            patch("repomgr.cli.deps_mod.build_dep_graph", return_value={"repo-a": []}),
            patch("repomgr.cli.manager.status_all"),
        ):
            result = runner.invoke(app, ["status", "--config", str(toml)])

        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# fetch
# ---------------------------------------------------------------------------


class TestFetchCommand:
    """Tests for the ``fetch`` command."""

    def test_fetch_command_runs(self, runner: CliRunner, tmp_path: Path) -> None:
        """``fetch`` exits 0 and delegates to manager.fetch_all."""
        toml = _write_toml(tmp_path)
        with (
            patch("repomgr.cli.deps_mod.build_dep_graph", return_value={"repo-a": []}),
            patch("repomgr.cli.manager.fetch_all") as mock_fetch,
        ):
            result = runner.invoke(app, ["fetch", "--config", str(toml)])

        assert result.exit_code == 0
        mock_fetch.assert_called_once()


# ---------------------------------------------------------------------------
# clone-missing
# ---------------------------------------------------------------------------


class TestCloneMissingCommand:
    """Tests for the ``clone-missing`` command."""

    def test_clone_missing_runs(self, runner: CliRunner, tmp_path: Path) -> None:
        """``clone-missing`` exits 0 and delegates to manager.clone_missing."""
        toml = _write_toml(tmp_path)
        with (
            patch("repomgr.cli.deps_mod.build_dep_graph", return_value={"repo-a": []}),
            patch("repomgr.cli.manager.clone_missing") as mock_clone,
        ):
            result = runner.invoke(app, ["clone-missing", "--config", str(toml)])

        assert result.exit_code == 0
        mock_clone.assert_called_once()


# ---------------------------------------------------------------------------
# update-deps
# ---------------------------------------------------------------------------


class TestUpdateDepsCommand:
    """Tests for the ``update-deps`` command."""

    def test_update_deps_runs(self, runner: CliRunner, tmp_path: Path) -> None:
        """``update-deps`` exits 0 and delegates to update_mod.update_deps."""
        toml = _write_toml(tmp_path)
        with (
            patch("repomgr.cli.deps_mod.build_dep_graph", return_value={"repo-a": []}),
            patch("repomgr.cli.update_mod.update_deps") as mock_update,
        ):
            result = runner.invoke(app, ["update-deps", "--config", str(toml)])

        assert result.exit_code == 0
        mock_update.assert_called_once()

    def test_update_deps_dry_run(self, runner: CliRunner, tmp_path: Path) -> None:
        """``--dry-run`` is forwarded as ``dry_run=True``."""
        toml = _write_toml(tmp_path)
        with (
            patch("repomgr.cli.deps_mod.build_dep_graph", return_value={"repo-a": []}),
            patch("repomgr.cli.update_mod.update_deps") as mock_update,
        ):
            result = runner.invoke(
                app, ["update-deps", "--config", str(toml), "--dry-run"]
            )

        assert result.exit_code == 0
        _kw = mock_update.call_args.kwargs
        assert _kw["dry_run"] is True

    def test_update_deps_no_tests(self, runner: CliRunner, tmp_path: Path) -> None:
        """``--no-tests`` is forwarded as ``no_tests=True``."""
        toml = _write_toml(tmp_path)
        with (
            patch("repomgr.cli.deps_mod.build_dep_graph", return_value={"repo-a": []}),
            patch("repomgr.cli.update_mod.update_deps") as mock_update,
        ):
            result = runner.invoke(
                app, ["update-deps", "--config", str(toml), "--no-tests"]
            )

        assert result.exit_code == 0
        _kw = mock_update.call_args.kwargs
        assert _kw["no_tests"] is True

    def test_update_deps_repo_filter(self, runner: CliRunner, tmp_path: Path) -> None:
        """``--repo`` is forwarded as ``repo_name``."""
        toml = _write_toml(tmp_path)
        with (
            patch("repomgr.cli.deps_mod.build_dep_graph", return_value={"repo-a": []}),
            patch("repomgr.cli.update_mod.update_deps") as mock_update,
        ):
            result = runner.invoke(
                app, ["update-deps", "--config", str(toml), "--repo", "repo-a"]
            )

        assert result.exit_code == 0
        _kw = mock_update.call_args.kwargs
        assert _kw["repo_name"] == "repo-a"

    def test_update_deps_unknown_repo_exits(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """An UnknownRepoError causes exit code 1."""
        toml = _write_toml(tmp_path)
        with (
            patch("repomgr.cli.deps_mod.build_dep_graph", return_value={"repo-a": []}),
            patch(
                "repomgr.cli.update_mod.update_deps",
                side_effect=UnknownRepoError("no-such-repo"),
            ),
        ):
            result = runner.invoke(
                app,
                ["update-deps", "--config", str(toml), "--repo", "no-such-repo"],
            )

        assert result.exit_code == 1


# ---------------------------------------------------------------------------
# stale-branches
# ---------------------------------------------------------------------------


class TestStaleBranchesCommand:
    """Tests for the ``stale-branches`` command."""

    def test_stale_branches_runs(self, runner: CliRunner, tmp_path: Path) -> None:
        """``stale-branches`` exits 0 and delegates to manager.stale_branches."""
        toml = _write_toml(tmp_path)
        with (
            patch("repomgr.cli.deps_mod.build_dep_graph", return_value={"repo-a": []}),
            patch("repomgr.cli.manager.stale_branches") as mock_stale,
        ):
            result = runner.invoke(app, ["stale-branches", "--config", str(toml)])

        assert result.exit_code == 0
        mock_stale.assert_called_once()


# ---------------------------------------------------------------------------
# dep-graph
# ---------------------------------------------------------------------------


class TestDepGraphCommand:
    """Tests for the ``dep-graph`` command."""

    def test_dep_graph_runs(self, runner: CliRunner, tmp_path: Path) -> None:
        """``dep-graph`` exits 0 and delegates to renderer.render_dep_graph."""
        toml = _write_toml(tmp_path)
        with (
            patch("repomgr.cli.deps_mod.build_dep_graph", return_value={"repo-a": []}),
            patch("repomgr.cli.renderer.render_dep_graph") as mock_render,
        ):
            result = runner.invoke(app, ["dep-graph", "--config", str(toml)])

        assert result.exit_code == 0
        mock_render.assert_called_once_with({"repo-a": []})


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


class TestErrorPaths:
    """Tests for config error handling."""

    def test_missing_config_exits(self, runner: CliRunner, tmp_path: Path) -> None:
        """Exit code 1 when the config file does not exist."""
        missing = tmp_path / "no-such.toml"
        result = runner.invoke(app, ["status", "--config", str(missing)])
        assert result.exit_code == 1

    def test_invalid_config_exits(self, runner: CliRunner, tmp_path: Path) -> None:
        """Exit code 1 when the config file contains invalid content."""
        bad_toml = tmp_path / "repos.toml"
        bad_toml.write_text("[[repo]]\nname = 123\n")  # name must be a string
        result = runner.invoke(app, ["status", "--config", str(bad_toml)])
        assert result.exit_code == 1


# ---------------------------------------------------------------------------
# Config path resolution (env var)
# ---------------------------------------------------------------------------


class TestConfigEnvVar:
    """Tests for resolving the config path via ``REPOMGR_CONFIG``."""

    def test_env_var_used_when_no_flag(
        self,
        runner: CliRunner,
        tmp_path: Path,
    ) -> None:
        """``REPOMGR_CONFIG`` supplies the config path when no flag is passed."""
        toml = _write_toml(tmp_path)
        with (
            patch("repomgr.cli.deps_mod.build_dep_graph", return_value={"repo-a": []}),
            patch("repomgr.cli.manager.status_all"),
            patch("repomgr.cli.load_config", wraps=load_config) as mock_load,
        ):
            result = runner.invoke(
                app,
                ["status"],
                env={"REPOMGR_CONFIG": str(toml)},
            )

        assert result.exit_code == 0
        mock_load.assert_called_once_with(toml)

    def test_flag_overrides_env_var(
        self,
        runner: CliRunner,
        tmp_path: Path,
    ) -> None:
        """An explicit ``--config`` flag wins over ``REPOMGR_CONFIG``."""
        flag_toml = _write_toml(tmp_path)
        env_toml = tmp_path / "from-env.toml"
        with (
            patch("repomgr.cli.deps_mod.build_dep_graph", return_value={"repo-a": []}),
            patch("repomgr.cli.manager.status_all"),
            patch("repomgr.cli.load_config", wraps=load_config) as mock_load,
        ):
            result = runner.invoke(
                app,
                ["status", "--config", str(flag_toml)],
                env={"REPOMGR_CONFIG": str(env_toml)},
            )

        assert result.exit_code == 0
        mock_load.assert_called_once_with(flag_toml)


# ---------------------------------------------------------------------------
# Log level
# ---------------------------------------------------------------------------


class TestLogLevel:
    """Tests for the global ``--log-level`` option."""

    def _run(
        self,
        runner: CliRunner,
        tmp_path: Path,
        args: list[str],
    ) -> tuple[int, object]:
        """Invoke ``status`` with the given args, returning (exit_code, level)."""
        toml = _write_toml(tmp_path)
        with (
            patch("repomgr.cli.deps_mod.build_dep_graph", return_value={"repo-a": []}),
            patch("repomgr.cli.manager.status_all"),
            patch("repomgr.cli._configure_logging") as mock_cfg,
        ):
            result = runner.invoke(app, [*args, "status", "--config", str(toml)])
        level = mock_cfg.call_args.args[0] if mock_cfg.call_args else None
        return result.exit_code, level

    def test_default_level_is_info(self, runner: CliRunner, tmp_path: Path) -> None:
        """No flag configures logging at INFO."""
        exit_code, level = self._run(runner, tmp_path, [])
        assert exit_code == 0
        assert level == LogLevel.INFO

    def test_explicit_level(self, runner: CliRunner, tmp_path: Path) -> None:
        """``--log-level DEBUG`` configures logging at DEBUG."""
        exit_code, level = self._run(runner, tmp_path, ["--log-level", "DEBUG"])
        assert exit_code == 0
        assert level == LogLevel.DEBUG

    def test_level_is_case_insensitive(
        self,
        runner: CliRunner,
        tmp_path: Path,
    ) -> None:
        """A lowercase level name is accepted."""
        exit_code, level = self._run(runner, tmp_path, ["--log-level", "warning"])
        assert exit_code == 0
        assert level == LogLevel.WARNING

    def test_invalid_level_exits(self, runner: CliRunner, tmp_path: Path) -> None:
        """An unknown level name exits non-zero."""
        exit_code, _level = self._run(runner, tmp_path, ["--log-level", "LOUD"])
        assert exit_code != 0
