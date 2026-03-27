# Params / Config Pattern

This guide explains the two-layer settings architecture used throughout
this project and shows how to apply it correctly when adding new
configuration.

## Overview

Settings are split into two layers:

| Layer | Location | Responsibility |
|---|---|---|
| **Config** | `src/repomgr/config/` | Defines the *shape* of settings as Pydantic models |
| **Params** | `src/repomgr/params/` | Loads *actual values* and produces a Config via `to_config()` |

**Config** models are pure data containers.  They define types, defaults,
and validation.  They never read environment variables, open files, or
perform any I/O.

**Params** classes are plain Python classes.  They read environment
variables, inspect `EnvType`, and hard-code environment-specific literals.
They expose the assembled settings as a typed Config model.

The reference implementations are:

- [`SampleConfig`](../../reference/repomgr/config/sample_config/) - config side
- [`SampleParams`](../../reference/repomgr/params/sample_params/) - params side

---

## Config layer

### Rules

1. Extend `BaseModelKwargs`, not plain `BaseModel`.
2. Use `SecretStr` for every sensitive field (API keys, passwords, tokens).
   Pydantic masks the value automatically in `repr` and log output.
3. Add an optional `kwargs: dict = Field(default_factory=dict)` when the
   config will be forwarded to a third-party constructor via `to_kw()`.
4. **Never** import `os`, call `load_dotenv`, or read any runtime state.

### Example

```python
from pydantic import Field, SecretStr
from repomgr.data_models.basemodel_kwargs import BaseModelKwargs


class NestedModel(BaseModelKwargs):
    some_str: str


class SampleConfig(BaseModelKwargs):
    some_int: int
    nested_model: NestedModel
    secret_api_key: SecretStr
    kwargs: dict = Field(default_factory=dict)
```

### Accessing secrets

Call `.get_secret_value()` only at the point where the raw value is
genuinely needed (e.g., when constructing an external client):

```python
config = params.to_config()
client = SomeClient(api_key=config.secret_api_key.get_secret_value())
```

---

## Params layer

### Rules

1. **Single constructor argument**: `env_type: EnvType | None = None`.
   Pass it explicitly from the caller (e.g., `RepomgrParams`).  When
   `None`, fall back to `EnvType.from_env_var()`.  Keep the argument
   present even if the class does not yet use it - consistency matters
   more than brevity here.

2. **Thin `__init__`**: store `env_type` and call `_load_params()`.
   Nothing else.

3. **`_load_params()` orchestration**:
   - Call `_load_common_params()` first.
   - Dispatch on `env_type.stage` (DEV / PROD) via `match`.
   - Each stage method dispatches further on `env_type.location`
     (LOCAL / RENDER) for fine-grained overrides.

4. **Literals, not `os.getenv()`**: write non-secret values as Python
   literals in the appropriate loading method.  Use the stage / location
   dispatch machinery to express the differences - do not duplicate
   values across branches.

5. **Secrets via `os.environ`**: load secrets with `os.environ[VAR]`
   (raises `KeyError` naturally - no custom exception needed) and wrap
   in `SecretStr`.  Centralise this in a module-level helper.

6. **`to_config()`**: assembles and returns the Pydantic config model.

7. **`__str__`**: render every secret field as `[REDACTED]`.

### Full example

