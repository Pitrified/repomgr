# Rework repo remote config: store user + repo name, not a hard-coded URL

## The idea (original framing)

Right now each `[[repo]]` entry in `repos.toml` carries a full `remote` URL,
hard-coded as either SSH or HTTPS:

```toml
[[repo]]
name   = "my-lib"
remote = "git@github.com:you/my-lib.git"
```

That bakes the transport (ssh vs https) and the host into every entry.
Instead we want to save just the **user/owner** and the **repo name**, and let
repomgr build the actual clone URL from those plus a configurable transport.
So the same config works whether you clone over SSH or HTTPS, and switching is
a one-line global change instead of editing every repo.

## Current state (what exists today)

- Schema lives in `src/repomgr/config/repos_config.py`.
  - `RepoConfig.remote: str` - "Git remote URL (SSH or HTTPS)".
  - `RepoConfig.name: str` - unique short name, also used to derive the local
    clone path (`base_path / name`).
  - `Settings` block holds `base_path`, `default_test_cmd`, `state_file`.
- `remote` is consumed in exactly one place for cloning:
  - `src/repomgr/manager.py:112` - `git.clone(repo.remote, repo.path)`.
  - `src/repomgr/git.py:329` - `clone(remote: str, dest: Path)` just shells
    `git clone <remote> <dest>`.
- A separate, related URL concern lives in `src/repomgr/deps.py`:
  - `_GIT_DEP_PATTERN` parses git-sourced dependency lines out of a consumer's
    `pyproject.toml` of the form
    `name @ git+ssh://git@<host>/<owner>/<repo>[@tag]` or the `https://` form.
  - This parses URLs that *already exist in pyproject.toml*, not the ones we
    generate. It is downstream of pip/uv, not of `repos.toml`. So it is mostly
    out of scope, but the host/owner/repo shape there is a useful reference for
    how URLs are structured. Worth keeping consistent.
- Sample config: `repos.toml.example` documents `remote` as required.

## Proposed approach

Replace the single `remote: str` field with structured identity fields, and
derive the URL when cloning.

Per-repo fields (decided):

- `owner` - optional per-repo override of the user/org. When missing, falls
  back to `[settings].owner`. (At least one of the two must resolve - error if
  neither is set.)
- `name` - already exists; the local short name / key.
- `repo_name` - optional override for the repo name on the remote. When
  missing, populated with `name`. (Q3 answered: keep the override, optional.)

Global `[settings]` fields (decided):

- `owner` - default user/org applied to every repo that does not set its own.
  Matches real usage (all 28 entries share `Pitrified`).
- `host` - default `github.com`.
- `transport` - `ssh` or `https`, default `ssh`. (Naming: `transport`, for
  consistency. Q1 answered.)

URL construction (derived, e.g. a `computed_field` or method on `RepoConfig`).
Uses `repo_name` (which defaults to `name`):

- ssh: `git@{host}:{owner}/{repo_name}.git`
- https: `https://{host}/{owner}/{repo_name}.git`

This keeps `name` as the local key/path, while `repo_name` (defaulted to `name`)
is what appears on the remote. The derived URL feeds `git.clone` unchanged.

Note: `host` and `transport` live in `[settings]`, but the derived URL is a
property of each `RepoConfig`. So either the `RepoConfig` needs access to the
settings at construction time, or the URL is derived at `load_config()` time
(where both are in scope) and stored. Leaning toward deriving in
`load_config()` and storing a `remote` field, mirroring how `path` and
`test_cmd` are already resolved there - keeps the model self-contained and the
existing downstream `repo.remote` access unchanged.

### Why this shape

- The transport is a deployment/environment concern (does this machine use SSH
  keys or HTTPS tokens?), not a property of the repo itself. It belongs in
  `[settings]`, set once.
- `owner` + `name` is the minimal identity GitHub (and most forges) need.
  Everything else is derivable.
- Keeping a derived `remote` property means downstream code (`manager.py`,
  `git.clone`) can keep calling something that looks like a URL; the change is
  contained to the config layer. Low blast radius.

