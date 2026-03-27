"""Deployment environment type."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import os

from loguru import logger as lg


class EnvStageType(Enum):
    """Deployment environment stage type."""

    DEV = "dev"
    PROD = "prod"

    @classmethod
    def from_env_var(cls, default_env: str = "dev") -> EnvStageType:
        """Get the environment from the environment variable ``ENV_STAGE_TYPE``.

        Args:
            default_env (str): The default environment.
                Defaults to "dev".

        Returns:
            EnvStageType: The environment type.
        """
        env = os.getenv("ENV_STAGE_TYPE", default_env)
        lg.success(f"EnvStageType: {env}")
        return EnvStageType(env)


class EnvLocationType(Enum):
    """Deployment environment location type."""

    LOCAL = "local"
    RENDER = "render"

    @classmethod
    def from_env_var(cls, default_env: str = "local") -> EnvLocationType:
        """Get the environment from the environment variable ``ENV_LOCATION_TYPE``.

        Args:
            default_env (str): The default environment.
                Defaults to "local".

        Returns:
            EnvLocationType: The environment type.
        """
        env = os.getenv("ENV_LOCATION_TYPE", default_env)
        lg.success(f"EnvLocationType: {env}")
        return EnvLocationType(env)


class UnknownEnvLocationError(Exception):
    """Raised when an unknown or unsupported environment location is encountered.

    Args:
        location (EnvLocationType): the environment location that caused the error
    """

    def __init__(self, location: EnvLocationType) -> None:
        """Initialize with the invalid location.

        Args:
            location: The unknown environment location
        """
        self.location = location
        message = f"Unknown environment location: {location}"
        super().__init__(message)


class UnknownEnvStageError(Exception):
    """Raised when an unknown or unsupported environment stage is encountered.

    Args:
        stage (EnvStageType): the environment stage that caused the error
    """

    def __init__(self, stage: EnvStageType) -> None:
        """Initialize with the invalid stage.

        Args:
            stage: The unknown environment stage
        """
        self.stage = stage
        message = f"Unknown environment stage: {stage}"
        super().__init__(message)


@dataclass
class EnvType:
    """Deployment environment type."""

    stage: EnvStageType
    location: EnvLocationType

    @classmethod
    def from_env_var(cls) -> EnvType:
        """Initialize the environment from environment variables."""
        stage = EnvStageType.from_env_var()
        location = EnvLocationType.from_env_var()
        return EnvType(stage, location)

    def __str__(self) -> str:
        """Return the string representation of the environment."""
        return f"EnvType: {self.stage.value}-{self.location.value}"
