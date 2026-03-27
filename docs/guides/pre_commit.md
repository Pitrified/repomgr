# Pre commit

## Maintenance of the file

### Manually check the latest release versions

For

- pre-commit hooks versions
- yelp detect-secrets

1. open the repo link
2. go to releases
3. get the latest stable version

### Match the uv versions of the tools

For repos:

- uv itself
- ruff
- pyright
- nbstripout

1. update the tool with [uv](./uv.md)

   ```bash
   uv lock --upgrade-package ruff
   uv lock --upgrade-package pyright
   ```

2. run the command to get the version

   ```bash
   uv run ruff --version
   uv run pyright --version
   ```

3. update the rev in the precommit file (note that some revs have a "v" prefix)
