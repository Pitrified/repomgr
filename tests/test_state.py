"""Tests for the state module."""

from datetime import UTC
from datetime import datetime
import json
from pathlib import Path

import pytest

from repomgr.state import RepoState
from repomgr.state import StateStore

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_store(tmp_path: Path) -> StateStore:
    return StateStore(tmp_path / "repos.state.json")


def _make_state(name: str = "my-repo") -> RepoState:
    return RepoState(
        name=name,
        last_fetch_at=datetime(2026, 3, 27, 9, 14, 0, tzinfo=UTC),
        last_seen_main_sha="abc1234",
        new_tags_since_last_fetch=["v1.2.0"],
        last_update_run_at=datetime(2026, 3, 27, 10, 0, 0, tzinfo=UTC),
        last_update_result="ok",
        last_test_run_at=datetime(2026, 3, 27, 10, 1, 0, tzinfo=UTC),
        last_test_passed=True,
    )


# ---------------------------------------------------------------------------
# StateStore - initialisation
# ---------------------------------------------------------------------------


def test_missing_file_creates_empty(tmp_path: Path) -> None:
    """StateStore initialises cleanly even when the JSON file does not exist."""
    store = StateStore(tmp_path / "nonexistent.json")
    assert store.get_all() == []


def test_empty_state_file(tmp_path: Path) -> None:
    """An empty JSON object on disk yields no stored states."""
    p = tmp_path / "repos.state.json"
    p.write_text("{}", encoding="utf-8")
    store = StateStore(p)
    assert store.get_all() == []


# ---------------------------------------------------------------------------
# StateStore.get
# ---------------------------------------------------------------------------


def test_get_unknown_name_returns_empty_repo_state(tmp_path: Path) -> None:
    """get() never raises; returns empty RepoState for unknown names."""
    store = _make_store(tmp_path)
    result = store.get("unknown")
    assert isinstance(result, RepoState)
    assert result.name == "unknown"
    assert result.last_fetch_at is None
    assert result.last_seen_main_sha is None
    assert result.new_tags_since_last_fetch == []
    assert result.last_update_run_at is None
    assert result.last_update_result is None
    assert result.last_test_run_at is None
    assert result.last_test_passed is None


def test_get_returns_saved_state(tmp_path: Path) -> None:
    """get() retrieves a previously saved state by name."""
    store = _make_store(tmp_path)
    state = _make_state("repo-a")
    store.save(state)
    result = store.get("repo-a")
    assert result.name == "repo-a"
    assert result.last_seen_main_sha == "abc1234"


# ---------------------------------------------------------------------------
# StateStore.save
# ---------------------------------------------------------------------------


def test_save_and_get_round_trip(tmp_path: Path) -> None:
    """A state written with save() is returned intact by get()."""
    store = _make_store(tmp_path)
    state = _make_state()
    store.save(state)
    result = store.get("my-repo")
    assert result.name == state.name
    assert result.last_fetch_at == state.last_fetch_at
    assert result.last_seen_main_sha == state.last_seen_main_sha
    assert result.new_tags_since_last_fetch == state.new_tags_since_last_fetch
    assert result.last_update_run_at == state.last_update_run_at
    assert result.last_update_result == state.last_update_result
    assert result.last_test_run_at == state.last_test_run_at
    assert result.last_test_passed == state.last_test_passed


def test_save_preserves_other_repos(tmp_path: Path) -> None:
    """Saving one repo does not overwrite other repos already in the store."""
    store = _make_store(tmp_path)
    store.save(RepoState(name="repo-a", last_seen_main_sha="aaa"))
    store.save(RepoState(name="repo-b", last_seen_main_sha="bbb"))
    assert store.get("repo-a").last_seen_main_sha == "aaa"
    assert store.get("repo-b").last_seen_main_sha == "bbb"


# ---------------------------------------------------------------------------
# StateStore.get_all / save_all
# ---------------------------------------------------------------------------


def test_get_all_returns_all_stored_states(tmp_path: Path) -> None:
    """get_all() returns every stored repo state."""
    store = _make_store(tmp_path)
    store.save(RepoState(name="repo-a"))
    store.save(RepoState(name="repo-b"))
    all_states = store.get_all()
    names = {s.name for s in all_states}
    assert names == {"repo-a", "repo-b"}


def test_save_all_replaces_existing_states(tmp_path: Path) -> None:
    """save_all() replaces the entire store contents."""
    store = _make_store(tmp_path)
    store.save(RepoState(name="old-repo"))
    store.save_all([RepoState(name="new-repo-1"), RepoState(name="new-repo-2")])
    all_states = store.get_all()
    names = {s.name for s in all_states}
    assert names == {"new-repo-1", "new-repo-2"}
    assert store.get("old-repo").last_fetch_at is None  # returns empty, not old data


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def test_datetime_serialization_round_trip(tmp_path: Path) -> None:
    """Datetimes survive a full serialize/deserialize cycle unchanged."""
    store = _make_store(tmp_path)
    dt = datetime(2026, 3, 27, 9, 14, 0, tzinfo=UTC)
    state = RepoState(name="dt-repo", last_fetch_at=dt, last_test_run_at=dt)
    store.save(state)

    store2 = StateStore(tmp_path / "repos.state.json")
    result = store2.get("dt-repo")
    assert result.last_fetch_at == dt
    assert result.last_test_run_at == dt


def test_none_datetimes_stay_none(tmp_path: Path) -> None:
    """None datetime fields remain None after deserialization."""
    store = _make_store(tmp_path)
    store.save(RepoState(name="bare"))
    store2 = StateStore(tmp_path / "repos.state.json")
    result = store2.get("bare")
    assert result.last_fetch_at is None
    assert result.last_update_run_at is None
    assert result.last_test_run_at is None


def test_json_format_on_disk(tmp_path: Path) -> None:
    """The on-disk JSON is keyed by repo name and contains expected fields."""
    p = tmp_path / "repos.state.json"
    store = StateStore(p)
    store.save(RepoState(name="check-repo", last_seen_main_sha="deadbeef"))

    raw = json.loads(p.read_text(encoding="utf-8"))
    assert "check-repo" in raw
    entry = raw["check-repo"]
    assert entry["name"] == "check-repo"
    assert entry["last_seen_main_sha"] == "deadbeef"
    assert "last_fetch_at" in entry


# ---------------------------------------------------------------------------
# Persistence across instances
# ---------------------------------------------------------------------------


def test_persistence_across_instances(tmp_path: Path) -> None:
    """Data written by one StateStore instance is read correctly by another."""
    p = tmp_path / "repos.state.json"
    first = StateStore(p)
    first.save(_make_state("persist-repo"))

    second = StateStore(p)
    result = second.get("persist-repo")
    assert result.last_seen_main_sha == "abc1234"
    assert result.last_update_result == "ok"
    assert result.last_test_passed is True


# ---------------------------------------------------------------------------
# Atomic write
# ---------------------------------------------------------------------------


def test_atomic_write_uses_tmp_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """_flush() writes to a .tmp file then renames it; no .tmp remains after write."""
    p = tmp_path / "repos.state.json"
    store = StateStore(p)
    store.save(RepoState(name="atomic-test"))

    # The final file must exist and the staging .tmp file must be gone
    assert p.exists()
    tmp_file = p.with_suffix(".tmp")
    assert not tmp_file.exists()
