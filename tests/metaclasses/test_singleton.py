"""Test the Singleton metaclass."""

from repomgr.metaclasses.singleton import Singleton


class SingletonClass(metaclass=Singleton):
    """A test class using the Singleton metaclass."""

    def __init__(self) -> None:
        """Initialize the class."""
        self.value = 0


def test_singleton_instance() -> None:
    """Test that multiple instantiations return the same object."""
    instance1 = SingletonClass()
    instance2 = SingletonClass()

    assert instance1 is instance2
    assert id(instance1) == id(instance2)


def test_singleton_state() -> None:
    """Test that state is shared across instances."""
    instance1 = SingletonClass()
    instance1.value = 42

    instance2 = SingletonClass()
    assert instance2.value == 42