### Rejected / deferred alternatives

- **Keep `remote` but make it optional, derive when absent.** Hybrid configs
  are harder to reason about and document. Clean break confirmed: the only real
  configs are ones we own (sibling repo on the linux box), so we migrate them
  ourselves. No back-compat shim needed. (Q2 answered.)
- **Per-repo transport override.** Possible but probably YAGNI; a single global
  transport is the common case. Leave room for it (a per-repo optional
  `transport`) without building it now.
- **Full URL templating** (user supplies a format string with placeholders).
  More flexible, supports self-hosted/gitlab/custom SSH ports, but heavier.
  Defer unless a real need shows up.

## Resolved questions

1. **Field names.** ANS: pick consistent names; going with `owner` +
   `transport` + `repo_name` + `host`.
2. **Backward compatibility.** ANS: no shim. The only live configs are ours
   (sibling repo on the linux box, we own it); migrate them by hand alongside
   the schema change.
3. **Remote repo name vs local name.** ANS: yes, keep an optional `repo_name`
   override; when missing, populate it with `name`.
4. **Default host/transport.** ANS: confirmed `host = "github.com"`,
   `transport = "ssh"`.
5. **Self-hosted / non-GitHub forges.** ANS: no, not needed. The
   `git@host:owner/repo` and `https://host/owner/repo` forms are enough; no
   custom SSH user/port.
6. **`deps.py` consistency.** ANS: leave it alone. Confirmed in code:
   `update_pyproject` (deps.py:303) only string-replaces the tag
   (`@current_tag` -> `@latest_tag`) and preserves the rest of each dep line
   verbatim. Nothing ever *builds* a git-dep URL from scratch, so there is no
   consumer for the new `owner`/`host`/`transport` fields and no link to forge.
   Linking them would mean having repomgr regenerate the full `git+...` URL in a
   consumer's pyproject from the source repo's config - which we explicitly do
   not want; it would fight the formatting-preserving string replacement.

## Migration follow-up

The sibling config is at
`~/repos/linux-box-cloudflare/configs/repomgr/repos.toml` (28 `[[repo]]`
entries). Findings from reading it - they confirm the design:

- Every `remote` is `git@github.com:Pitrified/<repo>.git`. So uniformly
  `owner = "Pitrified"`, `host = "github.com"`, `transport = "ssh"`. The
  proposed defaults match 100% of real entries; after migration each repo only
  needs `owner` (and a global `[settings]` could even default `owner`, see
  below).
- `name` matches the remote repo name in 27 of 28 entries. Exactly one needs
  the `repo_name` override: `convo_craft` (local) -> `convo-craft` (remote,
  hyphen not underscore). This is the concrete case that justifies keeping
  `repo_name` optional (Q3).

Migration when the schema phase lands (decided to use a global owner default):

- Add `owner = "Pitrified"` to `[settings]` once.
- Delete every per-repo `remote = "..."` line (all 28 inherit the global owner).
- Add `repo_name = "convo-craft"` to the `convo_craft` entry only.
- `host`/`transport` rely on defaults (`github.com` / `ssh`).

Net: the whole file collapses to a one-line global addition plus a single
per-repo override - no per-repo `owner` needed anywhere, since none deviate.

## Consistency check + hidden future problems

Done on branch `feat/config-owner-repo` after the brainstorm settled. The design
holds, but the following were missed or under-stated above.

### 1. Blast radius is the tests, not `manager.py` (correction)

"Consumed in exactly one place / low blast radius" is true only for `src/`
runtime (`manager.py:112`). Removing the `remote` field breaks ~7 test files
that construct `RepoConfig(remote=...)` directly or put `remote =` in TOML
fixtures:
`tests/test_health.py:22`, `tests/test_cli.py:36`, `tests/test_update.py:44`,
`tests/test_manager.py:45,225`, `tests/test_deps.py:45`, and many cases in
`tests/config/test_repos_config.py`. Updating these is the bulk of the work and
must be its own explicit step in the phasing, not an afterthought.

