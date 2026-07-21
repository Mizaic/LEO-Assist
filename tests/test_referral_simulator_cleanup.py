"""Happy/unhappy tests for legacy scenario purge + quick-run wrappers (Slice C)."""

from __future__ import annotations

import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

_API_ROOT = Path(__file__).parent.parent / "services" / "api"
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))

from libs.referral_simulator.cleanup import (  # noqa: E402
    PURGE_LEGACY_SCENARIO_ENCOUNTER_PATIENTS,
    purge_legacy_scenario_encounter_patients,
)
from libs.referral_simulator.message import ReferralSimulatorError  # noqa: E402
from libs.referral_simulator.scaffold import (  # noqa: E402
    SOURCE_QUICK_TEST,
    SOURCE_SCENARIO,
)


class _FakeClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.closed = False

    def run(self, query: str, **params: Any) -> list[dict[str, Any]]:
        self.calls.append((query, params))
        return [{"deleted_count": 2}]

    def close(self) -> None:
        self.closed = True

    @contextmanager
    def session(self):
        yield self


def test_purge_happy_removes_scenario_source_patients():
    client = _FakeClient()
    with patch(
        "libs.referral_simulator.cleanup.PatientGraphClient",
        return_value=client,
    ):
        deleted = purge_legacy_scenario_encounter_patients(
            patient_id_prefix="scenario-sbar-"
        )

    assert deleted == 2
    assert len(client.calls) == 1
    query, params = client.calls[0]
    assert params["source"] == SOURCE_SCENARIO
    assert params["patient_id_prefix"] == "scenario-sbar-"
    assert SOURCE_QUICK_TEST not in query or "$source" in query
    assert "patient_id_prefix" in params
    assert client.closed is True


def test_purge_unhappy_empty_prefix_is_noop():
    client = _FakeClient()
    with patch(
        "libs.referral_simulator.cleanup.PatientGraphClient",
        return_value=client,
    ):
        with pytest.raises(ReferralSimulatorError, match="prefix"):
            purge_legacy_scenario_encounter_patients(patient_id_prefix="")

    assert client.calls == []


def test_purge_unhappy_does_not_target_quick_test_source():
    """Purge Cypher must bind source to ai_summarisation_scenario only."""
    assert SOURCE_SCENARIO in PURGE_LEGACY_SCENARIO_ENCOUNTER_PATIENTS or (
        "$source" in PURGE_LEGACY_SCENARIO_ENCOUNTER_PATIENTS
    )
    client = _FakeClient()
    with patch(
        "libs.referral_simulator.cleanup.PatientGraphClient",
        return_value=client,
    ):
        purge_legacy_scenario_encounter_patients(patient_id_prefix="scenario-sbar-")
    _, params = client.calls[0]
    assert params["source"] == SOURCE_SCENARIO
    assert params["source"] != SOURCE_QUICK_TEST


def test_quick_run_scaffold_wrapper_delegates_to_simulator():
    from app.services import quick_run_scaffold as qrs

    with patch(
        "app.services.quick_run_scaffold._scaffold_referral",
        return_value=["c1", "c2"],
    ) as mock_sim:
        result = qrs.scaffold_referral("p", "rr", "dr", "Some text.\n\nMore.")

    assert result == ["c1", "c2"]
    mock_sim.assert_called_once()
    kwargs = mock_sim.call_args.kwargs
    assert kwargs["source"] == SOURCE_QUICK_TEST
    assert kwargs["document_title"] == "Quick test document"
