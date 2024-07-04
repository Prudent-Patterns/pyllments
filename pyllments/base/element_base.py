import warnings

import param

from .model_base import Model
from ..ports import Ports

class Element(param.Parameterized):

    """Base class for all elements in the framework"""
    model = param.ClassSelector(class_=Model, default=None)
    ports = param.ClassSelector(class_=Ports)

    def __init__(self, **params):
        super().__init__(**params)
        self.ports = Ports(containing_element=self)

    def _view_exists(self, view):
        if view:
            warnings.warn(f'{view} already exists. Returning existing view.')
            return True