### 2. Stored `remote` vs computed property - drift risk (revise the lean)

The brainstorm leans toward "store a `remote` field, populated in
`load_config()`." But `RepoConfig` is a public model constructed directly in
tests (and potentially by users). If `remote` is just a stored string while
`owner`/`repo_name` are separate fields, the two can disagree (owner says X,
remote URL says Y) - no single source of truth. Two options:

- (a) `remote` stays a required stored string set by `load_config()`. Simple,
  but direct constructors must pass it and inconsistency is possible.
- (b) Resolve `owner`/`repo_name`/`host`/`transport` onto each `RepoConfig` at
  load time and expose `remote` as a `@computed_field`/property derived from
  them. Single source of truth, no drift; direct construction stays ergonomic
  (pass the parts, get the URL for free).

Recommend (b). It does mean copying the resolved `host`/`transport` (which live
in `[settings]`) onto each `RepoConfig`, but that is the price of a
self-contained model and is what makes the derived URL trustworthy.

### 3. `transport = "https"` does NOT provide authentication (real trap)

This is the sharpest hidden problem. Today everything is SSH, which uses the
user's keys. Offering `transport = "https"` makes HTTPS a first-class choice,
but HTTPS clone/fetch/push against **private** repos needs a credential
(token or a configured git credential helper). Setting `transport = "https"`
alone will hang on a prompt or fail for private repos. Note in docs that https
is safe for public repos or where a credential helper is set up, and that it
does not itself authenticate. This is exactly the gap the **deferred GitHub App
auth phase** (`scratch_space/03-package-begin/11-github-auth.md`) was written
for: "becomes relevant when moving to HTTPS-only git remotes." So this feature
makes that deferred phase reachable - link them.

### 4. `transport` needs an enum + validation

Add a `Transport(StrEnum)` (`ssh` / `https`) mirroring `Role`, so a typo in the
TOML raises a clear validation error instead of silently producing a broken
URL. Cheap, belongs in the schema phase.

### 5. Non-issues confirmed (so future-me does not re-investigate)

- **State file**: `RepoState` keys on `name` and stores sha/tags/timestamps,
  never `remote` (`state.py`). No state migration needed.
- **`sample_config.py`**: unrelated - it is the Config/Params pattern demo, not
  the repos.toml schema. Untouched.
- **`name` -> local path mapping**: unchanged. The clone still lands at
  `base_path / name`; only URL derivation changes. For `convo_craft` the local
  dir stays `convo_craft` while the remote is `convo-craft` - identical to
  today's behaviour, now expressed via `repo_name`.

### 6. Minor: normalise `repo_name`

Consider stripping a trailing `.git` from `repo_name`/`name` before building the
URL (the template appends `.git`), so a user who writes `repo_name = "foo.git"`
does not get `foo.git.git`. Repos with dots in the name (`pitrified.github.io`)
are fine - only a literal trailing `.git` is the hazard. Low priority.

## Notes for phasing (later)

Likely phases once the brainstorm is settled:

1. Schema change in `repos_config.py`: `Transport` enum, `[settings].owner/host/
   transport`, per-repo `owner`/`repo_name`, resolution in `load_config()`, and
   `remote` as a computed property (option (b) above). Update
   `tests/config/test_repos_config.py` in the same phase.
2. Sweep `remote` consumers + fixtures: `manager.py` (no code change expected if
   `repo.remote` still resolves) and the direct-construction tests in
   `test_health/cli/update/manager/deps`.
3. Update `repos.toml.example` and docs (`docs/library/repos_config.md`),
   including the https-needs-auth caveat and the link to the deferred GitHub App
   phase.
4. Migrate the live config
   `~/repos/linux-box-cloudflare/configs/repomgr/repos.toml` (one global `owner`
   line + the single `convo_craft` -> `convo-craft` `repo_name`). No back-compat
   shim - clean break (Q2).

Not writing `tracking.md` or sub-plans yet - brainstorm only, per request.
