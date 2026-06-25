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
owner            = "Pitrified"   # default owner for every repo
host             = "github.com"
transport        = "ssh"         # or "https"

[[repo]]
name       = "llm-core"
roles      = ["source"]
auto_merge = true

[[repo]]
name      = "convo_craft"
repo_name = "convo-craft"        # remote name differs from local name
roles     = ["consumer"]

[[repo]]
name     = "recipamatic"
owner    = "SomeoneElse"         # per-repo owner overrides settings.owner
roles    = ["consumer"]
path     = "~/projects/recipamatic"
test_cmd = "uv run pytest -x"
```

The clone URL is **derived**, not stored: repomgr builds it from
`transport` + `host` + `owner` + `repo_name` (falling back to `name`). The two
forms are:

- ssh: `git@{host}:{owner}/{repo_name}.git`
- https: `https://{host}/{owner}/{repo_name}.git`

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

### Transport

`Transport` is a `StrEnum` with two values:

- `ssh` (default) - builds `git@{host}:{owner}/{repo}.git`.
- `https` - builds `https://{host}/{owner}/{repo}.git`.

!!! warning "`transport = "https"` does not authenticate"
    Choosing HTTPS only changes the URL shape. Cloning, fetching, and pushing
    **private** repos over HTTPS still needs a credential - a token or a
    configured git credential helper - otherwise the operation prompts or
    fails. HTTPS is fine for public repos or where a credential helper is set
    up. Built-in token-based auth is the subject of the deferred GitHub App
    phase (`scratch_space/03-package-begin/11-github-auth.md`); SSH needs no
    extra setup beyond the user's keys.

### Settings

| Field | Default | Description |
|-------|---------|-------------|
| `base_path` | `~/repos` | Root directory for repo clones. Tilde is expanded. |
| `default_test_cmd` | `uv run pytest` | Test command used when a repo has no override. |
| `state_file` | `./repos.state.json` | Path to the JSON state file. Relative paths are resolved against the directory that contains `repos.toml`. |
| `owner` | none | Default repo owner/org applied to every repo without its own `owner`. |
| `host` | `github.com` | Git host used to build clone URLs. |
| `transport` | `ssh` | Git transport (`ssh` or `https`) used to build clone URLs. |

### RepoConfig

| Field | Required | Description |
|-------|----------|-------------|
| `name` | yes | Unique short identifier; default local clone dir and remote repo name. |
| `owner` | resolved | Per-repo override or `settings.owner`. An unresolvable owner is an error. |
| `repo_name` | no | Remote repo name when it differs from `name`; defaults to `name`. |
| `roles` | yes | Non-empty list of `Role` values. |
| `auto_merge` | no (false) | Merge dependency updates automatically on success. |
| `test_cmd` | resolved | Per-repo override or `settings.default_test_cmd`. |
| `path` | resolved | Explicit override or `settings.base_path / name`. |
| `deps` | populated later | Git-sourced dependency names; filled by `deps.py`. |
| `remote` | computed | Derived clone URL (`transport`/`host`/`owner`/`repo_name`); read-only. |

`host` and `transport` are also copied onto each `RepoConfig` during loading so
the computed `remote` is self-contained.

## Path resolution

All resolution happens inside `load_config()`, not in model validators.
Validators only normalise values that are always safe regardless of context
(expanding `~`).

Resolution order:

1. `settings.state_file` - if relative, joined to the TOML file's parent and resolved.
2. `repo.path` - explicit `path` field (tilde-expanded) or `settings.base_path / name`.
3. `repo.test_cmd` - per-repo `test_cmd` or `settings.default_test_cmd`.
4. `repo.owner` - per-repo `owner` or `settings.owner`; if neither is set,
   `OwnerNotResolvedError` is raised naming the repo.
5. `repo.host` / `repo.transport` - copied from `settings` so the computed
   `remote` URL is self-contained.

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
  (e.g. empty `roles`, duplicate repo names, an unknown `transport` value).
- `OwnerNotResolvedError` - if a repo has no `owner` and `settings.owner` is
  unset.

## Validation rules

- `name` must not be empty.
- `roles` must contain at least one value.
- Repo names must be unique across the entire config.
