from loguru import logger
from pyllments.serve import flow

try:
    from ._version import __version__  # noqa: F401
except ImportError:
    # This fallback is used when _version.py has not been generated yet
    # (e.g., in a fresh clone before running hatch version/build).
    # It matches the fallback-version in pyproject.toml.
    __version__ = "0.0.1"

logger.disable('pyllments')