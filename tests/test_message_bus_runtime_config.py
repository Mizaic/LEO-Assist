"""Tests for Service Bus runtime config logging helpers."""

from __future__ import annotations

import logging

from libs.message_bus.runtime_config import (
    connection_string_endpoint,
    describe_message_bus_runtime,
    log_message_bus_startup,
    normalize_service_bus_host,
)


def test_connection_string_endpoint_parses_sb_host() -> None:
    conn = (
        "Endpoint=sb://leoai-val-bus.servicebus.windows.net/;"
        "SharedAccessKeyName=RootManageSharedAccessKey;"
        "SharedAccessKey=secret-not-logged"
    )
    assert (
        connection_string_endpoint(conn) == "sb://leoai-val-bus.servicebus.windows.net"
    )


def test_normalize_service_bus_host_strips_scheme() -> None:
    assert (
        normalize_service_bus_host("leoai-dev-bus.servicebus.windows.net")
        == "leoai-dev-bus.servicebus.windows.net"
    )
    assert (
        normalize_service_bus_host("sb://leoai-dev-bus.servicebus.windows.net/")
        == "leoai-dev-bus.servicebus.windows.net"
    )


def test_describe_message_bus_runtime_detects_namespace_mismatch(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "AZURE_SERVICE_BUS_NAMESPACE",
        "leo-validation-service-bus.servicebus.windows.net",
    )
    monkeypatch.setenv(
        "AZURE_SERVICE_BUS_CONNECTION_STRING",
        "Endpoint=sb://leoai-val-bus.servicebus.windows.net/;"
        "SharedAccessKeyName=rule;SharedAccessKey=abc",
    )
    monkeypatch.setenv("PIPELINE_QUEUE_NAME", "pipeline-jobs")

    info = describe_message_bus_runtime()

    assert info["mode"] == "azure"
    assert info["auth"] == "connection_string"
    assert info["queue"] == "pipeline-jobs"
    assert info["namespace_endpoint_mismatch"] is True


def test_log_message_bus_startup_emits_mismatch_warning(monkeypatch, caplog) -> None:
    monkeypatch.setenv(
        "AZURE_SERVICE_BUS_NAMESPACE",
        "wrong-bus.servicebus.windows.net",
    )
    monkeypatch.setenv(
        "AZURE_SERVICE_BUS_CONNECTION_STRING",
        "Endpoint=sb://right-bus.servicebus.windows.net/;"
        "SharedAccessKeyName=rule;SharedAccessKey=abc",
    )

    logger = logging.getLogger("test.message_bus.runtime")
    with caplog.at_level(logging.INFO, logger="test.message_bus.runtime"):
        log_message_bus_startup(
            logger, service="pipeline-worker", queue_name="pipeline-jobs"
        )

    assert "wrong-bus.servicebus.windows.net" in caplog.text
    assert "right-bus.servicebus.windows.net" in caplog.text
    assert "message bus mismatch" in caplog.text
