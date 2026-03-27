"""Sample config - shape-only definition of settings.

This module is the reference implementation of the Config side of the
Config / Params pattern.  It lives in ``src/repomgr/config/`` and
defines only the *shape* of settings: typed fields, default factories, and
validation.  It never reads environment variables, files, or any runtime
state.  All of that belongs in the paired Params class
(``src/repomgr/params/sample_params.py``).

Pattern rules for Config models:
* Extend ``BaseModelKwargs``, not plain ``BaseModel``.
* Use ``SecretStr`` for any sensitive value (API keys, passwords, tokens).
  Pydantic masks the value in ``repr`` and log output automatically.
* Use an optional ``kwargs: dict`` field (default empty) when the config
  will be forwarded to a third-party constructor via ``to_kw()``.
* Never import or call ``os``, ``load_dotenv``, or anything that reads
  runtime state.

See Also:
    ``SampleParams`` - the companion Params class that loads actual values.
    ``docs/guides/params_config.md`` - full guide with examples and rationale.
"""

from pydantic import Field
from pydantic import SecretStr

from repomgr.data_models.basemodel_kwargs import BaseModelKwargs


class NestedModel(BaseModelKwargs):
    """Nested config model.

    Demonstrates that config models can be composed.  A parent config
    holds nested models as regular Pydantic fields; they round-trip cleanly
    through ``to_kw()`` and JSON serialisation.
    """

    some_str: str


class SampleConfig(BaseModelKwargs):
    """Sample config - reference shape for a config model.

    Attributes:
        some_int:
            A plain integer setting.  The value appropriate for each
            deployment environment is determined by the paired ``SampleParams``
            class.
        nested_model:
            Demonstrates config composition: a parent config holds a
            ``NestedModel`` sub-config as a typed field.
        secret_api_key:
            A sensitive value stored as ``SecretStr``.  Pydantic masks it
            automatically in ``repr`` / ``str`` output.  To obtain the raw
            string call ``config.secret_api_key.get_secret_value()``.
        kwargs:
            Extra arguments merged into the top-level dictionary when
            ``to_kw()`` is called.  Use this to forward arbitrary keyword
            arguments to a third-party constructor without listing every one
            explicitly.

    Example:
        Always produce a ``SampleConfig`` via the paired ``SampleParams``
        class, never by hand-constructing it in application code::

            from repomgr.params.env_type import EnvType
            from repomgr.params.sample_params import SampleParams

            params = SampleParams(env_type)
            config = params.to_config()
            # access the secret only when truly needed:
            raw_key = config.secret_api_key.get_secret_value()
    """

    some_int: int
    nested_model: NestedModel
    secret_api_key: SecretStr
    kwargs: dict = Field(default_factory=dict)
