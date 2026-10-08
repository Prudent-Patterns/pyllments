from pathlib import Path
import warnings

import param

from pyllments.base.component_base import Component

class Payload(Component):
    css_cache = param.Dict(default={}, instantiate=False, per_instance=False,
        doc="""Cache for CSS files - Set on the Class Level""")

    def __init__(self, **params):
        super().__init__(**params)

    @property
    def finished(self) -> bool:
        """
        Whether this payload will change no more.

        A payload that is still live (a reply being streamed, a tool call not yet
        run) is for an uptake element, which finishes or uses it and emits the
        finished form. A ledger element such as the history handler accepts only
        finished payloads. Payloads with no live state are always finished.
        """
        return True

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