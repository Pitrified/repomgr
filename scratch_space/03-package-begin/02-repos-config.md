# Phase 1a - repos.toml Config Models + Loader

## Goal

Define the `repos.toml` schema as Pydantic models and provide a single `load_config()` function.
This module is the foundation - everything downstream works with clean typed models, never raw TOML.

## File

`src/repomgr/config/repos_config.py`

## Design decisions

### Placement in `config/`

The existing `config/` directory holds Pydantic shape models (per the config/params pattern).
The repos.toml models define the shape of the configuration, so they belong here.
The `load_config()` function is a simple TOML deserializer (not an env-var loader), so
including it alongside the models is pragmatic and keeps the module self-contained.

### `repos.toml` location

repomgr does NOT own `repos.toml`. The path is passed in:
- CLI: `--config path/to/repos.toml` (with a default like `./repos.toml`)
- Programmatic: `load_config(path)`

This keeps repomgr generic. The actual `repos.toml` with real repo definitions can live in
`linux-box-cloudflare/` or anywhere else.

## TOML schema

```toml
[settings]
base_path        = "~/repos"
default_test_cmd = "uv run pytest"
state_file       = "./repos.state.json"

[[repo]]
name        = "llm-core"
remote      = "git@github.com:Pitrified/llm-core.git"
roles       = ["source"]
auto_merge  = true

[[repo]]
name        = "fastapi-tools"
remote      = "git@github.com:Pitrified/fastapi-tools.git"
roles       = ["source", "consumer"]
auto_merge  = true

[[repo]]
name        = "recipamatic"
remote      = "git@github.com:Pitrified/recipamatic.git"
roles       = ["consumer"]
auto_merge  = false
test_cmd    = "uv run pytest -x"

[[repo]]
name        = "some-exception"
remote      = "git@github.com:Pitrified/some-exception.git"
roles       = ["consumer"]
path        = "~/projects/some-exception"
```

## Pydantic models

### `Role` enum

```python
class Role(StrEnum):
    SOURCE = "source"
    CONSUMER = "consumer"
```

### `Settings`

```python
class Settings(BaseModel):
    base_path: Path          # expanded (~ resolved)
    default_test_cmd: str
    state_file: Path         # resolved relative to repos.toml location
```

- `base_path` defaults to `~/repos`
- `default_test_cmd` defaults to `"uv run pytest"`
- `state_file` defaults to `"./repos.state.json"` (relative to repos.toml dir)

### `RepoConfig`

```python
class RepoConfig(BaseModel):
    name: str
    remote: str
    roles: list[Role]
    auto_merge: bool = False
    test_cmd: str            # resolved: per-repo override OR settings default
    path: Path               # resolved: explicit override OR base_path / name
    deps: list[str] = []     # populated later by deps.py
```

Validation:
- `name` must be non-empty
- `roles` must be non-empty
- `path` is `~`-expanded

### `RepomgrTomlConfig`

```python
class RepomgrTomlConfig(BaseModel):
    settings: Settings
    repos: list[RepoConfig]
    repos_by_name: dict[str, RepoConfig]   # computed convenience index
```

The `repos_by_name` is a computed property or populated during model construction.

## Public API

```python
def load_config(path: Path) -> RepomgrTomlConfig:
    """Read repos.toml and return validated config.

    Args:
        path: Path to the repos.toml file.

    Returns:
        Validated RepomgrTomlConfig with all paths resolved.

    Raises:
        FileNotFoundError: If the TOML file does not exist.
        ValidationError: If the TOML content does not match the schema.
    """
```

### Resolution logic inside `load_config()`

1. Read TOML via `tomllib.loads(path.read_text())`.
2. Expand `~` in `settings.base_path`.
3. Resolve `settings.state_file` relative to the TOML file's parent directory.
4. For each repo:
   - `path` = explicit override (expanded) OR `settings.base_path / name`.
   - `test_cmd` = per-repo value OR `settings.default_test_cmd`.
5. Validate and return `RepomgrTomlConfig`.

## Tests

`tests/config/test_repos_config.py`

Test cases:
- `test_load_minimal_config` - only required fields, defaults applied
- `test_load_full_config` - all fields specified
- `test_path_resolution` - base_path + name, explicit override, ~ expansion
- `test_state_file_resolution` - relative to TOML dir
- `test_test_cmd_fallback` - per-repo override vs settings default
- `test_repos_by_name` - convenience index populated correctly
- `test_missing_file` - raises FileNotFoundError
- `test_invalid_toml` - raises ValidationError
- `test_duplicate_repo_names` - raises validation error
- `test_empty_roles` - raises validation error

Use `tmp_path` fixture with TOML strings written to temp files.

## Dependencies

- `tomllib` (stdlib, Python 3.11+)
- `pydantic` (already a dependency)

## Notes

- No env vars read here - this is pure TOML deserialization
- The `deps` field on `RepoConfig` starts empty and is populated by `deps.py` at startup
- `remote` is stored as a plain string - no SSH vs HTTPS validation (that's git's job)
