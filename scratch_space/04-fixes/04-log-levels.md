# log level default

## overview

in cli
`/home/pmn/ephem/repomgr/src/repomgr/cli.py`

we want to add a flag `--log-level` that sets the log level for the commands

The default log level should be `INFO`

set it for loguru for whole app

is it a flag on the main `repomgr` command, or on each subcommand? probably main command, so it applies to all subcommands

## plan

### approach

Add a Typer **app-level callback** (`@app.callback()`) with a `--log-level`
option that applies to every subcommand. The callback runs before any command,
so configuring loguru there sets the level once for the whole process.

Currently nothing configures loguru anywhere (only `logger as lg` is imported
and used). loguru ships with a default stderr sink at `DEBUG`. To honour the
flag we must `logger.remove()` the default handler and `logger.add()` a fresh
stderr sink at the requested level.

### log level values

Use a `str`-backed `enum.Enum` (`LogLevel`) of loguru's standard levels so Typer
validates the input and lists choices in `--help`:

`TRACE, DEBUG, INFO, SUCCESS, WARNING, ERROR, CRITICAL`

Default = `INFO`. An enum is preferred over a free `str` because it gives
automatic validation + a clean error on a bad value, and shows the choices in
help. Typer matches enum values case-insensitively by name.

### steps

1. `src/repomgr/cli.py`:
   - `import sys` and `from enum import Enum`.
   - Define `class LogLevel(str, Enum)` with the seven loguru levels (value =
     the loguru level name, e.g. `INFO = "INFO"`).
   - Add a small helper `_configure_logging(level: LogLevel) -> None` that does
     `lg.remove()` then `lg.add(sys.stderr, level=level.value)`.
   - Add an `@app.callback()` function (e.g. `main`) taking
     `log_level: Annotated[LogLevel, typer.Option("--log-level", help=...)] = LogLevel.INFO`
     and calling `_configure_logging(log_level)`.

   ```python
   @app.callback()
   def main(
       log_level: Annotated[
           LogLevel,
           typer.Option("--log-level", help="Logging verbosity.", case_sensitive=False),
       ] = LogLevel.INFO,
   ) -> None:
       """Manage a fleet of Python repos."""
       _configure_logging(log_level)
   ```

   Note: `--log-level` goes *before* the subcommand
   (`repomgr --log-level DEBUG status`), which is standard Typer behaviour for
   callback options.

2. `tests/test_cli.py` - add a `TestLogLevel` class:
   - default invocation configures loguru at `INFO`,
   - `--log-level DEBUG` (and a lowercase `debug`) is accepted,
   - an invalid level exits non-zero.
   Patch `repomgr.cli._configure_logging` (or `lg.remove`/`lg.add`) to assert it
   is called with the resolved level rather than mutating global logger state.

3. Docs:
   - `docs/library/cli.md` - document the global `--log-level` option in the
     CLI overview / startup section.
   - `docs/guides/user-guide.md` - mention `--log-level` in the Commands section
     (global flag, default `INFO`, placed before the subcommand).

4. Verify: `uv run pytest && uv run ruff check . && uv run pyright`.

### notes / edge cases

- Because the callback runs for every command, the existing `lg.error(...)`
  calls in `_load` / `update_deps` continue to work and now respect the level.
- `lg.remove()` with no args drops loguru's default handler; safe to call once
  per process at startup.
- Adding `--log-level` as a callback option means `repomgr --help` shows it at
  the top level, and each subcommand's `--help` will not repeat it (acceptable;
  it is a global flag).
- The callback also becomes the app's help docstring source; keep the existing
  "Manage a fleet of Python repos." text so `repomgr --help` is unchanged.