---
status: done
---

# Phase 4 - Migrate the live linux-box config

## Overview

Migrate the one real config we own to the new schema. This lives in a sibling
repo, so it is a separate change committed there, not in repomgr.

Context: [`00-start.md`](00-start.md) (Migration follow-up), depends on
[`01_schema.md`](01_schema.md) (and ideally a released/installed repomgr build).

## Goals (draft)

Edit `~/repos/linux-box-cloudflare/configs/repomgr/repos.toml`:

1. Add `owner = "Pitrified"` to `[settings]` once.
2. Delete all 28 per-repo `remote = "..."` lines.
3. Add `repo_name = "convo-craft"` to the `convo_craft` entry only.
4. Leave `host`/`transport` on defaults (`github.com` / `ssh`).

## Done when

- [x] Config migrated: global `owner = "Pitrified"` + `host`/`transport`,
  all 28 `remote =` lines removed, `repo_name = "convo-craft"` on `convo_craft`.
  `recipamatic`'s `test_cmd` override preserved.
- [x] Derived URLs verified identical to the old `remote` values via
  `load_config` (28 repos, spot-checked llm-core / convo-craft /
  pitrified.github.io / Pitrified / recipamatic).
- [x] `repomgr status`, `dep-graph`, and `clone-missing` run cleanly against
  the migrated config (`--config <path>`). status renders all 28 repos and the
  dep graph; clone-missing is a no-op (all on disk).
- [ ] Commit in the linux-box-cloudflare repo - left to the user (no commit
  was requested for that repo; the file is migrated and verified, ready to
  review/commit there).

## Notes

- `clone-missing` could not exercise a real `git clone` because every repo is
  already on disk; the derived-URL equality check above is what confirms the
  clone path would receive the same URLs as before.
