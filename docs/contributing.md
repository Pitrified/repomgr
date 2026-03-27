# Contributing

Thank you for your interest in contributing to this project!

## Development Setup

1. Fork and clone the repository
2. Install dependencies: `uv sync --group dev`
3. Install pre-commit hooks: `uv run pre-commit install`

## Code Style

This project uses:

- **Ruff** for linting and formatting
- **Pyright** for type checking
- **Pre-commit** hooks for automated checks

### Style Guidelines

```python
# ✅ Good: Clear typing, early returns, descriptive names
from loguru import logger as lg

def fetch_entity(table: str, entity_id: str | None) -> dict:
    if entity_id is None:
        msg = "entity_id required"
        raise ValueError(msg)

    lg.info(f"Fetching {entity_id} from {table}")
    return {"id": entity_id, "table": table}
```

## Pull Request Process

1. Create a feature branch from `main`
2. Make your changes with clear, focused commits
3. Ensure all tests pass: `uv run pytest`
4. Ensure code quality checks pass: `uv run ruff check . && uv run pyright`
5. Update documentation if needed
6. Submit a pull request

## Commit Messages

Use conventional commit style:

```
type(scope): description

feat(config): add environment variable validation
fix(params): handle missing path gracefully
docs(readme): update installation instructions
test(models): add edge case coverage
```

## Testing

- Write tests for new functionality
- Place tests in `tests/` mirroring the `src/` structure
- Use descriptive test names: `test_function_does_expected_behavior`

```bash
# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov=src/repomgr
```

## Documentation

- Update docs when adding new features
- Include usage examples in docstrings
- Build and preview locally: `uv run mkdocs serve`

## Questions?

Open an issue for any questions or concerns.
