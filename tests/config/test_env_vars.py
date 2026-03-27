"""Test that the environment variables are available."""

import os


def test_env_vars() -> None:
    """The environment var REPOMGR_SAMPLE_ENV_VAR is available."""
    assert "REPOMGR_SAMPLE_ENV_VAR" in os.environ
    assert os.environ["REPOMGR_SAMPLE_ENV_VAR"] == "sample"
