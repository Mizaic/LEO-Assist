"""Tests for trainer warm-start fallback behaviour.

Covers VT-LEO-AI-106-TC-004.
"""

import unittest
from unittest.mock import MagicMock, patch


class TestFetchWarmStartModel(unittest.TestCase):
    """VT-106-TC-004: warm-start falls back to cold init on error."""

    def _run_fetch(self, version: str, raises: bool):
        """Import and call _fetch_warm_start_model with a mocked ModelStore."""
        log_messages = []

        def _log(msg: str) -> None:
            log_messages.append(msg)

        if raises:
            mock_store = MagicMock()
            mock_store.download.side_effect = Exception("blob not found")
        else:
            mock_store = MagicMock()
            from pathlib import Path

            mock_store.download.return_value = Path("/tmp/mock_model")

        with patch.dict(
            "sys.modules",
            {"libs.model_store": MagicMock(ModelStore=lambda: mock_store)},
        ):
            from app.trainer import _fetch_warm_start_model

            result = _fetch_warm_start_model(version, _log)

        return result, log_messages

    def test_fallback_returns_none_on_exception(self):
        result, logs = self._run_fetch("v1.0.0", raises=True)
        self.assertIsNone(result)

    def test_fallback_logs_warning(self):
        result, logs = self._run_fetch("v1.0.0", raises=True)
        warning_logs = [m for m in logs if "warm-start" in m.lower() or "WARNING" in m]
        self.assertTrue(
            len(warning_logs) > 0, "Expected warning log from failed warm-start"
        )

    def test_success_returns_path(self):
        from pathlib import Path

        result, logs = self._run_fetch("v1.0.0", raises=False)
        self.assertIsInstance(result, Path)

    def test_no_exception_propagated(self):
        try:
            self._run_fetch("v1.0.0", raises=True)
        except Exception as exc:
            self.fail(f"_fetch_warm_start_model should not propagate exception: {exc}")
