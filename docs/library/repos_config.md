# Repos Config

`config/repos_config.py` defines the Pydantic schema for `repos.toml` and
provides `load_config()` - the single entry point for reading repository
configuration at runtime.

## Schema overview

A `repos.toml` file has two sections: an optional `[settings]` block and one
or more `[[repo]]` entries.

```toml
[settings]
base_path        = "~/repos"
default_test_cmd = "uv run pytest"
state_file       = "./repos.state.json"

[[repo]]
name       = "llm-core"
remote     = "git@github.com:Pitrified/llm-core.git"
roles      = ["source"]
auto_merge = true

[[repo]]
name     = "recipamatic"
remote   = "git@github.com:Pitrified/recipamatic.git"
roles    = ["consumer"]
path     = "~/projects/recipamatic"
test_cmd = "uv run pytest -x"
```

## Model hierarchy

```
RepomgrTomlConfig
  settings: Settings
  repos:    list[RepoConfig]
  repos_by_name: dict[str, RepoConfig]   <- computed index
```

### Role

`Role` is a `StrEnum` with two values:

- `source` - the repo produces artifacts consumed by others.
- `consumer` - the repo depends on git-sourced artifacts from other repos.

A repo can have both roles simultaneously.

### Settings

| Field | Default | Description |
|-------|---------|-------------|
| `base_path` | `~/repos` | Root directory for repo clones. Tilde is expanded. |
| `default_test_cmd` | `uv run pytest` | Test command used when a repo has no override. |
| `state_file` | `./repos.state.json` | Path to the JSON state file. Relative paths are resolved against the directory that contains `repos.toml`. |

### RepoConfig

| Field | Required | Description |
|-------|----------|-------------|
| `name` | yes | Unique short identifier. |
| `remote` | yes | Git remote URL (SSH or HTTPS). |
| `roles` | yes | Non-empty list of `Role` values. |
| `auto_merge` | no (false) | Merge dependency updates automatically on success. |
| `test_cmd` | resolved | Per-repo override or `settings.default_test_cmd`. |
| `path` | resolved | Explicit override or `settings.base_path / name`. |
| `deps` | populated later | Git-sourced dependency names; filled by `deps.py`. |

## Path resolution

All resolution happens inside `load_config()`, not in model validators.
Validators only normalise values that are always safe regardless of context
(expanding `~`).

Resolution order:

1. `settings.state_file` - if relative, joined to the TOML file's parent and resolved.
2. `repo.path` - explicit `path` field (tilde-expanded) or `settings.base_path / name`.
3. `repo.test_cmd` - per-repo `test_cmd` or `settings.default_test_cmd`.

## Loading config

```python
from pathlib import Path
from repomgr.config.repos_config import load_config

cfg = load_config(Path("repos.toml"))

# Access settings
print(cfg.settings.base_path)

# Iterate repos
for repo in cfg.repos:
    print(repo.name, repo.path)

# Look up a specific repo
lib = cfg.repos_by_name["llm-core"]
```

`load_config()` raises:

- `FileNotFoundError` - if the TOML file does not exist.
- `tomllib.TOMLDecodeError` - if the file content is not valid TOML.
- `pydantic.ValidationError` - if the content does not match the schema
  (e.g. empty `roles`, duplicate repo names, missing required fields).

## Validation rules

- `name` must not be empty.
- `roles` must contain at least one value.
- Repo names must be unique across the entire config.
