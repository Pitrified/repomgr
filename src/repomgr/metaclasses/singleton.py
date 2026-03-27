"""Singleton metaclass.

https://stackoverflow.com/questions/6760685/what-is-the-best-way-of-implementing-singleton-in-python
"""

from typing import ClassVar


class Singleton(type):
    """Singleton metaclass."""

    _instances: ClassVar = {}

    def __call__(cls, *args, **kwargs):  # noqa: ANN002, ANN003, ANN204
        """Singleton instance creation."""
        if cls not in cls._instances:
            cls._instances[cls] = super().__call__(*args, **kwargs)
        return cls._instances[cls]
