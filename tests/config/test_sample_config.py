"""Test the SampleConfig class."""

from pydantic import SecretStr

from repomgr.config.sample_config import NestedModel
from repomgr.config.sample_config import SampleConfig


def test_sample_config_init() -> None:
    """Test initialization of SampleConfig."""
    nested = NestedModel(some_str="test")
    config = SampleConfig(
        some_int=1,
        nested_model=nested,
        secret_api_key=SecretStr("test-key"),
    )

    assert config.some_int == 1
    assert config.nested_model.some_str == "test"
    assert config.kwargs == {}


def test_sample_config_secret_str() -> None:
    """Test that secret_api_key is stored as SecretStr."""
    nested = NestedModel(some_str="test")
    config = SampleConfig(
        some_int=1,
        nested_model=nested,
        secret_api_key=SecretStr("my-secret"),
    )

    # SecretStr masks the value in repr/str
    assert "my-secret" not in repr(config)
    # Raw value is accessible via get_secret_value()
    assert config.secret_api_key.get_secret_value() == "my-secret"


def test_sample_config_with_kwargs() -> None:
    """Test initialization with kwargs."""
    nested = NestedModel(some_str="test")
    config = SampleConfig(
        some_int=1,
        nested_model=nested,
        secret_api_key=SecretStr("test-key"),
        kwargs={"extra": "value"},
    )

    assert config.kwargs == {"extra": "value"}


def test_sample_config_to_kw() -> None:
    """Test to_kw method inherited from BaseModelKwargs."""
    nested = NestedModel(some_str="test")
    config = SampleConfig(
        some_int=1,
        nested_model=nested,
        secret_api_key=SecretStr("test-key"),
        kwargs={"extra": "value"},
    )

    kw = config.to_kw()
    assert kw["some_int"] == 1
    assert kw["nested_model"] == nested
    assert kw["extra"] == "value"
    assert "kwargs" not in kw
