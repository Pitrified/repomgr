---
status: draft
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

## Done when (draft)

- `repomgr --config <that file> status` works against the migrated config
  (verifies the derived URLs match the previous `remote` values).
- Change committed in the linux-box-cloudflare repo.

Detail this phase fully before starting it.
