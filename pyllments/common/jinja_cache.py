"""Jinja2 templates compiled once per source, not once per render."""

from functools import lru_cache

import jinja2

_STRICT = jinja2.Environment(undefined=jinja2.StrictUndefined)


@lru_cache(maxsize=128)
def strict_template(source: str) -> jinja2.Template:
    """``source`` compiled with StrictUndefined; the same source compiles once."""
    return _STRICT.from_string(source)
