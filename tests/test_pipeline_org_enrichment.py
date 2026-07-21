"""VT-F266ECFB -- enrich pipeline state.org_id from patient / context."""

from __future__ import annotations

from unittest.mock import MagicMock

from libs.workflow.step_state_loader import enrich_patient_org_id


class TestEnrichPatientOrgId:
    def test_patient_with_gp_sets_org_id(self):
        client = MagicMock()
        client.run.return_value = [{"org_id": "org-gp-1"}]
        state: dict = {}
        enrich_patient_org_id(client, "pat-1", state)
        assert state["org_id"] == "org-gp-1"

    def test_patient_without_org_leaves_absent(self):
        client = MagicMock()
        client.run.return_value = [{"org_id": None}]
        state: dict = {}
        enrich_patient_org_id(client, "pat-1", state)
        assert "org_id" not in state

    def test_context_override_not_replaced(self):
        client = MagicMock()
        state = {"org_id": "org-from-job"}
        enrich_patient_org_id(client, "pat-1", state)
        assert state["org_id"] == "org-from-job"
        client.run.assert_not_called()

    def test_missing_patient_id_no_throw(self):
        client = MagicMock()
        state: dict = {}
        enrich_patient_org_id(client, "", state)
        assert "org_id" not in state
        client.run.assert_not_called()