```python
import os
from pydantic import SecretStr
from repomgr.params.env_type import (
    EnvLocationType, EnvStageType, EnvType,
    UnknownEnvLocationError, UnknownEnvStageError,
)
from repomgr.config.sample_config import NestedModel, SampleConfig


def _load_secret(var_name: str) -> SecretStr:
    return SecretStr(os.environ[var_name])


class SampleParams:
    def __init__(self, env_type: EnvType | None = None) -> None:
        self.env_type = env_type or EnvType.from_env_var()
        self._load_params()

    def _load_params(self) -> None:
        self._load_common_params()
        match self.env_type.stage:
            case EnvStageType.DEV:
                self._load_dev_params()
            case EnvStageType.PROD:
                self._load_prod_params()
            case _:
                raise UnknownEnvStageError(self.env_type.stage)

    def _load_common_params(self) -> None:
        # Non-secret: literal, same in every env
        self.nested_model_some_str: str = "Hello, Params!"
        self.custom_kwargs: dict = {"key1": "value1", "key2": "value2"}
        # Secret: KeyError raised naturally if var is missing
        self.secret_api_key: SecretStr = _load_secret("SAMPLE_API_KEY")

    def _load_dev_params(self) -> None:
        self.some_int: int = 7   # smaller value in dev
        match self.env_type.location:
            case EnvLocationType.LOCAL:
                self._load_dev_local_params()
            case EnvLocationType.RENDER:
                self._load_dev_render_params()
            case _:
                raise UnknownEnvLocationError(self.env_type.location)

    def _load_dev_local_params(self) -> None:
        pass  # no local-specific overrides needed

    def _load_dev_render_params(self) -> None:
        self.nested_model_some_str = "Hello from Render (dev)!"

    def _load_prod_params(self) -> None:
        self.some_int = 42
        match self.env_type.location:
            case EnvLocationType.LOCAL:
                self._load_prod_local_params()
            case EnvLocationType.RENDER:
                self._load_prod_render_params()
            case _:
                raise UnknownEnvLocationError(self.env_type.location)

    def _load_prod_local_params(self) -> None:
        pass

    def _load_prod_render_params(self) -> None:
        self.nested_model_some_str = "Hello from Render (prod)!"

    def to_config(self) -> SampleConfig:
        return SampleConfig(
            some_int=self.some_int,
            nested_model=NestedModel(some_str=self.nested_model_some_str),
            secret_api_key=self.secret_api_key,
            kwargs=self.custom_kwargs,
        )

    def __str__(self) -> str:
        s = "SampleParams:"
        s += f"\n  env_type:              {self.env_type}"
        s += f"\n  some_int:              {self.some_int}"
        s += f"\n  nested_model_some_str: {self.nested_model_some_str}"
        s += "\n  secret_api_key:        [REDACTED]"
        return s

    def __repr__(self) -> str:
        return str(self)
```

---

## Common mistakes

### Reading env vars for non-secret values

```python
# Wrong - do not read non-secrets from os.getenv()
self.host: str = os.getenv("WEBAPP_HOST", "0.0.0.0")

# Right - write the literal; use stage/location dispatch for differences
def _load_common_params(self) -> None:
    self.host: str = "0.0.0.0"

def _load_prod_render_params(self) -> None:
    self.host = "0.0.0.0"  # same here; only override what actually changes
```

### Custom exception for a missing env var

```python
# Wrong - unnecessary custom exception
token = os.getenv("BOT_TOKEN")
if not token:
    raise MissingTokenError("BOT_TOKEN not set")

# Right - os.environ raises KeyError with the variable name
self._token = _load_secret("BOT_TOKEN")
```

### Calling `__init__` with logic beyond delegation

```python
# Wrong - logic in __init__
def __init__(self, env_type: EnvType) -> None:
    self.env_type = env_type
    self.host = "0.0.0.0"   # should be in _load_common_params
    if env_type.stage == EnvStageType.PROD:
        self.host = "server.example.com"

# Right - __init__ only delegates
def __init__(self, env_type: EnvType | None = None) -> None:
    self.env_type = env_type or EnvType.from_env_var()
    self._load_params()
```

---

## How it fits into ParamsParams

`RepomgrParams` (the top-level singleton) owns all Params instances
and passes the resolved `EnvType` to each one:

```python
class RepomgrParams(metaclass=Singleton):
    def load_config(self) -> None:
        self.paths = RepomgrPaths(env_type=self.env_type)
        self.sample = SampleParams(env_type=self.env_type)
        ...
```

This ensures that the whole application agrees on a single `EnvType`
determined once at startup.

---

## Testing

In tests, always pass an explicit `env_type` to avoid relying on
environment variables:

```python
from repomgr.params.env_type import EnvLocationType, EnvStageType, EnvType
from repomgr.params.sample_params import SampleParams

DEV_LOCAL = EnvType(stage=EnvStageType.DEV, location=EnvLocationType.LOCAL)

def test_dev_local_defaults() -> None:
    params = SampleParams(env_type=DEV_LOCAL)
    assert params.some_int == 7
```

Secrets required by `_load_common_params` should be set before the
first `SampleParams` instantiation.  The root `tests/conftest.py` does
this with `os.environ.setdefault(...)`:

```python
# tests/conftest.py
import os
os.environ.setdefault("SAMPLE_API_KEY", "test-api-key-do-not-use-in-prod")
```
