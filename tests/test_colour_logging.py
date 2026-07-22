"""Colour console logging for shared service bootstrap."""

from __future__ import annotations

import logging
from io import StringIO

import pytest

from libs.utils.logging import (
    ColourFormatter,
    colour_enabled,
    configure_logging,
)


def test_colour_formatter_marks_info_warn_error() -> None:
    formatter = ColourFormatter("%(levelname)s %(message)s")
    info = formatter.format(
        logging.LogRecord(
            name="t",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="ok",
            args=(),
            exc_info=None,
        )
    )
    warn = formatter.format(
        logging.LogRecord(
            name="t",
            level=logging.WARNING,
            pathname=__file__,
            lineno=1,
            msg="careful",
            args=(),
            exc_info=None,
        )
    )
    err = formatter.format(
        logging.LogRecord(
            name="t",
            level=logging.ERROR,
            pathname=__file__,
            lineno=1,
            msg="bad",
            args=(),
            exc_info=None,
        )
    )
    assert "\033[32mINFO\033[0m" in info
    assert "\033[33mWARNING\033[0m" in warn
    assert "\033[31mERROR\033[0m" in err


def test_colour_enabled_respects_no_color(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.delenv("LOG_COLOR", raising=False)
    assert colour_enabled() is False


def test_colour_enabled_always(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("LOG_COLOR", "always")
    assert colour_enabled() is True


def test_configure_logging_applies_colour_formatter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("LOG_COLOR", "always")
    monkeypatch.setenv("LOG_LEVEL", "INFO")
    configure_logging(service_name="pipeline-worker")

    root = logging.getLogger()
    assert root.level == logging.INFO
    assert any(isinstance(h.formatter, ColourFormatter) for h in root.handlers)

    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(ColourFormatter("%(levelname)s %(message)s"))
    log = logging.getLogger("pipeline-worker.colour-test")
    log.handlers = [handler]
    log.propagate = False
    log.setLevel(logging.INFO)
    log.info("hello")
    log.warning("heads-up")
    log.error("fail")
    out = stream.getvalue()
    assert "\033[32mINFO\033[0m" in out
    assert "\033[33mWARNING\033[0m" in out
    assert "\033[31mERROR\033[0m" in out
