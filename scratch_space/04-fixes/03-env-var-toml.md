# env var for config path

## overview

in cli
`/home/pmn/ephem/repomgr/src/repomgr/cli.py`

we have

```python
_CONFIG_OPTION = typer.Option(
    "repos.toml",
    "--config",
    "-c",
    help="Path to repos.toml config file.",
)
```

we want to make it so that default is empty, and when the environment variable `REPOMGR_CONFIG` is set, it will be used as the default value for the `--config` option.

## plan

### approach

Typer's `typer.Option` natively supports an `envvar=` argument. Resolution
precedence is: explicit CLI flag (`--config` / `-c`) > environment variable >
hard-coded default. This gives exactly the behaviour we want without any manual
`os.environ` reads, no custom default-factory logic, and it shows up in
`--help` automatically.

So we only need to add `envvar="REPOMGR_CONFIG"` to the existing
`_CONFIG_OPTION` and keep `"repos.toml"` as the final fallback default.

### decision: keep `repos.toml` fallback vs truly empty default

The overview says "make default empty". Two options:

- **Keep `"repos.toml"` as the fallback default** (recommended). When the env
  var is unset and no flag is passed, behaviour is unchanged (looks for
  `repos.toml` in CWD). When `REPOMGR_CONFIG` is set, it wins. This is the least
  surprising and keeps every existing test green.
- **Truly empty default** (`None`). Requires changing the option type to
  `Path | None`, adding a guard in `_load()` that raises a clean
  `typer.Exit(1)` with a helpful message when neither flag nor env var is set,
  and updating `_load`'s signature/typing. More churn, breaks the "just works in
  CWD" ergonomics.

Going with the first unless you say otherwise.

### steps

1. `src/repomgr/cli.py` - add `envvar="REPOMGR_CONFIG"` to `_CONFIG_OPTION` and
   mention the env var in its `help` string. No other code changes (the option
   is shared by all six commands, so all pick it up for free).

   ```python
   _CONFIG_OPTION = typer.Option(
       "repos.toml",
       "--config",
       "-c",
       envvar="REPOMGR_CONFIG",
       help="Path to repos.toml config file. Defaults to $REPOMGR_CONFIG, then repos.toml.",
   )
   ```

2. `tests/test_cli.py` - add a small test class covering env-var resolution via
   `CliRunner.invoke(..., env={"REPOMGR_CONFIG": str(toml)})`:
   - env var used when no `--config` flag is passed,
   - explicit `--config` flag overrides the env var,
   - (optional) unset env var + no flag still falls back to `repos.toml`.

3. Docs - update the `--config` description in:
   - `docs/library/cli.md` (lines ~28-29, ~47),
   - `docs/guides/user-guide.md` (line ~98, and the troubleshooting note ~223),
   to mention the `REPOMGR_CONFIG` env var and the precedence order.

4. Verify: `uv run pytest && uv run ruff check . && uv run pyright`.

### notes / edge cases

- Typer reads the env var at invocation time, so each command run re-reads it.
- Relative paths in `REPOMGR_CONFIG` resolve against CWD, same as the flag - no
  special handling needed; `load_config` already resolves paths.
- No change to `_load()` signature or the `RepomgrTomlConfig` loading path.
