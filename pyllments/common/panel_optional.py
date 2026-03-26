"""Lazy import for Panel (optional GUI dependency)."""


def import_panel():
    """Import and return the ``panel`` module, or raise a clear error if missing."""
    try:
        import panel as pn
    except ImportError as exc:
        raise ImportError(
            "Pyllments GUI views require the 'panel' package. "
            "Install it (e.g. pip install panel) or avoid calling @Component.view methods."
        ) from exc
    return pn
