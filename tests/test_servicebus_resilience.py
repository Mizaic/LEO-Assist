from __future__ import annotations

from libs.message_bus.azure_adapter import (
    _MAX_RECONNECT_BACKOFF_SECONDS,
    _RECONNECT_BASE_DELAY_SECONDS,
    _is_unrecoverable_credential_error,
    _reconnect_backoff_seconds,
)


def test_reconnect_backoff_uses_base_delay_on_first_attempt() -> None:
    assert _reconnect_backoff_seconds(1) == _RECONNECT_BASE_DELAY_SECONDS


def test_reconnect_backoff_grows_and_caps() -> None:
    assert _reconnect_backoff_seconds(2) >= _RECONNECT_BASE_DELAY_SECONDS
    assert _reconnect_backoff_seconds(100) == _MAX_RECONNECT_BACKOFF_SECONDS


def test_unrecoverable_credential_error_detects_unicode_decode_chain() -> None:
    root = UnicodeDecodeError("utf-8", b"\xa0", 0, 1, "invalid start byte")
    exc = RuntimeError("credential failure")
    exc.__cause__ = root
    assert _is_unrecoverable_credential_error(exc) is True


def test_unrecoverable_credential_error_false_for_generic_exception() -> None:
    exc = RuntimeError("socket timeout")
    assert _is_unrecoverable_credential_error(exc) is False
