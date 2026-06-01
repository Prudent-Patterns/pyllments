import io
import sys

import pytest
from loguru import logger

from pyllments.logging import (
    configure_diagnostics,
    diagnostics_enabled,
    log_connect,
    log_emit,
    log_receive,
    log_staging,
    setup_logging,
    setup_serve_logging,
)


@pytest.fixture(autouse=True)
def reset_diagnostics():
    configure_diagnostics(False)
    yield
    configure_diagnostics(False)


@pytest.fixture(autouse=True)
def reset_loguru_sinks():
    """Isolate Loguru configuration between tests."""
    logger.remove()
    yield
    logger.remove()


class ExplodingElement:
    @property
    def logger(self):
        raise AssertionError("disabled diagnostics should not access element loggers")


class FakePort:
    def __init__(self, name="port", element=None):
        self.name = name
        self.containing_element = element or ExplodingElement()


def test_port_diagnostics_are_disabled_by_default():
    assert diagnostics_enabled() is False

    output_port = FakePort("out")
    input_port = FakePort("in")

    log_staging(output_port, "payload", object())
    log_emit(output_port, object())
    log_receive(input_port, object())
    log_connect(output_port, input_port)


def test_port_diagnostics_emit_when_enabled():
    records = []

    class RecordingLogger:
        def log(self, level, message, *args):
            records.append((level, message.format(*args)))

    element = type("ElementWithLogger", (), {"logger": RecordingLogger()})()
    output_port = FakePort("out", element)
    input_port = FakePort("in", element)

    configure_diagnostics(True, level="DEBUG")

    log_staging(output_port, "payload", object())
    log_emit(output_port, object())
    log_receive(input_port, object())
    log_connect(output_port, input_port)

    assert records == [
        ("DEBUG", "Staging: out | Staged Item: payload: object"),
        ("DEBUG", "Emitting from out | Payload: object"),
        ("DEBUG", "Receiving | Port: in | Payload: object"),
        ("DEBUG", "Connecting ElementWithLogger | Port: in to ElementWithLogger | Port: out"),
    ]


def test_setup_logging_embedded_preserves_existing_sink():
    host_output = io.StringIO()
    host_sink = logger.add(host_output, format="{message}", level="DEBUG")

    setup_logging(stdout_log_level="INFO", replace_existing=False)

    logger.debug("host-visible")
    assert "host-visible" in host_output.getvalue()

    logger.remove(host_sink)


def test_setup_serve_logging_replaces_existing_sinks():
    host_output = io.StringIO()
    logger.add(host_output, format="{message}", level="DEBUG")

    setup_serve_logging(stdout_log_level="INFO")

    logger.info("serve-only")
    # After replace, prior sink should not receive records
    assert host_output.getvalue() == ""


def test_setup_logging_without_log_file_is_stdout_only():
    setup_serve_logging(stdout_log_level="INFO", enable_diagnostics=True)

    assert diagnostics_enabled() is True
    # No exception and diagnostics flag set; file sink is optional API only
    setup_serve_logging(log_file=None, enable_diagnostics=False)
    assert diagnostics_enabled() is False


def test_configure_diagnostics_without_setup_logging():
    """Embedded hosts can enable traces without configuring sinks."""
    configure_diagnostics(True, level="TRACE")
    assert diagnostics_enabled() is True
