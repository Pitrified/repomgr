"""Per-repo runtime state persistence.

This module provides ``StateStore``, the single point of contact for reading
and writing ``repos.state.json``.  No other module imports ``json`` for state
purposes.

The backing format is a flat JSON object keyed by repo name.  Each value is a
dict that maps directly to the ``RepoState`` dataclass fields.  Dates are
serialized as ISO 8601 strings.

Pattern rules:
    ``StateStore.get()`` never raises - it returns an empty ``RepoState`` for
    any name not yet seen.  Writes use a write-to-temp-then-rename strategy
    to prevent partial writes from corrupting the file.
"""

from dataclasses import dataclass
from dataclasses import field
from datetime import datetime
import json
from pathlib import Path


@dataclass
class RepoState:
    """Per-repo runtime state.

    Attributes:
        name:
            Unique short name of the repository (matches ``RepoConfig.name``).
        last_fetch_at:
            Timestamp of the most recent successful ``git fetch``.
        last_seen_main_sha:
            Full SHA of the main branch tip at the last fetch.
        new_tags_since_last_fetch:
            Tags that appeared since the previous fetch run.
        last_update_run_at:
            Timestamp of the most recent dep-update run.
        last_update_result:
            Outcome of the most recent dep-update run.
            One of ``"ok"``, ``"failed_tests"``, ``"skipped"``,
            ``"no_updates"``, or ``None`` if never run.
        last_test_run_at:
            Timestamp of the most recent test run.
        last_test_passed:
            Whether the most recent test run passed.
    """

    name: str

    last_fetch_at: datetime | None = None
    last_seen_main_sha: str | None = None
    new_tags_since_last_fetch: list[str] = field(default_factory=list)

    last_update_run_at: datetime | None = None
    last_update_result: str | None = None

    last_test_run_at: datetime | None = None
    last_test_passed: bool | None = None


class StateStore:
    """JSON-backed connector for per-repo ``RepoState``.

    All reads and writes to ``repos.state.json`` go through this class.

    Args:
        path: Absolute path to the state JSON file.  If the file does not
            exist it is created on first write.

    Example:
        Basic read/write cycle::

            store = StateStore(Path("/srv/repos.state.json"))
            state = store.get("my-repo")
            state.last_fetch_at = datetime.now()
            store.save(state)
    """

    def __init__(self, path: Path) -> None:
        """Load state from JSON file.  Create empty state if file does not exist."""
        self._path = path
        self._data: dict[str, RepoState] = {}
        self._load()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, name: str) -> RepoState:
        """Return state for a repo.

        Args:
            name: Repo short name.

        Returns:
            Stored ``RepoState`` or a fresh empty one if the name is unknown.
        """
        return self._data.get(name, RepoState(name=name))

    def save(self, state: RepoState) -> None:
        """Persist updated state for a single repo.

        Other repos already in the store are unaffected.

        Args:
            state: Updated ``RepoState`` to write.
        """
        self._data[state.name] = state
        self._flush()

    def get_all(self) -> list[RepoState]:
        """Return all stored repo states.

        Returns:
            List of ``RepoState`` objects in insertion order.
        """
        return list(self._data.values())

    def save_all(self, states: list[RepoState]) -> None:
        """Replace the entire store with the provided states and write to disk.

        Args:
            states: New set of states.  Replaces previous contents entirely.
        """
        self._data = {s.name: s for s in states}
        self._flush()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _load(self) -> None:
        """Read JSON from disk into ``self._data``."""
        if not self._path.exists():
            return
        raw = json.loads(self._path.read_text(encoding="utf-8"))
        self._data = {name: self._from_dict(d) for name, d in raw.items()}

    def _flush(self) -> None:
        """Write ``self._data`` to disk atomically."""
        tmp = self._path.with_suffix(".tmp")
        payload = {name: self._to_dict(s) for name, s in self._data.items()}
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp.rename(self._path)

    @staticmethod
    def _to_dict(state: RepoState) -> dict:
        """Serialize ``RepoState`` to a JSON-safe dict.

        Args:
            state: The state instance to serialize.

        Returns:
            Dict where all values are JSON-serializable.
        """

        def _iso(dt: datetime | None) -> str | None:
            return dt.isoformat() if dt else None

        return {
            "name": state.name,
            "last_fetch_at": _iso(state.last_fetch_at),
            "last_seen_main_sha": state.last_seen_main_sha,
            "new_tags_since_last_fetch": state.new_tags_since_last_fetch,
            "last_update_run_at": _iso(state.last_update_run_at),
            "last_update_result": state.last_update_result,
            "last_test_run_at": _iso(state.last_test_run_at),
            "last_test_passed": state.last_test_passed,
        }

    @staticmethod
    def _from_dict(data: dict) -> RepoState:
        """Deserialize a JSON dict to ``RepoState``.

        Args:
            data: Raw dict loaded from JSON.

        Returns:
            Populated ``RepoState`` instance.
        """

        def _dt(key: str) -> datetime | None:
            raw = data.get(key)
            return datetime.fromisoformat(raw) if raw else None

        return RepoState(
            name=data["name"],
            last_fetch_at=_dt("last_fetch_at"),
            last_seen_main_sha=data.get("last_seen_main_sha"),
            new_tags_since_last_fetch=data.get("new_tags_since_last_fetch", []),
            last_update_run_at=_dt("last_update_run_at"),
            last_update_result=data.get("last_update_result"),
            last_test_run_at=_dt("last_test_run_at"),
            last_test_passed=data.get("last_test_passed"),
        )
