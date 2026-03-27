# Phase 1b - State Persistence

## Goal

Provide a `StateStore` class that reads/writes `repos.state.json` and a `RepoState` model
that captures per-repo runtime state (fetch times, test results, update outcomes).

## File

`src/repomgr/state.py`

## Design decisions

### StateStore as a connector

`StateStore` is the **only** module that touches the state file. No other module imports
`json` for state purposes. The backing implementation is JSON today; it could be swapped
to SQLite later without changing any caller.

### `get()` never raises

`StateStore.get(name)` returns a `RepoState` with all optional fields as `None` for
unknown names. This makes callers simpler - no existence checks needed before first use.

### Atomic writes

State is written via write-to-temp + `os.rename()` to prevent corruption from partial writes.

## `RepoState` model

```python
@dataclass
class RepoState:
    name: str

    # Populated after fetch
    last_fetch_at: datetime | None = None
    last_seen_main_sha: str | None = None
    new_tags_since_last_fetch: list[str] = field(default_factory=list)

    # Populated after update-deps run
    last_update_run_at: datetime | None = None
    last_update_result: str | None = None  # "ok" | "failed_tests" | "skipped" | "no_updates"

    # Populated after test run
    last_test_run_at: datetime | None = None
    last_test_passed: bool | None = None
```

Using a `dataclass` (not Pydantic) since this is internal state, not user-facing config.
Dates serialize as ISO 8601 strings.

## `StateStore` public API

```python
class StateStore:
    def __init__(self, path: Path) -> None:
        """Load state from JSON file. Create empty state if file doesn't exist."""

    def get(self, name: str) -> RepoState:
        """Return state for a repo. Returns empty RepoState if not found."""

    def save(self, state: RepoState) -> None:
        """Update state for a single repo and write to disk."""

    def get_all(self) -> list[RepoState]:
        """Return all stored repo states."""

    def save_all(self, states: list[RepoState]) -> None:
        """Replace all states and write to disk."""
```

## JSON format

```json
{
  "llm-core": {
    "name": "llm-core",
    "last_fetch_at": "2026-03-27T09:14:00",
    "last_seen_main_sha": "abc1234",
    "new_tags_since_last_fetch": [],
    "last_update_run_at": null,
    "last_update_result": null,
    "last_test_run_at": null,
    "last_test_passed": null
  }
}
```

## Serialization helpers

Private methods on `StateStore`:
- `_to_dict(state: RepoState) -> dict` - convert to JSON-serializable dict (datetime to ISO string)
- `_from_dict(data: dict) -> RepoState` - parse ISO strings back to datetime
- `_flush() -> None` - atomic write (write to `.tmp`, then `os.rename`)
- `_load() -> None` - read JSON into internal `dict[str, RepoState]`

## Tests

`tests/test_state.py`

Test cases:
- `test_empty_state_file` - get returns empty RepoState
- `test_get_unknown_name` - returns empty RepoState (no raise)
- `test_save_and_get` - round-trip a RepoState
- `test_save_preserves_other_repos` - saving one doesn't clobber others
- `test_get_all` - returns all stored states
- `test_save_all` - replaces all states
- `test_datetime_serialization` - ISO 8601 round-trip
- `test_persistence_across_instances` - write with one instance, read with another
- `test_missing_file_creates_empty` - StateStore works with non-existent path
- `test_atomic_write` - file is not corrupted mid-write (check via temp file)

All tests use `tmp_path` fixture.

## Dependencies

- `json` (stdlib)
- `dataclasses` (stdlib)
- `datetime` (stdlib)
- No external dependencies
