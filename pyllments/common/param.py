from typing import Union, get_origin, get_args
import param

from pyllments.base.payload_base import Payload

class PayloadType(param.ClassSelector):
    """Holds the typing signature of the Payload"""

    
class PayloadSelector(param.ClassSelector):
    """
    PayloadSelector is a parameterized class that validates whether a given value
    is an instance of a specified Payload subclass or a list of Payload instances.

    This class extends the functionality of param.ClassSelector to enforce type
    constraints specifically for Payloads, ensuring that only valid Payload types
    are accepted.

    Parameters:
    - class_: A class or list of classes that are subclasses of Payload. 
              It can be None, in which case any Payload instance is accepted.
    - **params: Additional parameters passed to the parent ClassSelector.

    Validation Logic:
    - If class_ is not None, it must be a subclass of Payload or a list of Payload subclasses.
    - The _validate method checks the value against the specified class_ and raises
      ValueErrors if the value does not conform to the expected type.
    """

    def __init__(self, class_=None, **params):
        if class_ is not None:
            if not (issubclass(class_, Payload) or
                    (get_origin(class_) in (list, Union) and
                     all(issubclass(arg, Payload) for arg in get_args(class_)))):
                raise ValueError(
                    "class_ must be a Payload subclass, "
                    "List[PayloadSubclass], Union[PayloadSubclass, ...], or None"
                )
        super().__init__(class_=class_, **params)

    def _validate(self, val):
        """
        Validates the provided value against the expected Payload type.

        Parameters:
        - val: The value to validate.

        Returns:
        - The validated value if it conforms to the expected type.

        Raises:
        - ValueError: If the value does not match the expected type.
        """
        if val is None and self.allow_None:
            return None

        if isinstance(val, type):
            raise ValueError(f"Expected an instance, got a class: {val}")

        if self.class_ is None:
            if not isinstance(val, Payload) and not (
                isinstance(val, list) and
                all(isinstance(item, Payload) for item in val)
            ):
                raise ValueError(
                    f"Expected a Payload instance or a list of "
                    f"Payload instances, got {type(val)}"
                )
        elif get_origin(self.class_) is list:
            if not isinstance(val, list):
                raise ValueError(
                    f"Expected a list of {get_args(self.class_)[0]}, "
                    f"got {type(val)}"
                )
            item_type = get_args(self.class_)[0]
            if not all(self._is_instance(item, item_type) for item in val):
                raise ValueError(
                    f"All items in the list must be instances of "
                    f"{item_type}"
                )
        elif get_origin(self.class_) is Union:
            if not any(self._is_instance(val, arg) for arg in get_args(self.class_)):
                raise ValueError(
                    f"Expected an instance of one of {get_args(self.class_)}, "
                    f"got {type(val)}"
                )
        else:
            if not self._is_instance(val, self.class_):
                raise ValueError(
                    f"Expected an instance of {self.class_}, "
                    f"got {type(val)}"
                )

        return val

    def _is_instance(self, obj, class_or_tuple):
        """
        A custom implementation of isinstance that can handle generic types.
        """
        if get_origin(class_or_tuple) is Union:
            return any(self._is_instance(obj, arg) for arg in get_args(class_or_tuple))
        elif get_origin(class_or_tuple) is list:
            return isinstance(obj, list) and all(self._is_instance(item, get_args(class_or_tuple)[0]) for item in obj)
        else:
            return isinstance(obj, class_or_tuple)