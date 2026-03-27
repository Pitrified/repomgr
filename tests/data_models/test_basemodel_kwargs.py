"""Test the BaseModelKwargs data model."""

from repomgr.data_models.basemodel_kwargs import BaseModelKwargs


class ModelForTest(BaseModelKwargs):
    """Test model for BaseModelKwargs."""

    a: int
    b: str | None = None
    kwargs: dict | None = None


def test_to_kw_basic() -> None:
    """Test basic to_kw functionality."""
    model = ModelForTest(a=1, b="test")
    assert model.to_kw() == {"a": 1, "b": "test", "kwargs": None}


def test_to_kw_exclude_none() -> None:
    """Test to_kw with exclude_none=True."""
    model = ModelForTest(a=1, b=None)
    assert model.to_kw(exclude_none=True) == {"a": 1}
    assert model.to_kw(exclude_none=False) == {"a": 1, "b": None, "kwargs": None}


def test_to_kw_flatten_kwargs() -> None:
    """Test flattening of kwargs."""
    model = ModelForTest(a=1, kwargs={"c": 3, "d": 4})
    expected = {"a": 1, "b": None, "c": 3, "d": 4}
    assert model.to_kw() == expected


def test_to_kw_flatten_kwargs_exclude_none() -> None:
    """Test flattening of kwargs with exclude_none=True."""
    model = ModelForTest(a=1, kwargs={"c": 3, "d": None})
    expected = {"a": 1, "c": 3}
    assert model.to_kw(exclude_none=True) == expected


def test_to_kw_kwargs_not_dict() -> None:
    """Test behavior when kwargs is not a dict.

    This should not happen with type hint but good for robustness.
    """

    # Override type hint for testing
    class ModelForTestBadKwargs(BaseModelKwargs):
        a: int
        kwargs: int  # type: ignore[assignment]

    model = ModelForTestBadKwargs(a=1, kwargs=5)
    assert model.to_kw() == {"a": 1, "kwargs": 5}
