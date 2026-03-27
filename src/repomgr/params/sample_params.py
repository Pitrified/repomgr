"""Sample params - canonical reference implementation of the Params pattern.

This module is the *authoritative example* of how to write a Params class
in this project.  It pairs with ``SampleConfig`` in
``src/repomgr/config/sample_config.py``.

Config / Params split:

* **Config** (``src/repomgr/config/``) defines only the *shape* of
  settings using Pydantic models.  It never reads environment variables.
* **Params** (this file) loads *actual values* and constructs the config
  model via ``to_config()``.

Pattern rules:

1. ``__init__`` accepts ``env_type: EnvType | None = None`` as its only
   argument beyond ``self``.  Pass it explicitly when you have it; it
   will be inferred from environment variables when ``None``.  Keeping
   the argument present - even when not yet needed - makes the API
   consistent and future-proof across all Params classes.

2. ``__init__`` does nothing except store ``env_type`` and call
   ``_load_params()``.  Keep it as a one-liner delegation so the loading
   logic is easy to test in isolation.

3. ``_load_params()`` orchestrates loading in a fixed order:

   a. ``_load_common_params()`` - attributes shared across **all** envs.
   b. Dispatch on ``env_type.stage`` (DEV / PROD) via ``match``; each
      branch sets or overrides stage-specific attributes and then
      dispatches further on ``env_type.location`` (LOCAL / RENDER).

4. ``_load_common_params()`` writes values as **Python literals**, not
   ``os.getenv()`` calls.  If a value is the same in every environment,
   write it once here.  If it changes between environments, set it only
   in the relevant stage or location method - never duplicate it.

5. **Secrets** are the exception to the no-env-var rule: load them from
   environment variables using the module-level ``_load_secret()`` helper.
   It uses ``os.environ[VAR]``, which raises ``KeyError`` naturally when
   the variable is missing - no custom exception is needed.  This
   surfaces broken configurations at startup rather than at the point of
   use.

6. ``to_config()`` constructs and returns the Pydantic config model.

7. ``__str__`` produces a human-readable summary.  Every secret field
   must be rendered as ``[REDACTED]`` - never call
   ``.get_secret_value()`` inside ``__str__``.

See Also:
    ``SampleConfig`` - the paired config model in ``src/repomgr/config/``.
    ``docs/guides/params_config.md`` - full guide with rationale.
"""

import os

from pydantic import SecretStr

from repomgr.config.sample_config import NestedModel
from repomgr.config.sample_config import SampleConfig
from repomgr.params.env_type import EnvLocationType
from repomgr.params.env_type import EnvStageType
from repomgr.params.env_type import EnvType
from repomgr.params.env_type import UnknownEnvLocationError
from repomgr.params.env_type import UnknownEnvStageError


def _load_secret(var_name: str) -> SecretStr:
    """Load a secret from an environment variable.

    Uses ``os.environ`` rather than ``os.getenv`` so that a missing
    variable raises ``KeyError`` immediately with the variable name.
    No custom exception is needed - the standard error is descriptive
    enough and avoids cluttering the codebase with one-off exception types.

    Args:
        var_name: Name of the environment variable to read.

    Returns:
        The secret value wrapped in ``SecretStr`` to prevent accidental
        logging or printing.

    Raises:
        KeyError: If the environment variable is not set.
    """
    return SecretStr(os.environ[var_name])


