import sys
import inspect
import warnings
from functools import wraps
from pathlib import Path
from uuid import uuid4

import param

from pyllments.base.model_base import Model


class Component(param.Parameterized):
    """Base class for all components(Elements and Payloads)"""
    model = param.ClassSelector(class_=Model)
    id = param.String()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.id = str(uuid4())

    @classmethod
    def _get_module_path(cls):
        """
        Gets the path of the class's module in which it is defined.
        Gets the path of the child, not the parent class if the class is subclassed.
        """
        # Get the module where the class is defined
        module = sys.modules[cls.__module__]
        # Return the parent directory of the module's file
        return Path(module.__file__).parent

    def _view_exists(self, view):
        if view:
            warnings.warn(f'{view} already exists. Returning existing view.')
            return True
    
    def __hash__(self):
        """Return a hash of the component's id for use in hash-based collections."""
        return hash(self.id)

    def __eq__(self, other):
        """Check equality based on the component's id."""
        if not isinstance(other, Component):
            return NotImplemented
        return self.id == other.id