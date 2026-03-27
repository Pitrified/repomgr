"""Base model which can be converted to dict at only the top level of attributes.

Useful to send config values using **config.to_kw() to functions.
"""

from pydantic import BaseModel


class BaseModelKwargs(BaseModel):
    """Base model with to_kw method."""

    def to_kw(
        self,
        *,
        exclude_none: bool = False,
    ) -> dict:
        """Convert the model to a dictionary, flattening any 'kwargs' attribute.

        Args:
            exclude_none (bool): Whether to exclude None values. Defaults to False.
        """
        base_dict = (
            {k: v for k, v in self if v is not None} if exclude_none else dict(self)
        )

        # Flatten kwargs if it exists and is a dict
        if "kwargs" in base_dict:
            kwargs_value = base_dict.pop("kwargs")
            if isinstance(kwargs_value, dict):
                # Filter None values from kwargs if exclude_none is True
                if exclude_none:
                    kwargs_filtered = {
                        k: v for k, v in kwargs_value.items() if v is not None
                    }
                    base_dict.update(kwargs_filtered)
                else:
                    base_dict.update(kwargs_value)
            else:
                # Put kwargs back if it's not a dict
                base_dict["kwargs"] = kwargs_value

        return base_dict
