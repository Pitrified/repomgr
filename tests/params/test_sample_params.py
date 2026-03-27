"""Test the SampleParams class."""

from repomgr.config.sample_config import SampleConfig
from repomgr.params.env_type import EnvLocationType
from repomgr.params.env_type import EnvStageType
from repomgr.params.env_type import EnvType
from repomgr.params.sample_params import SampleParams

_DEV_LOCAL = EnvType(stage=EnvStageType.DEV, location=EnvLocationType.LOCAL)
_DEV_RENDER = EnvType(stage=EnvStageType.DEV, location=EnvLocationType.RENDER)
_PROD_LOCAL = EnvType(stage=EnvStageType.PROD, location=EnvLocationType.LOCAL)
_PROD_RENDER = EnvType(stage=EnvStageType.PROD, location=EnvLocationType.RENDER)


def test_sample_params_dev_local() -> None:
    """Test DEV + LOCAL defaults."""
    params = SampleParams(env_type=_DEV_LOCAL)
    assert params.some_int == 7
    assert params.nested_model_some_str == "Hello, Params!"
    assert params.custom_kwargs == {"key1": "value1", "key2": "value2"}


def test_sample_params_dev_render() -> None:
    """Test DEV + RENDER overrides."""
    params = SampleParams(env_type=_DEV_RENDER)
    assert params.some_int == 7
    assert params.nested_model_some_str == "Hello from Render (dev)!"


def test_sample_params_prod_local() -> None:
    """Test PROD + LOCAL defaults."""
    params = SampleParams(env_type=_PROD_LOCAL)
    assert params.some_int == 42
    assert params.nested_model_some_str == "Hello, Params!"


def test_sample_params_prod_render() -> None:
    """Test PROD + RENDER overrides."""
    params = SampleParams(env_type=_PROD_RENDER)
    assert params.some_int == 42
    assert params.nested_model_some_str == "Hello from Render (prod)!"


def test_sample_params_secret_loaded() -> None:
    """Test that the secret is loaded and stored as SecretStr."""
    params = SampleParams(env_type=_DEV_LOCAL)
    # The value comes from the conftest.py env var override
    assert params.secret_api_key.get_secret_value() == "test-api-key-do-not-use-in-prod"


def test_sample_params_to_config() -> None:
    """Test conversion to SampleConfig."""
    params = SampleParams(env_type=_DEV_LOCAL)
    config = params.to_config()

    assert isinstance(config, SampleConfig)
    assert config.some_int == 7
    assert config.nested_model.some_str == "Hello, Params!"
    assert config.kwargs == {"key1": "value1", "key2": "value2"}
    assert config.secret_api_key.get_secret_value() == "test-api-key-do-not-use-in-prod"


def test_sample_params_str_masks_secret() -> None:
    """Test that __str__ masks the secret."""
    params = SampleParams(env_type=_DEV_LOCAL)
    s = str(params)
    assert "SampleParams:" in s
    assert "[REDACTED]" in s
    assert "test-api-key" not in s


def test_sample_params_str_contains_key_fields() -> None:
    """Test that __str__ shows non-secret fields."""
    params = SampleParams(env_type=_DEV_LOCAL)
    s = str(params)
    assert "some_int" in s
    assert "nested_model_some_str" in s
