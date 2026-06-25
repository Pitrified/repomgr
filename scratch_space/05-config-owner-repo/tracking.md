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
| 1  | Schema + load_config + config tests    | [`01_schema.md`](01_schema.md)    | planned |
| 2  | Sweep `remote` consumers + fixtures    | [`02_consumers.md`](02_consumers.md) | draft   |
| 3  | Update `repos.toml.example` + docs      | [`03_docs.md`](03_docs.md)        | draft   |
| 4  | Migrate live linux-box config           | [`04_migrate.md`](04_migrate.md)  | draft   |

Status values: draft / planned / in progress / done / superseded / discarded.

## Log

Append-only. Newest at the bottom.

- 2026-06-25 : bootstrapped plan folder; brainstorm in 00-start.md, branch
  `feat/config-owner-repo` created, brainstorm committed (79fcb08).
- 2026-06-25 : added tracking.md and fleshed out phase 1 (`01_schema.md`);
  phases 2-4 stubbed as draft.
