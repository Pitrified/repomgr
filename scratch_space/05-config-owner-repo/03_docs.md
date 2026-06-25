---
status: draft
---

# Phase 3 - Update `repos.toml.example` + docs

## Overview

Document the new schema for users: replace `remote =` with `owner`/`repo_name`
and the global `[settings]` `owner`/`host`/`transport`.

Context: [`00-start.md`](00-start.md), depends on
[`01_schema.md`](01_schema.md).

## Goals (draft)

1. Rewrite `repos.toml.example`: `[settings]` gains `owner`/`host`/`transport`;
   `[[repo]]` entries use `owner`/`repo_name` instead of `remote`; update the
   "Required fields" comment.
2. Update `docs/library/repos_config.md` narrative.
3. Add the caveat that `transport = "https"` does not itself authenticate
   (needs a token / credential helper), with a pointer to the deferred GitHub
   App phase (`scratch_space/03-package-begin/11-github-auth.md`).

## Done when (draft)

- `repos.toml.example` parses and matches the new schema.
- Docs describe owner/repo_name/transport and the https-auth caveat.

Detail this phase fully before starting it.
