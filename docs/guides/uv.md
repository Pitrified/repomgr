# UV package manager

## Dependencies group

To add a package to a specific group, use the `--group` option:

```bash
uv add --group lint ruff
```

## Upgrade packages

Upgrades the lock, but not the dependencies in `pyproject.toml`.

```bash
uv add --dev --upgrade-package pyright "pyright[nodejs]"
```

If you want to upgrade the dependencies in `pyproject.toml`, use:

```bash
uv add --dev "pyright[nodejs]>=1.2.3"
```

If you want to upgrade the lock for all packages, use:

```bash
uv lock --upgrade
uv sync
```
