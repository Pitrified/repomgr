---
status: done
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

## Done when

- [x] `repos.toml.example` parses and matches the new schema (verified by
  loading it via `load_config`: all 5 derived URLs correct, including
  `convo_craft` -> `convo-craft` and the per-repo owner override).
- [x] Docs describe owner/repo_name/transport and the https-auth caveat.

## What was done

- `repos.toml.example`: `[settings]` gained `owner`/`host`/`transport` with the
  https-auth note; `[[repo]]` entries dropped `remote`; added a `repo_name`
  example (`convo_craft` -> `convo-craft`) and a per-repo `owner` override
  example; updated the "Required fields" comment.
- `docs/library/repos_config.md`: added a `Transport` section with a
  material-theme `!!! warning` admonition on https-not-authenticating (links
  the deferred GitHub App phase); updated the Settings and RepoConfig tables;
  extended the resolution order (owner, host/transport) and the `load_config`
  raises list (`OwnerNotResolvedError`, unknown transport).
- `docs/getting-started.md` and `docs/guides/user-guide.md`: updated the toml
  examples and the user-guide reference tables.
- Left `docs/library/deps.md` git-dep URLs alone (they are pyproject
  `git+ssh://...` lines, unrelated to repos.toml - see 00-start Q6).
