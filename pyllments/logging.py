"""
Pyllments logging: framework diagnostics vs. process-owned sink setup.

Embedded / headless usage
    Import pyllments only. Logs stay disabled (see ``pyllments.__init__``).
    Optionally call ``configure_diagnostics(True)`` for payload-flow traces
    without adding sinks.

Local debugging / serve / CLI
    Call ``setup_serve_logging(...)`` (or ``setup_logging(..., replace_existing=True)``)
    to configure stdout/file sinks and optionally enable diagnostics.
"""
import sys
from typing import List, Optional

from loguru import logger

# Re-export for ``from pyllments.logging import logger``
__all__ = [
    "logger",
    "configure_diagnostics",
    "diagnostics_enabled",
    "setup_logging",
    "setup_serve_logging",
    "log_staging",
    "log_emit",
    "log_receive",
    "log_connect",
]

_DIAGNOSTICS_ENABLED = False
_DIAGNOSTICS_LEVEL = "TRACE"
_PYLLMENTS_SINK_IDS: List[int] = []

LOG_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
    "<level>{level:^8}</level> | "
    "<cyan>{extra[element]}</cyan> | "
    "{message}"
)


def configure_diagnostics(enabled: bool = False, level: str = "TRACE"):
    """
    Enable or disable detailed framework diagnostics (port payload-flow helpers).

    This does not configure Loguru sinks. Safe to call in embedded hosts that
    manage their own logging/telemetry.

    Parameters
    ----------
    enabled : bool, optional
        Whether port-flow diagnostic helpers should emit records, by default False.
    level : str, optional
        Loguru level used for diagnostic records, by default ``TRACE``.
    """
    global _DIAGNOSTICS_ENABLED, _DIAGNOSTICS_LEVEL

    _DIAGNOSTICS_ENABLED = enabled
    _DIAGNOSTICS_LEVEL = level.upper()


def diagnostics_enabled() -> bool:
    """Return whether detailed framework diagnostics are enabled."""
    return _DIAGNOSTICS_ENABLED


def _remove_pyllments_sinks() -> None:
    """Remove sinks previously added by this module."""
    global _PYLLMENTS_SINK_IDS
    for sink_id in _PYLLMENTS_SINK_IDS:
        try:
            logger.remove(sink_id)
        except ValueError:
            pass
    _PYLLMENTS_SINK_IDS = []


def setup_logging(
    log_file: Optional[str] = None,
    stdout_log_level: str = "DEBUG",
    file_log_level: str = "DEBUG",
    file_log_mode: str = "w",
    enqueue: bool = False,
    enable_diagnostics: bool = False,
    diagnostics_level: str = "TRACE",
    replace_existing: bool = False,
):
    """
    Configure Loguru sinks for Pyllments framework logs.

    By default (``replace_existing=False``), existing process sinks are preserved.
    Use this when Pyllments is embedded inside another application.

    For Pyllments-owned processes (CLI, ``serve``), prefer :func:`setup_serve_logging`.

    Parameters
    ----------
    log_file : str, optional
        Optional file path. When unset, output is stdout-only.
    stdout_log_level : str, optional
        Minimum level for stdout sink.
    file_log_level : str, optional
        Minimum level for file sink when ``log_file`` is set.
    file_log_mode : str, optional
        File open mode for the file sink.
    enqueue : bool, optional
        Whether Loguru should enqueue records (background thread).
    enable_diagnostics : bool, optional
        Whether to enable port payload-flow diagnostics.
    diagnostics_level : str, optional
        Level for diagnostic helpers when enabled.
    replace_existing : bool, optional
        If True, remove all Loguru sinks before adding Pyllments sinks.
        If False, only replace sinks previously added by this module.

    Returns
    -------
    loguru.Logger
        The configured logger instance.
    """
    logger.enable("pyllments")
    logger.configure(extra={"element": ""})

    if replace_existing:
        logger.remove()
        _remove_pyllments_sinks()
    else:
        _remove_pyllments_sinks()

    _PYLLMENTS_SINK_IDS.append(
        logger.add(
            sys.stdout,
            level=stdout_log_level,
            format=LOG_FORMAT,
            enqueue=enqueue,
        )
    )

    if log_file:
        _PYLLMENTS_SINK_IDS.append(
            logger.add(
                log_file,
                rotation="10 MB",
                level=file_log_level,
                format=LOG_FORMAT,
                mode=file_log_mode,
                enqueue=enqueue,
            )
        )

    configure_diagnostics(enabled=enable_diagnostics, level=diagnostics_level)
    return logger


def setup_serve_logging(
    log_file: Optional[str] = None,
    stdout_log_level: str = "INFO",
    file_log_level: str = "INFO",
    file_log_mode: str = "w",
    enqueue: bool = False,
    enable_diagnostics: bool = False,
    diagnostics_level: str = "TRACE",
):
    """
    Configure logging for Pyllments CLI / ``serve`` entrypoints.

    Replaces existing Loguru sinks so the served process has a single clear
    logging configuration. Enables the ``pyllments`` namespace and optionally
    framework diagnostics.

    Parameters
    ----------
    log_file : str, optional
        Optional file path. When unset, output is stdout-only.
    stdout_log_level : str, optional
        Minimum level for stdout sink, by default ``INFO``.
    enable_diagnostics : bool, optional
        Enable port payload-flow diagnostic helpers, by default False.
    diagnostics_level : str, optional
        Level for diagnostics when enabled.

    Returns
    -------
    loguru.Logger
        The configured logger instance.
    """
    return setup_logging(
        log_file=log_file,
        stdout_log_level=stdout_log_level,
        file_log_level=file_log_level,
        file_log_mode=file_log_mode,
        enqueue=enqueue,
        enable_diagnostics=enable_diagnostics,
        diagnostics_level=diagnostics_level,
        replace_existing=True,
    )


def _diagnostic_logger(port: object):
    element = getattr(port, "containing_element", None)
    return getattr(element, "logger", logger)


def log_staging(port: object, item_name: str, item_value: any):
    """Log a staged port item (diagnostics only; no-op when diagnostics disabled)."""
    if not _DIAGNOSTICS_ENABLED:
        return

    _diagnostic_logger(port).log(
        _DIAGNOSTICS_LEVEL,
        "Staging: {} | Staged Item: {}: {}",
        port.name,
        item_name,
        type(item_value).__name__,
    )


def log_emit(port: object, payload: object):
    """Log a port emission (diagnostics only)."""
    if not _DIAGNOSTICS_ENABLED:
        return

    _diagnostic_logger(port).log(
        _DIAGNOSTICS_LEVEL,
        "Emitting from {} | Payload: {}",
        port.name,
        type(payload).__name__,
    )


def log_receive(port: object, payload: object):
    """Log a port reception (diagnostics only)."""
    if not _DIAGNOSTICS_ENABLED:
        return

    _diagnostic_logger(port).log(
        _DIAGNOSTICS_LEVEL,
        "Receiving | Port: {} | Payload: {}",
        port.name,
        type(payload).__name__,
    )


def log_connect(output_port: object, input_port: object):
    """Log a port connection (diagnostics only)."""
    if not _DIAGNOSTICS_ENABLED:
        return

    output_element_type = output_port.containing_element.__class__.__name__
    input_element_type = input_port.containing_element.__class__.__name__

    _diagnostic_logger(output_port).log(
        _DIAGNOSTICS_LEVEL,
        "Connecting {} | Port: {} to {} | Port: {}",
        input_element_type,
        input_port.name,
        output_element_type,
        output_port.name,
    )
