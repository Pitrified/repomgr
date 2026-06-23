# env loading

## draft

load env is called in init
please call it from within the cli
but note the trick: we want to call it AFTER app callback main fired, so that the cli knows which level to use (load env writes to log.debug),
but has to be available for the typer option to get the repomgr_config
analyze if it's possible, when does the config actually read the env var?
cheers

## analysis

### Current state

`load_env()` is called at import time in `__init__.py`. This means it fires the moment
any part of `repomgr` is imported - before the CLI has even started parsing arguments.
`_configure_logging()` inside the app callback has not run yet, so loguru still has its
default handler. The `lg.debug(...)` lines in `load_env()` either vanish (default level
is WARNING) or land on the wrong handler.

### When does `REPOMGR_CONFIG` get read?

Typer wraps Click. The `envvar="REPOMGR_CONFIG"` annotation means Click will fall back
to `os.environ["REPOMGR_CONFIG"]` if the option is not supplied on the command line.

Click resolves option values - including env-var lookups - during the **parsing phase**,
inside `Context.__init__` / `Command.parse_args()`. That happens before any Python
function is called: before the app callback, before the subcommand. The call chain is:

```
app()                        # Click's main entry
  -> BaseCommand.main()
  -> Context created
  -> args parsed / envvars resolved  ← REPOMGR_CONFIG read here
  -> app callback (main) invoked
  -> subcommand invoked
```

So `load_env()` would have to run **before** Click starts parsing for `REPOMGR_CONFIG`
from the `.env` file to have any effect on that option.

### The tension

Two goals are in conflict:

| Goal | Requires |
|---|---|
| `load_env()` debug respects `--log-level` | `load_env()` after `_configure_logging()`, i.e. inside the callback |
| `envvar="REPOMGR_CONFIG"` works from `.env` | `load_env()` before Click parses args, i.e. before the callback |

They cannot both be satisfied. Trying to accommodate both while leaving `envvar=`
in place and documenting "don't put `REPOMGR_CONFIG` in the `.env`" is a broken
contract - the annotation implies it works.

### Resolution options

**Option A - keep `load_env()` early, drop the debug-level ambition**
Keep the call in `__init__.py` (or move it to a module-level statement in `cli.py`).
The debug messages fire before logging is configured; at default INFO level they are
invisible, which is fine - they are noise for normal users. `envvar="REPOMGR_CONFIG"`
works from both the shell and from `.env`. Nothing changes for users.

**Option B - move `load_env()` to callback, drop `envvar="REPOMGR_CONFIG"`**
If `load_env()` runs after Click parses args, the `envvar=` annotation is unreliable
for `.env`-sourced values. The honest thing is to remove it. Users who want a
non-default config path must pass `--config` or set the var in their shell profile.
The `.env` file is for credentials only, which is already the intent.

### Why Option A is also broken

Loguru's default handler uses DEBUG level. Moving `load_env()` to module level in
`cli.py` doesn't help - those debug lines fire before `_configure_logging()` runs,
and they print on every invocation. That's visible noise, not silent.

### Verdict

Option B - but with a clarification on `envvar=`.

`envvar="REPOMGR_CONFIG"` reads from `os.environ`, which is populated before the
process starts. It only fails to pick up a value that came from the `.env` file, because
that file hasn't been loaded yet. A path like `REPOMGR_CONFIG` belongs in `.bashrc` /
`.zshrc`, not in a credentials file. So removing `envvar=` from the Typer option
doesn't take anything away from realistic usage - shell-level exports still work, and
`--config` / `-c` covers the rest. The `.env` file stays strictly for credentials.

## plan

1. Remove `load_env()` call (and its import) from `src/repomgr/__init__.py`.
2. Add `from repomgr.params.load_env import load_env` to `cli.py`.
3. Call `load_env()` after `_configure_logging(log_level)` in the `main()` callback.
4. Drop `envvar="REPOMGR_CONFIG"` from `_CONFIG_OPTION` and update the help text.
5. Run `uv run pytest && uv run ruff check . && uv run pyright` to verify.

