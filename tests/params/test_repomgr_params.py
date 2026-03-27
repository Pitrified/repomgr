"""Test the RepomgrParams class."""

from repomgr.params.repomgr_params import RepomgrParams
from repomgr.params.repomgr_params import get_repomgr_params
from repomgr.params.repomgr_paths import RepomgrPaths
from repomgr.params.sample_params import SampleParams


def test_repomgr_params_singleton() -> None:
    """Test that RepomgrParams is a singleton."""
    params1 = RepomgrParams()
    params2 = RepomgrParams()
    assert params1 is params2
    assert get_repomgr_params() is params1


def test_repomgr_params_init() -> None:
    """Test initialization of RepomgrParams."""
    params = RepomgrParams()
    assert isinstance(params.paths, RepomgrPaths)
    assert isinstance(params.sample, SampleParams)


def test_repomgr_params_str() -> None:
    """Test string representation."""
    params = RepomgrParams()
    s = str(params)
    assert "RepomgrParams:" in s
    assert "RepomgrPaths:" in s
    assert "SampleParams:" in s
