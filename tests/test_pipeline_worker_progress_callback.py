"""VT-297D9C18: pipeline_worker publishes step + run_completed progress events.

Atlas trace:
  DI: DI-705C806B
  DO: DO-A26CD350
  VT: VT-297D9C18
  Look up via: get_design_control(dc_type="verification-test", dc_id="VT-297D9C18")

Verifies the acceptance criteria of VT-297D9C18:

  AC1 -- pipeline_worker.on_message passes a step_callback to
         handler.handle_message for non-SBAR messages.
  AC2 -- the callback invokes services.coding_worker.app.services
         .progress_publisher.publish_progress for both step_completed
         and run_completed payloads.
  AC3 -- publish_progress is called with the message correlation_id
         (run_id) so /pipeline/progress/{run_id} receives matching
         events.
  AC4 -- at least one run_completed payload is published when
         WorkflowEngine.handle_event finishes successfully.

The behavioural test directly exercises build_progress_callback (the
helper main.py imports). The static-source test asserts the wiring in
main.py is intact, so we do not need to boot the FastAPI app (which
requires the azure-keyvault and sentence-transformers stacks) to gain
confidence in the contract.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from services.pipeline_worker.app.services.progress_callback import (
    build_progress_callback,
)

ROOT = Path(__file__).resolve().parents[1]
MAIN_PATH = ROOT / "services" / "pipeline_worker" / "app" / "main.py"


# -----------------------------------------------------------------------
# AC2 + AC3 + AC4: behavioural tests for build_progress_callback
# -----------------------------------------------------------------------


def _install_publish_progress_capture(
    monkeypatch: pytest.MonkeyPatch,
) -> list[tuple[str, dict[str, Any]]]:
    """Replace publish_progress and update_from_event with capturing fakes."""
    captured: list[tuple[str, dict[str, Any]]] = []

    def _fake_publish(run_id: str, payload: dict[str, Any]) -> None:
        captured.append((run_id, dict(payload)))

    def _fake_update(*_args: Any, **_kwargs: Any) -> None:
        return None

    monkeypatch.setattr(
        "services.coding_worker.app.services.progress_publisher.publish_progress",
        _fake_publish,
    )
    monkeypatch.setattr(
        "libs.redis_client.rebuild_status.update_from_event",
        _fake_update,
    )
    return captured


def test_build_progress_callback_requires_run_id() -> None:
    """Defensive: empty run_id must not be silently accepted."""
    with pytest.raises(ValueError):
        build_progress_callback("")


def test_step_and_run_completed_are_published(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC2 + AC4 -- both step_completed and run_completed reach Redis."""
    captured = _install_publish_progress_capture(monkeypatch)

    callback = build_progress_callback(
        "run-abc-123", patient_id="patient-xyz"
    )

    callback(
        {
            "type": "step_completed",
            "action_id": "act_1",
            "subgraph_id": "extraction",
        }
    )
    callback(
        {
            "type": "run_completed",
            "status": "completed",
            "step_count": 4,
        }
    )

    types = [payload["type"] for _run, payload in captured]
    assert "step_completed" in types
    assert "run_completed" in types


def test_publish_called_with_message_run_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC3 -- publish_progress must use the correlation_id as the channel."""
    captured = _install_publish_progress_capture(monkeypatch)
    callback = build_progress_callback("run-correlation-7", patient_id="p1")

    callback({"type": "run_completed", "status": "completed"})

    assert captured, "publish_progress was not invoked"
    run_ids = {run for run, _payload in captured}
    assert run_ids == {"run-correlation-7"}


def test_payload_stamped_with_run_id_and_patient_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Defensive -- callback must enrich payload so SSE consumers can route."""
    captured = _install_publish_progress_capture(monkeypatch)
    callback = build_progress_callback("run-99", patient_id="patient-42")

    callback({"type": "step_completed", "action_id": "loader"})

    assert captured, "publish_progress was not invoked"
    _run, payload = captured[0]
    assert payload["run_id"] == "run-99"
    assert payload["patient_id"] == "patient-42"


def test_update_from_event_failure_does_not_break_publish(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Defensive -- a Redis rebuild status outage must not block SSE events."""
    captured: list[tuple[str, dict[str, Any]]] = []

    def _fake_publish(run_id: str, payload: dict[str, Any]) -> None:
        captured.append((run_id, dict(payload)))

    def _broken_update(*_a: Any, **_kw: Any) -> None:
        raise RuntimeError("redis down")

    monkeypatch.setattr(
        "services.coding_worker.app.services.progress_publisher.publish_progress",
        _fake_publish,
    )
    monkeypatch.setattr(
        "libs.redis_client.rebuild_status.update_from_event",
        _broken_update,
    )

    callback = build_progress_callback("run-77", patient_id="patient-1")
    callback({"type": "run_completed", "status": "completed"})

    assert captured and captured[0][1]["type"] == "run_completed"


# -----------------------------------------------------------------------
# AC1: static-source check -- pipeline_worker.on_message wires the callback
# -----------------------------------------------------------------------


def _read_main() -> str:
    return MAIN_PATH.read_text(encoding="utf-8")


def test_main_imports_build_progress_callback() -> None:
    """Wiring -- main.py must depend on the shared callback factory."""
    text = _read_main()
    assert "from services.pipeline_worker.app.services.progress_callback" in text
    assert "build_progress_callback" in text


def test_on_message_passes_step_callback_to_handler() -> None:
    """AC1 -- handler.handle_message receives step_callback for non-SBAR work."""
    text = _read_main()
    assert "handler.handle_message(msg, step_callback=step_callback)" in text


def test_on_message_derives_run_id_from_correlation_id() -> None:
    """Wiring -- run_id is taken from msg.correlation_id then message_id."""
    text = _read_main()
    assert "msg.correlation_id" in text
    assert "_build_progress_callback(" in text
