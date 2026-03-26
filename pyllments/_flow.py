"""Internal marker for servable pyllments entrypoints."""

import functools


def flow(func):
    """Mark a function as a pyllments-served entrypoint."""
    func.pyllments_flow = True

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)

    return wrapper
