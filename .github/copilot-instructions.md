# repomgr - Copilot Instructions

## Project overview

`repomgr` is a local CLI tool for managing a fleet of Python repos on a single Linux box. It fetches, clones, health-checks, and updates git-sourced dependencies across a set of tracked repos defined in `repos.toml`. It supersedes the standalone `update_git_deps.py` script.

The package name is `repomgr` throughout the source. The CLI entry point is `repomgr` (via `repomgr.cli:app`).

## Running & tooling

```bash
uv run pytest                        # run tests
uv run ruff check .                  # lint (ruff, ALL rules enabled)
uv run pyright                       # type-check (src/ and tests/ only)

uv run mkdocs serve                  # MkDocs local docs server

repomgr status                       # dashboard across all repos
repomgr fetch                        # fetch all, report, auto-merge where configured
repomgr clone-missing                # clone repos not on disk
repomgr update-deps                  # run dep update flow across all consumers
repomgr stale-branches               # list and interactively delete stale branches
repomgr dep-graph                    # print the dependency tree
```

Credentials live at `~/cred/repomgr/.env` (loaded by `load_env()` in `src/repomgr/params/load_env.py`). See `nokeys.env` for required keys (`GITHUB_APP_ID`, `GITHUB_INSTALLATION_ID`, `GITHUB_APP_PEM_PATH`).

## Architecture layers

| Layer       | Path                               | Role                                                                     |
| ----------- | ---------------------------------- | ------------------------------------------------------------------------ |
| CLI         | `src/repomgr/cli.py`               | Typer entrypoint; loads config, builds dep graph, dispatches to modules  |
| Config      | `src/repomgr/config.py`            | `load_config(path)` - reads `repos.toml`, returns `RepomgrConfig`        |
| State       | `src/repomgr/state.py`             | `StateStore` - JSON-backed connector for `RepoState` per repo            |
| Git         | `src/repomgr/git.py`               | Pure subprocess layer; all git operations; no business logic             |
| Deps        | `src/repomgr/deps.py`              | Parses `pyproject.toml` git deps, resolves latest tags, dep graph        |
| Health      | `src/repomgr/health.py`            | Traffic-light scoring (`GREEN`/`YELLOW`/`RED`) from config + state       |
| Renderer    | `src/repomgr/renderer.py`          | Rich terminal output; reads data structures, no git calls or file IO     |
| Manager     | `src/repomgr/manager.py`           | Orchestrates fetch, clone, status, stale-branch operations               |
| Update      | `src/repomgr/update.py`            | Dep update flow: branch, edit pyproject.toml, test, merge or leave       |
| Params      | `src/repomgr/params/`              | Singleton `RepomgrParams`; paths and env-type helpers                    |

## Key patterns

**`repos.toml` is the single source of truth**  
All repo definitions live in `repos.toml`. The `load_config()` function in `config.py` is the only place that reads TOML. Everything downstream works with clean Pydantic models (`RepomgrConfig`, `RepoConfig`, `Settings`).

**`StateStore` is the only persistence layer**  
All read/write of `repos.state.json` goes through `StateStore`. Other modules never import `json` for state purposes. `StateStore.get(name)` never raises - it returns an empty `RepoState` for unknown names.

**`git.py` is a pure subprocess layer**  
All git operations are functions in `git.py`. Every function takes `cwd: Path` as its first argument. No config objects, no state, no business logic in this module.

**`renderer.py` is the only module that imports rich**  
It takes data structures and formats them. No git calls, no file IO.

**`RepomgrParams` singleton**  
Access project-wide config via `get_repomgr_params()` from `src/repomgr/params/repomgr_params.py`.

```python
from repomgr.params.repomgr_params import get_repomgr_params

params = get_repomgr_params()
paths = params.paths          # RepomgrPaths
```

**`BaseModelKwargs`**  
Extend `BaseModelKwargs` (not plain `BaseModel`) for any config that needs to be forwarded as `**kwargs` to a third-party constructor. `to_kw(exclude_none=True)` flattens a nested `kwargs` dict at the top level.

## Style rules

- Never use em dashes (`--` or `---` or Unicode `—`). Use a hyphen `-` or rewrite the sentence.
- Use `loguru` (`from loguru import logger as lg`) for all logging.
- Raise descriptive custom exceptions (e.g., `UnknownEnvLocationError`) rather than bare `ValueError`/`RuntimeError`.

## Documentation

Always keep the `docs/` folder updated at the end of a task.

### Docs folder

- `docs/` holds MkDocs source. `mkdocs.yml` configures the site with the Material theme, mkdocstrings for API reference.
- `docs/guides/` holds narrative guides related to tooling, setup, and project conventions. These are not part of the API reference and should not be written in docstring style.
- `docs/library/` holds description of the core library code. This is not an API reference; write in narrative style with custom headings as needed. Can create subfolders for different domains.
- `docs/reference/` is a virtual folder generated by `mkdocstrings` from docstrings in the source code. Do not write any files here; write docstrings in the source code instead.

### Docstring style

Use **Google style** throughout. mkdocstrings is configured with `docstring_style: "google"`.

Standard sections use a label followed by a colon, with content indented by 4 spaces:

```python
def example(value: int) -> str:
    """One-line summary.

    Extended description as plain prose.

    Args:
        value: Description of the argument.

    Returns:
        Description of the return value.

    Raises:
        KeyError: If the key is missing.

    Example:
        Brief usage example::

            result = example(42)
    """
```

**Never use NumPy / Sphinx RST underline-style headers** (`Args\n----`, `Returns\n-------`, `Attributes\n----------`, etc.).

Rules:
- Section labels: `Args:`, `Returns:`, `Raises:`, `Attributes:`, `Note:`, `Warning:`, `See Also:`, `Example:`, `Examples:` - always with a trailing colon, never with an underline.
- `Attributes:` in class docstrings uses two levels of indentation: the attribute name at +4 spaces, its description at +8 spaces.
- Module docstrings are narrative prose. Custom topic headings (e.g., "Pattern rules") are written as plain labelled paragraphs (`Pattern rules:`) - no underline, no RST heading markup.
- `See Also:` lists items as bare lines indented under the section label, not as `*` bullets.

## Testing & scratch space

- Tests live in `tests/` mirroring `src/repomgr/` structure.
- `scratch_space/` holds numbered exploratory notebooks and scripts. Not part of the package; ruff ignores `ERA001`/`F401`/`T20` there.

## Linting notes

- `ruff.toml` targets Python 3.13 with `select = ["ALL"]`. Key ignores: `COM812`, `D104`, `D203`, `D213`, `D413`, `FIX002`, `RET504`, `TD002`, `TD003`.
- Tests additionally allow `ARG001`, `INP001`, `PLR2004`, `S101`.
- Notebooks (`*.ipynb`) additionally allow `ERA001`, `F401`, `T20`.
- `meta/*` additionally allows `INP001`, `T20`.
- `max-args = 10` (pylint).

## End-of-task verification

After every code change, run the full verification suite before considering the task done:

```bash
uv run pytest && uv run ruff check . && uv run pyright
```

Then update the docs.
