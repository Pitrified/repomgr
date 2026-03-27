"""Test the repomgr paths."""

from repomgr.params.repomgr_params import get_repomgr_paths


def test_repomgr_paths() -> None:
    """Test the repomgr paths."""
    repomgr_paths = get_repomgr_paths()
    assert repomgr_paths.src_fol.name == "repomgr"
    assert repomgr_paths.root_fol.name == "repomgr"
    assert repomgr_paths.data_fol.name == "data"
