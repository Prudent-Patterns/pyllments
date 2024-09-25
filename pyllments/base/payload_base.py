from functools import wraps
from inspect import signature
from pathlib import Path
import warnings
import re

import param

from pyllments.base.component_base import Component

class Payload(Component):
    css_cache = param.Dict(default={}, instantiate=False, per_instance=False,
        doc="""Cache for CSS files - Set on the Class Level""")
    view_cache = param.Dict(default={}, doc="""
        Cache for views - Set on the Instance Level""")

    def __init__(self, **params):
        super().__init__(**params)

    @staticmethod
    def _load_css(key, module_path):
        """Load CSS from a file, returning an empty string if not found."""
        css_path = Path(module_path, 'css', f'{key}.css')
        try:
            with css_path.open('r') as file:
                return file.read()
        except FileNotFoundError:
            warnings.warn(f"CSS file not found: {css_path}")
        except Exception as e:
            warnings.warn(f"Error loading CSS: {str(e)}")
        return ''