class SampleParams:
    """Sample params - reference implementation of the Params pattern.

    Loads actual runtime values for the given deployment environment and
    exposes a typed ``SampleConfig`` via ``to_config()``.

    Non-secret values are written as Python literals inside the appropriate
    loading method - not read from environment variables.  If a value
    differs between environments, write it only in the relevant stage or
    location method; do not repeat it across branches.

    Secrets are the exception: they are loaded via ``_load_secret()`` in
    ``_load_common_params()``, which means a missing secret is caught at
    startup.

    Args:
        env_type: Deployment environment (stage + location).  If ``None``,
            inferred from ``ENV_STAGE_TYPE`` and ``ENV_LOCATION_TYPE``
            environment variables (defaults: ``dev`` / ``local``).
    """

    def __init__(self, env_type: EnvType | None = None) -> None:
        """Load sample params for the given environment.

        Args:
            env_type: Deployment environment (stage + location).
                If ``None``, inferred from ``ENV_STAGE_TYPE`` and
                ``ENV_LOCATION_TYPE`` environment variables.
        """
        self.env_type: EnvType = env_type or EnvType.from_env_var()
        self._load_params()

    def _load_params(self) -> None:
        """Orchestrate loading: common first, then stage + location."""
        self._load_common_params()
        match self.env_type.stage:
            case EnvStageType.DEV:
                self._load_dev_params()
            case EnvStageType.PROD:
                self._load_prod_params()
            case _:
                raise UnknownEnvStageError(self.env_type.stage)

    def _load_common_params(self) -> None:
        """Set attributes shared across all environments.

        Non-secret values are Python literals here.  Secrets are loaded
        from environment variables via ``_load_secret()``; a missing
        variable surfaces as ``KeyError`` at startup, not silently later.
        """
        # Non-secret values: write as literals, not os.getenv()
        self.nested_model_some_str: str = "Hello, Params!"
        self.custom_kwargs: dict = {"key1": "value1", "key2": "value2"}
        # Secret: loaded from env; KeyError raised naturally if missing
        self.secret_api_key: SecretStr = _load_secret("SAMPLE_API_KEY")

    def _load_dev_params(self) -> None:
        """Set DEV-stage attributes, then dispatch on location.

        ``some_int`` is set here because it differs by stage but not by
        location within the stage.
        """
        self.some_int: int = 7
        match self.env_type.location:
            case EnvLocationType.LOCAL:
                self._load_dev_local_params()
            case EnvLocationType.RENDER:
                self._load_dev_render_params()
            case _:
                raise UnknownEnvLocationError(self.env_type.location)

    def _load_dev_local_params(self) -> None:
        """Set DEV + LOCAL overrides.

        No overrides needed beyond DEV stage defaults in this sample.
        """

    def _load_dev_render_params(self) -> None:
        """Set DEV + RENDER overrides."""
        self.nested_model_some_str = "Hello from Render (dev)!"

    def _load_prod_params(self) -> None:
        """Set PROD-stage attributes, then dispatch on location."""
        self.some_int = 42
        match self.env_type.location:
            case EnvLocationType.LOCAL:
                self._load_prod_local_params()
            case EnvLocationType.RENDER:
                self._load_prod_render_params()
            case _:
                raise UnknownEnvLocationError(self.env_type.location)

    def _load_prod_local_params(self) -> None:
        """Set PROD + LOCAL overrides.

        No overrides needed beyond PROD stage defaults in this sample.
        """

    def _load_prod_render_params(self) -> None:
        """Set PROD + RENDER overrides."""
        self.nested_model_some_str = "Hello from Render (prod)!"

    def to_config(self) -> SampleConfig:
        """Assemble and return the typed config model.

        Returns:
            SampleConfig: A Pydantic model carrying all settings.
                The secret is preserved as ``SecretStr``.
        """
        return SampleConfig(
            some_int=self.some_int,
            nested_model=NestedModel(some_str=self.nested_model_some_str),
            secret_api_key=self.secret_api_key,
            kwargs=self.custom_kwargs,
        )

    def __str__(self) -> str:
        """Return a human-readable summary with secrets masked."""
        s = "SampleParams:"
        s += f"\n  env_type: {self.env_type}"
        s += f"\n  some_int: {self.some_int}"
        s += f"\n  nested_model_some_str: {self.nested_model_some_str}"
        s += "\n  secret_api_key: [REDACTED]"
        s += f"\n  custom_kwargs: {self.custom_kwargs}"
        return s

    def __repr__(self) -> str:
        """Return the string representation of the object."""
        return str(self)
