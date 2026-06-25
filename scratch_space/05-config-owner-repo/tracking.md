# implementation tracking

Rework `repos.toml` so each repo stores structured identity (`owner` +
`repo_name`) instead of a hard-coded `remote` URL, with global `[settings]`
`owner`/`host`/`transport` defaults; the clone URL is derived. Analysis and
decisions in [`00-start.md`](00-start.md).

## Key decisions

- `remote: str` is removed from the schema. The clone URL is derived from
  `transport` + `host` + `owner` + `repo_name`. (00-start, Proposed approach)
- `[settings]` gains `owner` (optional default), `host` (`github.com`),
  `transport` (`ssh`/`https`, default `ssh`). Per-repo `owner` and `repo_name`
  override; `repo_name` defaults to `name`. Per-repo must resolve an `owner`
  (own or global) or it is an error.
- `remote` is exposed as a **computed property** over resolved fields, not a
  stored string - single source of truth, no drift (00-start, hidden problem 2).
- Clean break: no back-compat for the old `remote =` field (Q2). Tests and the
  one live config are migrated by hand.
- `transport = "https"` does not provide auth - documented caveat, links to the
  deferred GitHub App phase (00-start, hidden problem 3).

## Phases

| #  | Phase                                  | Plan                              | Status  |
| -- | -------------------------------------- | --------------------------------- | ------- |
| 1  | Schema + load_config + config tests    | [`01_schema.md`](01_schema.md)    | done    |
| 2  | Sweep `remote` consumers + fixtures    | [`02_consumers.md`](02_consumers.md) | done    |
| 3  | Update `repos.toml.example` + docs      | [`03_docs.md`](03_docs.md)        | draft   |
| 4  | Migrate live linux-box config           | [`04_migrate.md`](04_migrate.md)  | draft   |

Status values: draft / planned / in progress / done / superseded / discarded.

## Log

Append-only. Newest at the bottom.

- 2026-06-25 : bootstrapped plan folder; brainstorm in 00-start.md, branch
  `feat/config-owner-repo` created, brainstorm committed (79fcb08).
- 2026-06-25 : added tracking.md and fleshed out phase 1 (`01_schema.md`);
  phases 2-4 stubbed as draft.
- 2026-06-25 : phase 1 done. `repos_config.py`: added `Transport` enum and
  `OwnerNotResolvedError`; `Settings` gained `owner`/`host`/`transport`;
  `RepoConfig` dropped the `remote` field for `owner`/`repo_name`/`host`/
  `transport` with `remote` as a computed property; `load_config()` resolves
  owner (repo->global) and copies host/transport per repo. Rewrote
  `tests/config/test_repos_config.py` (29 pass), ruff clean. Confirmed the
  phase-2 worklist by running the full suite: failures isolated to
  `test_cli`, `test_deps`, `test_health`, `test_manager`, `test_update`
  (all `remote=` fixture/construction references, as predicted).
- 2026-06-25 : phase 2 done. Replaced `remote=` with `owner=` in the
  `RepoConfig` constructions/fixtures of `test_health`, `test_deps`,
  `test_manager`, `test_update` and the TOML fixture in `test_cli`. No `src/`
  change needed - `manager.py` `repo.remote` resolves via the computed
  property, and `test_manager.py:225`'s `clone_mock` assertion still matches
  the derived URL. Full suite green: 209 passed, ruff clean.
