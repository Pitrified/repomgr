---
status: planned
---

# Phase 1 - Schema + load_config + config tests

## Overview

Change the `repos.toml` schema in `src/repomgr/config/repos_config.py` so a repo
is identified by `owner` + `repo_name` (+ global `host`/`transport`) and the
clone URL is derived, then update the config's own test suite
(`tests/config/test_repos_config.py`) to match. This is the foundation phase;
everything downstream (manager, docs, live config) depends on the schema landing
first.

Context: [`00-start.md`](00-start.md) (Proposed approach + hidden problems 2, 4,
6). Phase 2 onward depend on this.

## Goals

1. Remove the per-repo `remote: str` field.
2. Add a `Transport` enum and the new identity fields on `Settings` and
   `RepoConfig`.
3. Resolve `owner`/`host`/`transport` onto each `RepoConfig` in `load_config()`,
   and expose `remote` as a computed property (single source of truth).
4. Raise a clear, named error when no `owner` can be resolved for a repo.
5. Update and extend `tests/config/test_repos_config.py`; suite green.

## Plan

### 1. `Transport` enum

Mirror the existing `Role(StrEnum)`:

```python
class Transport(StrEnum):
    SSH = "ssh"
    HTTPS = "https"
```

A bad value in TOML then fails pydantic validation with a clear message, for
free (no custom validator needed).

### 2. `Settings` - add global defaults

Add to `Settings`:

- `owner: str | None = None` - global default owner/org, optional.
- `host: str = "github.com"`
- `transport: Transport = Transport.SSH`

No validators needed beyond the enum coercion. Keep existing `base_path` /
`default_test_cmd` / `state_file` untouched.

### 3. `RepoConfig` - swap `remote` for identity fields

Remove `remote: str`. Add:

- `owner: str` - required *on the model* (by the time a `RepoConfig` exists the
  owner is resolved; `load_config` supplies it from the repo or the global).
- `repo_name: str | None = None` - remote repo name; when `None` the derived URL
  falls back to `name`.
- `host: str = "github.com"`
- `transport: Transport = Transport.SSH`

Keep `name`, `roles`, `auto_merge`, `test_cmd`, `path`, `deps` and their
validators unchanged.

Derived URL as a computed property (option (b) from 00-start - no stored
string, no drift):

```python
@computed_field  # type: ignore[prop-decorator]
@property
def remote(self) -> str:
    repo = self.repo_name or self.name
    if self.transport is Transport.SSH:
        return f"git@{self.host}:{self.owner}/{repo}.git"
    return f"https://{self.host}/{self.owner}/{repo}.git"
```

Downstream `repo.remote` (manager.py:112, tests) keeps working unchanged - it is
now a property instead of a field.

Optional (hidden problem 6): a `field_validator` that strips a single trailing
`.git` from `repo_name`/`name` before use, so `repo_name = "foo.git"` does not
yield `foo.git.git`. Low priority; include only if cheap.

### 4. `load_config()` - resolve owner/host/transport per repo

Inside the existing per-repo loop (currently resolves `path` and `test_cmd`):

- `owner = repo_raw.get("owner", settings.owner)`; if `owner is None`, raise a
  named error (see below) naming the repo.
- Pass `host=settings.host`, `transport=settings.transport` onto the
  `RepoConfig` so the computed `remote` is self-contained. A per-repo `transport`
  override is out of scope (00-start, rejected alternatives) - do not read it.
- `repo_name` flows through from `repo_raw` if present (else stays `None`).

Add a named exception near the top of the module (user rule: descriptive named
exceptions, not bare `ValueError`):

```python
class OwnerNotResolvedError(ValueError):
    """Raised when a repo has no owner and [settings].owner is unset."""

    def __init__(self, repo_name: str) -> None:
        super().__init__(
            f"repo {repo_name!r} has no 'owner' and [settings].owner is not set"
        )
```

### 5. Tests - `tests/config/test_repos_config.py`

Every fixture currently uses `remote = "git@github.com:user/<x>.git"`. Convert
each to `owner = "user"` (drop the `remote` line). Update assertions:

- `test_load_minimal_config`: drop `remote` from TOML, add `owner = "user"`;
  change `assert repo.remote == ...` to the derived ssh URL
  `git@github.com:user/myrepo.git`. Also assert `repo.owner == "user"`,
  `repo.transport is Transport.SSH`.
- `test_load_full_config`: add `[settings].owner`/`transport`/`host` where
  useful; assert derived `remote`.
- All other fixtures (`test_path_resolution_*`, `test_test_cmd_*`,
  `test_repos_by_name`, `test_multiple_repos`, the duplicate/empty error cases,
  `test_repo_config_path_tilde_expanded`): replace `remote=`/`remote =` with
  `owner`. The direct `RepoConfig(...)` construction at line 368 needs
  `owner="u"` instead of `remote="git@github.com:u/x.git"`.
- Import `Transport` alongside `Role`.

New tests to add:

- `test_remote_derived_ssh`: default transport yields
  `git@{host}:{owner}/{name}.git`.
- `test_remote_derived_https`: `[settings].transport = "https"` yields
  `https://{host}/{owner}/{name}.git`.
- `test_repo_name_override`: `repo_name` differing from `name` (the real
  `convo_craft` -> `convo-craft` case) appears in the URL while `path` still
  uses `name`.
- `test_owner_global_default`: repo with no `owner` inherits `[settings].owner`.
- `test_owner_per_repo_override`: per-repo `owner` beats the global.
- `test_owner_missing_raises`: no repo owner and no global owner ->
  `OwnerNotResolvedError` (subclass of `ValueError`).
- `test_transport_invalid_raises`: `transport = "ftp"` -> `ValidationError`.
- `test_transport_enum_values`: `Transport.SSH == "ssh"`,
  `Transport.HTTPS == "https"`.
- `test_settings_defaults`: extend to assert `owner is None`,
  `host == "github.com"`, `transport is Transport.SSH`.

## Out of scope

- Touching `manager.py` or non-config test files - phase 2. (No code change is
  expected there since `repo.remote` still resolves, but the verification of
  that belongs to phase 2.)
- `repos.toml.example` and docs - phase 3.
- Migrating the live linux-box config - phase 4.
- Per-repo `transport` override; HTTPS credential handling (deferred GitHub App
  phase).

## Done when

- `repos_config.py` has no `remote` field; `remote` is a computed property;
  `Transport` enum and the new `Settings`/`RepoConfig` fields exist;
  `OwnerNotResolvedError` is raised on an unresolvable owner.
- `uv run pytest tests/config/test_repos_config.py` passes, including the new
  cases above.
- `ruff` (and the repo's pre-commit hooks) are clean on the changed files.
- Full `uv run pytest` is NOT required to pass here (other suites still
  reference the old field; they are fixed in phase 2) - note which suites fail
  so phase 2 has the list.
