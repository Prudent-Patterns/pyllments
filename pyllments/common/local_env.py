"""A local .env for the laptop editions; the light edition ships without python-dotenv."""

from functools import cache


@cache
def _dotenv_loader():
    try:
        from dotenv import load_dotenv
    except ImportError:
        return None
    return load_dotenv


def load_local_env() -> None:
    """Read a local .env without overriding variables already set, if python-dotenv is installed."""
    loader = _dotenv_loader()
    if loader is not None:
        loader(override=False)
