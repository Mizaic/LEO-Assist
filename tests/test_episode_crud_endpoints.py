"""Tests for the manual EpisodeOfCare CRUD endpoints.

Atlas trace:
  VTs: VT-EFA1A6E2 (create-happy), VT-7C0B6121 (delete-confirm-gate),
       VT-D6C2E110 (role-denial), VT-A8E11D40 (org-scope-denial),
       VT-19BB6F1F (date-rederivation)
  DOs: DO-0792E2CB, DO-BDBEDA43, DO-13EA9B93, DO-CFB91205
  DIs: DI-3A19BE12, DI-F4C06C92, DI-B35DCA0F, DI-41B71BF8

Covers:

- Happy-path create / update / delete / attach / detach.
- Role gating: a clinician with selected_role outside the curator set
  receives HTTP 403.
- Org-scope: a non-admin caller whose org_ids do not include the
  episode's gp.id receives HTTP 404 (treated as not-found, not 403,
  to avoid leaking patient existence).
- ``confirm_episode_id`` mismatch is rejected before any graph write.
- Date re-derivation is invoked on attach / detach / create-with-links.
- AuditEvent rows are written via ``write_episode_audit_event``.
"""

from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest
from fastapi import HTTPException

from libs.auth.org_scope import CallerScope
from libs.auth.role_state import RoleState


def _admin_scope() -> CallerScope:
    return CallerScope(email="admin@example.com", is_admin=True, org_ids=[])


def _gp_scope(org_ids=("ORG-1",)) -> CallerScope:
    return CallerScope(
        email="clinician@example.com",
        is_admin=False,
        org_ids=list(org_ids),
    )


def _curator_role_state() -> RoleState:
    return RoleState(
        selected_role="clinician",
        allowed_roles=["clinician"],
    )


def _non_curator_role_state() -> RoleState:
    return RoleState(
        selected_role="developer",
        allowed_roles=["developer"],
    )


# ---------------------------------------------------------------------------
# create_episode
# ---------------------------------------------------------------------------


class TestCreateEpisode:
    """VT-EFA1A6E2 - happy-path create + audit + initial encounter links."""

    @patch(
        "services.analytics_api.app.routers."
        "episode_crud.PatientGraphClient"
    )
    def test_admin_creates_with_initial_encounter(self, MockPG):
        from services.analytics_api.app.routers.episode_crud import (
            EpisodeCreateRequest,
            EpisodeEncounterAttachment,
            create_episode,
        )

        client = MockPG.return_value
        # _require_patient_in_scope (admin path) returns a patient.
        # Subsequent .run() calls return whatever recompute_episode_dates
        # and episode_property_snapshot need.
        client.run.side_effect = [
            [{"id": "P-1"}],  # _require_patient_in_scope (admin path)
            [{"episode_id": "ep-manual-xxx"}],  # CREATE EpisodeOfCare
            [],  # MERGE first IS_PART_OF (link encounter)
            # recompute_episode_dates: collect attached encounters
            [{"episode_id": "ep-manual-xxx", "slots": []}],
            [],  # recompute_episode_dates: SET ep dates
            [{"props": {"episode_id": "ep-manual-xxx"}}],  # snapshot
            [],  # write audit event CREATE (:AuditEvent)
            [],  # write audit event MERGE AUDIT_FOR
        ]

        body = EpisodeCreateRequest(
            patient_id="P-1",
            cancer_type="breast",
            initial_encounter_links=[
                EpisodeEncounterAttachment(
                    encounter_id="E-1", milestone_type="referral"
                ),
            ],
        )
        result = create_episode(body=body, scope=_admin_scope())
        assert result["success"] is True
        assert result["patient_id"] == "P-1"
        assert result["episode_id"].startswith("ep-manual-")

    @patch(
        "services.analytics_api.app.routers."
        "episode_crud.PatientGraphClient"
    )
    def test_invalid_milestone_type_rejected(self, MockPG):
        from services.analytics_api.app.routers.episode_crud import (
            EpisodeCreateRequest,
            EpisodeEncounterAttachment,
            create_episode,
        )

        body = EpisodeCreateRequest(
            patient_id="P-1",
            initial_encounter_links=[
                EpisodeEncounterAttachment(
                    encounter_id="E-1", milestone_type="not-a-milestone"
                ),
            ],
        )
        with pytest.raises(HTTPException) as exc:
            create_episode(body=body, scope=_admin_scope())
        assert exc.value.status_code == 400
        assert "milestone_type" in exc.value.detail


# ---------------------------------------------------------------------------
# update_episode
# ---------------------------------------------------------------------------


class TestUpdateEpisode:
    @patch(
        "libs.auth.role_state.fetch_role_state",
        return_value=RoleState(
            selected_role="clinician", allowed_roles=["clinician"]
        ),
    )
    @patch(
        "services.analytics_api.app.routers."
        "episode_crud.PatientGraphClient"
    )
    def test_sparse_patch_writes_only_supplied_fields(
        self, MockPG, _mock_role
    ):
        from services.analytics_api.app.routers.episode_crud import (
            EpisodeUpdateRequest,
            update_episode,
        )

        client = MockPG.return_value
        client.run.side_effect = [
            [{"patient_id": "P-1", "gp_id": "ORG-1"}],  # require_episode_in_scope
            [{"props": {"cancer_type": "breast"}}],  # before snapshot
            [{"episode_id": "ep-1"}],  # SET update
            [{"props": {"cancer_type": "lung"}}],  # after snapshot
            [],  # CREATE AuditEvent
            [],  # MERGE AUDIT_FOR
        ]

        body = EpisodeUpdateRequest(cancer_type="lung")
        result = update_episode(
            episode_id="ep-1", body=body, scope=_gp_scope()
        )
        assert result["updated_fields"] == ["cancer_type"]
        # The SET clause must mention the updated field and only that field.
        set_call = client.run.call_args_list[2]
        assert "cancer_type" in set_call.args[0]
        assert "audit_notes" not in set_call.args[0]

    @patch(
        "services.analytics_api.app.routers."
        "episode_crud.PatientGraphClient"
    )
    def test_empty_patch_rejected(self, MockPG):
        from services.analytics_api.app.routers.episode_crud import (
            EpisodeUpdateRequest,
            update_episode,
        )

        with pytest.raises(HTTPException) as exc:
            update_episode(
                episode_id="ep-1",
                body=EpisodeUpdateRequest(),
                scope=_admin_scope(),
            )
        assert exc.value.status_code == 400
        assert "No fields" in exc.value.detail


# ---------------------------------------------------------------------------
# delete_episode - VT-7C0B6121 confirm-gate
# ---------------------------------------------------------------------------


class TestDeleteEpisode:
    """VT-7C0B6121 - the type-the-id gate must reject mismatches."""

    @patch(
        "services.analytics_api.app.routers."
        "episode_crud.PatientGraphClient"
    )
    def test_confirm_id_mismatch_rejected_before_graph_write(self, MockPG):
        from services.analytics_api.app.routers.episode_crud import (
            EpisodeDeleteRequest,
            delete_episode,
        )

        body = EpisodeDeleteRequest(confirm_episode_id="WRONG-ID")
        with pytest.raises(HTTPException) as exc:
            delete_episode(
                episode_id="ep-1", body=body, scope=_admin_scope()
            )
        assert exc.value.status_code == 400
        assert "confirm_episode_id" in exc.value.detail
        # Critically: no PatientGraphClient was instantiated, so no
        # graph write occurred.
        MockPG.assert_not_called()

    @patch(
        "libs.auth.role_state.fetch_role_state",
        return_value=RoleState(
            selected_role="clinician", allowed_roles=["clinician"]
        ),
    )
    @patch(
        "services.analytics_api.app.routers."
        "episode_crud.PatientGraphClient"
    )
    def test_confirm_id_match_proceeds_to_detach_delete(
        self, MockPG, _mock_role
    ):
        from services.analytics_api.app.routers.episode_crud import (
            EpisodeDeleteRequest,
            delete_episode,
        )

        client = MockPG.return_value
        client.run.side_effect = [
            [{"patient_id": "P-1", "gp_id": "ORG-1"}],  # require_episode_in_scope
            [{"props": {"episode_id": "ep-1"}}],  # before snapshot
            [],  # DETACH DELETE
            [],  # CREATE AuditEvent
            [],  # MERGE AUDIT_FOR
        ]

        body = EpisodeDeleteRequest(confirm_episode_id="ep-1")
        result = delete_episode(
            episode_id="ep-1", body=body, scope=_gp_scope()
        )
        assert result["success"] is True
        delete_call = client.run.call_args_list[2]
        assert "DETACH DELETE" in delete_call.args[0]


# ---------------------------------------------------------------------------
# Role gating - VT-D6C2E110
# ---------------------------------------------------------------------------


class TestRoleGating:
    """VT-D6C2E110 - non-curator roles must be rejected with HTTP 403."""

    @patch(
        "libs.auth.role_state.fetch_role_state",
        return_value=RoleState(
            selected_role="developer", allowed_roles=["developer"]
        ),
    )
    def test_developer_role_cannot_create_episode(self, _mock_role):
        from services.analytics_api.app.routers.episode_crud import (
            EpisodeCreateRequest,
            create_episode,
        )

        body = EpisodeCreateRequest(patient_id="P-1", cancer_type="breast")
        with pytest.raises(HTTPException) as exc:
            create_episode(body=body, scope=_gp_scope())
        assert exc.value.status_code == 403
        assert "not authorised" in exc.value.detail.lower()

    @patch(
        "libs.auth.role_state.fetch_role_state",
        return_value=RoleState(
            selected_role="qa_ra_lead", allowed_roles=["qa_ra_lead"]
        ),
    )
    @patch(
        "services.analytics_api.app.routers."
        "episode_crud.PatientGraphClient"
    )
    def test_qa_ra_lead_can_update_episode(self, MockPG, _mock_role):
        from services.analytics_api.app.routers.episode_crud import (
            EpisodeUpdateRequest,
            update_episode,
        )

        client = MockPG.return_value
        client.run.side_effect = [
            [{"patient_id": "P-1", "gp_id": "ORG-1"}],
            [{"props": {}}],
            [{"episode_id": "ep-1"}],
            [{"props": {"cancer_type": "lung"}}],
            [],
            [],
        ]

        result = update_episode(
            episode_id="ep-1",
            body=EpisodeUpdateRequest(cancer_type="lung"),
            scope=_gp_scope(),
        )
        assert result["success"] is True


# ---------------------------------------------------------------------------
# Org-scope denial - VT-A8E11D40
# ---------------------------------------------------------------------------


class TestOrgScopeDenial:
    """VT-A8E11D40 - episodes outside scope.org_ids must return HTTP 404."""

    @patch(
        "libs.auth.role_state.fetch_role_state",
        return_value=RoleState(
            selected_role="clinician", allowed_roles=["clinician"]
        ),
    )
    @patch(
        "services.analytics_api.app.routers."
        "episode_crud.PatientGraphClient"
    )
    def test_update_returns_404_when_gp_id_not_in_scope(
        self, MockPG, _mock_role
    ):
        from services.analytics_api.app.routers.episode_crud import (
            EpisodeUpdateRequest,
            update_episode,
        )

        client = MockPG.return_value
        # require_episode_in_scope: episode exists but its gp_id is
        # outside the caller's org_ids => 404.
        client.run.side_effect = [
            [{"patient_id": "P-1", "gp_id": "OTHER-ORG"}],
        ]

        with pytest.raises(HTTPException) as exc:
            update_episode(
                episode_id="ep-1",
                body=EpisodeUpdateRequest(cancer_type="lung"),
                scope=_gp_scope(org_ids=["ORG-1"]),
            )
        assert exc.value.status_code == 404
        # Importantly the message MUST be "Episode not found", not
        # "forbidden" -- we don't leak existence to out-of-scope callers.
        assert exc.value.detail == "Episode not found"


# ---------------------------------------------------------------------------
# Date re-derivation - VT-19BB6F1F
# ---------------------------------------------------------------------------


class TestDateRederivation:
    """VT-19BB6F1F - attach / detach must call recompute_episode_dates."""

    @patch(
        "services.analytics_api.app.routers."
        "episode_crud.recompute_episode_status"
    )
    @patch(
        "services.analytics_api.app.routers."
        "episode_crud.recompute_episode_dates"
    )
    @patch(
        "services.analytics_api.app.routers."
        "episode_crud.PatientGraphClient"
    )
    def test_attach_invokes_recompute(
        self, MockPG, mock_recompute, mock_recompute_status
    ):
        from services.analytics_api.app.routers.episode_crud import (
            EpisodeAttachEncounterRequest,
            attach_encounter_to_episode,
        )

        client = MockPG.return_value
        client.run.side_effect = [
            [{"patient_id": "P-1", "gp_id": "ORG-1"}],  # require_episode_in_scope
            [{"n": 0}],  # encounter_slot_edge_exists (pre-check)
            [{"props": {}}],  # before snapshot
            [{"encounter_id": "E-1"}],  # MERGE IS_PART_OF
            [{"props": {"referral_date": "2024-01-01"}}],  # after snapshot
            [],  # AuditEvent CREATE
            [],  # AUDIT_FOR MERGE
        ]
        mock_recompute.return_value = {"referral_date": "2024-01-01"}
        mock_recompute_status.return_value = {
            "status": None,
            "previous_status": None,
            "changed": False,
        }

        result = attach_encounter_to_episode(
            episode_id="ep-1",
            body=EpisodeAttachEncounterRequest(
                encounter_id="E-1", milestone_type="referral"
            ),
            scope=_admin_scope(),
        )
        assert mock_recompute.called
        assert mock_recompute_status.called
        assert result["derived_dates"] == {"referral_date": "2024-01-01"}
        assert result["already_linked"] is False
        assert result["status_change"]["changed"] is False

    @patch(
        "services.analytics_api.app.routers."
        "episode_crud.recompute_episode_status"
    )
    @patch(
        "services.analytics_api.app.routers."
        "episode_crud.recompute_episode_dates"
    )
    @patch(
        "services.analytics_api.app.routers."
        "episode_crud.PatientGraphClient"
    )
    def test_detach_invokes_recompute(
        self, MockPG, mock_recompute, mock_recompute_status
    ):
        from services.analytics_api.app.routers.episode_crud import (
            detach_encounter_from_episode,
        )

        client = MockPG.return_value
        client.run.side_effect = [
            [{"patient_id": "P-1", "gp_id": "ORG-1"}],
            [{"props": {"referral_date": "2024-01-01"}}],
            [{"encounter_id": "E-1"}],  # DELETE r returns the encounter id
            [{"props": {"referral_date": None}}],
            [],
            [],
        ]
        mock_recompute.return_value = {"referral_date": None}
        mock_recompute_status.return_value = {
            "status": "active",
            "previous_status": "completed",
            "changed": True,
        }

        result = detach_encounter_from_episode(
            episode_id="ep-1",
            encounter_id="E-1",
            scope=_admin_scope(),
        )
        assert mock_recompute.called
        assert mock_recompute_status.called
        assert result["derived_dates"]["referral_date"] is None
        assert result["status_change"]["changed"] is True
        assert result["status_change"]["status"] == "active"

    @patch(
        "services.analytics_api.app.routers."
        "episode_crud.PatientGraphClient"
    )
    def test_detach_returns_404_when_no_edge(self, MockPG):
        from services.analytics_api.app.routers.episode_crud import (
            detach_encounter_from_episode,
        )

        client = MockPG.return_value
        client.run.side_effect = [
            [{"patient_id": "P-1", "gp_id": "ORG-1"}],  # require_episode_in_scope
            [{"props": {}}],  # before
            [],  # DELETE r returned no rows -> no edge existed
        ]

        with pytest.raises(HTTPException) as exc:
            detach_encounter_from_episode(
                episode_id="ep-1",
                encounter_id="E-missing",
                scope=_admin_scope(),
            )
        assert exc.value.status_code == 404


# ---------------------------------------------------------------------------
# VT-AD52DFB4 -- multi-slot encounter attach + per-slot detach
# ---------------------------------------------------------------------------


class TestMultiSlotEncounter:
    """One encounter can fill multiple milestone slots on the same episode
    (DI-F5E030ED). Verifies the attach MERGE keys on milestone_type, the
    idempotent re-MERGE short-circuit, and the per-slot detach path."""

    @patch(
        "services.analytics_api.app.routers."
        "episode_crud.recompute_episode_status",
        return_value={"status": None, "previous_status": None, "changed": False},
    )
    @patch(
        "services.analytics_api.app.routers."
        "episode_crud.recompute_episode_dates"
    )
    @patch(
        "services.analytics_api.app.routers."
        "episode_crud.PatientGraphClient"
    )
    def test_attach_merge_cypher_keys_on_milestone_type(
        self, MockPG, mock_recompute, _mock_status
    ):
        """TC-001: the MERGE statement includes milestone_type in the
        relationship property map so one encounter can hold multiple
        :IS_PART_OF edges to the same episode."""
        from services.analytics_api.app.routers.episode_crud import (
            EpisodeAttachEncounterRequest,
            attach_encounter_to_episode,
        )

        client = MockPG.return_value
        client.run.side_effect = [
            [{"patient_id": "P-1", "gp_id": "ORG-1"}],  # scope check
            [{"n": 0}],  # pre-check: no existing edge
            [{"props": {}}],  # before snapshot
            [{"encounter_id": "E-1"}],  # MERGE
            [{"props": {}}],  # after snapshot
            [],
            [],
        ]
        mock_recompute.return_value = {}

        attach_encounter_to_episode(
            episode_id="ep-1",
            body=EpisodeAttachEncounterRequest(
                encounter_id="E-1", milestone_type="referral"
            ),
            scope=_admin_scope(),
        )

        merge_call = client.run.call_args_list[3]
        cypher = merge_call[0][0]
        assert "MERGE (e)-[r:IS_PART_OF {milestone_type: $mt}]->(ep)" in cypher
        assert "ON CREATE SET" in cypher
        assert merge_call.kwargs["mt"] == "referral"

    @patch(
        "services.analytics_api.app.routers."
        "episode_crud.write_episode_audit_event"
    )
    @patch(
        "services.analytics_api.app.routers."
        "episode_crud.PatientGraphClient"
    )
    def test_attach_same_slot_is_idempotent_no_op(
        self, MockPG, mock_audit
    ):
        """TC-002: re-attaching the same (encounter, episode, slot)
        triple returns already_linked=true and skips the audit write."""
        from services.analytics_api.app.routers.episode_crud import (
            EpisodeAttachEncounterRequest,
            attach_encounter_to_episode,
        )

        client = MockPG.return_value
        client.run.side_effect = [
            [{"patient_id": "P-1", "gp_id": "ORG-1"}],  # scope check
            [{"n": 1}],  # pre-check: edge already exists
        ]

        result = attach_encounter_to_episode(
            episode_id="ep-1",
            body=EpisodeAttachEncounterRequest(
                encounter_id="E-1", milestone_type="first_presentation"
            ),
            scope=_admin_scope(),
        )

        assert result["already_linked"] is True
        assert result["derived_dates"] is None
        mock_audit.assert_not_called()
        assert client.run.call_count == 2

    @patch(
        "services.analytics_api.app.routers."
        "episode_crud.recompute_episode_status",
        return_value={"status": None, "previous_status": None, "changed": False},
    )
    @patch(
        "services.analytics_api.app.routers."
        "episode_crud.recompute_episode_dates"
    )
    @patch(
        "services.analytics_api.app.routers."
        "episode_crud.PatientGraphClient"
    )
    def test_detach_with_milestone_type_filters_by_slot(
        self, MockPG, mock_recompute, _mock_status
    ):
        """TC-003: DELETE .../encounters/{id}?milestone_type=<slot>
        issues a MATCH that filters on milestone_type, preserving any
        other slots the encounter fills on the same episode."""
        from services.analytics_api.app.routers.episode_crud import (
            detach_encounter_from_episode,
        )

        client = MockPG.return_value
        client.run.side_effect = [
            [{"patient_id": "P-1", "gp_id": "ORG-1"}],  # scope check
            [{"props": {}}],  # before
            [{"encounter_id": "E-1"}],  # DELETE r returns encounter
            [{"props": {}}],  # after
            [],
            [],
        ]
        mock_recompute.return_value = {}

        result = detach_encounter_from_episode(
            episode_id="ep-1",
            encounter_id="E-1",
            milestone_type="referral",
            scope=_admin_scope(),
        )

        delete_call = client.run.call_args_list[2]
        cypher = delete_call[0][0]
        assert "[r:IS_PART_OF {milestone_type: $mt}]" in cypher
        assert delete_call.kwargs["mt"] == "referral"
        assert result["milestone_type"] == "referral"

    @patch(
        "services.analytics_api.app.routers."
        "episode_crud.recompute_episode_status",
        return_value={"status": None, "previous_status": None, "changed": False},
    )
    @patch(
        "services.analytics_api.app.routers."
        "episode_crud.recompute_episode_dates"
    )
    @patch(
        "services.analytics_api.app.routers."
        "episode_crud.PatientGraphClient"
    )
    def test_detach_without_milestone_type_deletes_all_edges(
        self, MockPG, mock_recompute, _mock_status
    ):
        """TC-004: DELETE .../encounters/{id} with no milestone_type
        query param issues an unfiltered MATCH (preserves CLI / bulk
        behaviour)."""
        from services.analytics_api.app.routers.episode_crud import (
            detach_encounter_from_episode,
        )

        client = MockPG.return_value
        client.run.side_effect = [
            [{"patient_id": "P-1", "gp_id": "ORG-1"}],  # scope check
            [{"props": {}}],
            [{"encounter_id": "E-1"}],
            [{"props": {}}],
            [],
            [],
        ]
        mock_recompute.return_value = {}

        result = detach_encounter_from_episode(
            episode_id="ep-1",
            encounter_id="E-1",
            milestone_type=None,
            scope=_admin_scope(),
        )

        delete_call = client.run.call_args_list[2]
        cypher = delete_call[0][0]
        assert "milestone_type" not in cypher
        assert "[r:IS_PART_OF]" in cypher
        assert result["milestone_type"] is None

    @patch(
        "services.analytics_api.app.routers."
        "episode_crud.recompute_episode_status",
        return_value={"status": None, "previous_status": None, "changed": False},
    )
    @patch(
        "services.analytics_api.app.routers."
        "episode_crud.recompute_episode_dates"
    )
    @patch(
        "services.analytics_api.app.routers."
        "episode_crud.PatientGraphClient"
    )
    def test_detach_accepts_legacy_milestone_type(
        self, MockPG, mock_recompute, _mock_status
    ):
        """TC-004b: detach is permissive about milestone_type so a
        curator can remove an :IS_PART_OF edge whose property pre-dates
        the canonical vocabulary (e.g. ``presentation``,
        ``first_clinic_visit``, ``treatment_decision``). The Cypher
        still filters on the supplied value, and if it matches a row
        the edge is removed; if not, the endpoint 404s."""
        from services.analytics_api.app.routers.episode_crud import (
            detach_encounter_from_episode,
        )

        client = MockPG.return_value
        client.run.side_effect = [
            [{"patient_id": "P-1", "gp_id": "ORG-1"}],  # scope check
            [{"props": {}}],
            [{"encounter_id": "E-1"}],
            [{"props": {}}],
            [],
            [],
        ]
        mock_recompute.return_value = {}

        result = detach_encounter_from_episode(
            episode_id="ep-1",
            encounter_id="E-1",
            milestone_type="first_clinic_visit",
            scope=_admin_scope(),
        )

        delete_call = client.run.call_args_list[2]
        assert "[r:IS_PART_OF {milestone_type: $mt}]" in delete_call[0][0]
        assert delete_call.kwargs["mt"] == "first_clinic_visit"
        assert result["milestone_type"] == "first_clinic_visit"

    def test_encounter_slot_edge_exists_helper(self):
        """TC-001b: the helper issues a COUNT query scoped to the
        (encounter, episode, slot) triple and returns a bool."""
        from services.analytics_api.app.routers._episode_crud_helpers import (
            encounter_slot_edge_exists,
        )

        client = MagicMock()
        client.run.return_value = [{"n": 2}]
        assert encounter_slot_edge_exists(
            client, "E-1", "ep-1", "referral"
        ) is True
        cypher = client.run.call_args[0][0]
        assert "[r:IS_PART_OF {milestone_type: $mt}]" in cypher

        client.run.return_value = [{"n": 0}]
        assert encounter_slot_edge_exists(
            client, "E-1", "ep-1", "referral"
        ) is False


# ---------------------------------------------------------------------------
# DI-3A19BE12 -- recompute_episode_status
# ---------------------------------------------------------------------------


class TestRecomputeEpisodeStatus:
    """The status helper drives the rail / cohort filters off the
    current milestone slots without waiting for the next pipeline run.
    """

    def _client_with(self, current: str | None, slots: list[str]):
        client = MagicMock()
        client.run.side_effect = [
            [{"status": current, "slots": slots}],  # MATCH
            [],  # SET (only consumed if changed)
        ]
        return client

    def test_diagnosis_confirmed_promotes_active_to_completed(self):
        from services.analytics_api.app.routers._episode_crud_helpers import (
            recompute_episode_status,
        )

        client = self._client_with("active", ["referral", "diagnosis_confirmed"])
        result = recompute_episode_status(client, "ep-1")
        assert result == {
            "status": "completed",
            "previous_status": "active",
            "changed": True,
        }
        # The SET must have run.
        assert client.run.call_count == 2
        set_call = client.run.call_args_list[1]
        assert "ep.status = $status" in set_call[0][0]
        assert set_call.kwargs["status"] == "completed"

    def test_benign_closure_beats_diagnosis_confirmed(self):
        """When both somehow exist, closure wins -- the curator has
        explicitly said this pathway is closed."""
        from services.analytics_api.app.routers._episode_crud_helpers import (
            recompute_episode_status,
        )

        client = self._client_with(
            "active", ["referral", "diagnosis_confirmed", "benign_closure"]
        )
        result = recompute_episode_status(client, "ep-1")
        assert result["status"] == "closed_benign"
        assert result["changed"] is True

    def test_detaching_diagnosis_reopens_completed_episode(self):
        from services.analytics_api.app.routers._episode_crud_helpers import (
            recompute_episode_status,
        )

        client = self._client_with("completed", ["referral", "first_seen"])
        result = recompute_episode_status(client, "ep-1")
        assert result == {
            "status": "active",
            "previous_status": "completed",
            "changed": True,
        }

    def test_no_op_when_status_already_matches(self):
        """Idempotent: status already matches the slot evidence."""
        from services.analytics_api.app.routers._episode_crud_helpers import (
            recompute_episode_status,
        )

        client = self._client_with("completed", ["referral", "diagnosis_confirmed"])
        result = recompute_episode_status(client, "ep-1")
        assert result == {
            "status": "completed",
            "previous_status": "completed",
            "changed": False,
        }
        assert client.run.call_count == 1  # MATCH only, no SET

    def test_protected_status_is_never_overwritten(self):
        """merged / closed_phantom / closed_related / stale_* statuses
        carry an authoritative reason and must not be silently
        overwritten by a slot-derived status."""
        from services.analytics_api.app.routers._episode_crud_helpers import (
            recompute_episode_status,
        )

        for protected in (
            "merged",
            "closed_phantom",
            "closed_related",
            "stale_no_diagnosis",
            "stale_post_specialist",
        ):
            client = self._client_with(protected, ["diagnosis_confirmed"])
            result = recompute_episode_status(client, "ep-1")
            assert result["changed"] is False, (
                f"protected status {protected} must not be overwritten"
            )
            assert client.run.call_count == 1

    def test_review_status_is_left_alone_until_evidence_present(self):
        """An in_review / review status with no closure or diagnosis
        slot must be left alone (the curator may still be working)."""
        from services.analytics_api.app.routers._episode_crud_helpers import (
            recompute_episode_status,
        )

        client = self._client_with("review", ["referral"])
        result = recompute_episode_status(client, "ep-1")
        assert result["changed"] is False

    def test_missing_episode_returns_empty_result(self):
        from services.analytics_api.app.routers._episode_crud_helpers import (
            recompute_episode_status,
        )

        client = MagicMock()
        client.run.return_value = []
        result = recompute_episode_status(client, "ep-missing")
        assert result == {"status": None, "previous_status": None, "changed": False}

    def test_recompute_respects_reviewed_at_and_appends_audit_note(self):
        """DI-C4CEFA32 / R-2AA626E7: a curator's signed-off verdict
        (reviewed_at IS NOT NULL) is ground truth. The recompute must
        NOT flip the status; instead it appends a one-line audit note
        explaining what would have changed."""

        from services.analytics_api.app.routers._episode_crud_helpers import (
            recompute_episode_status,
        )

        client = MagicMock()
        client.run.side_effect = [
            [
                {
                    "status": "active",
                    "reviewed_at": "2026-04-20T10:00:00Z",
                    "audit_notes": "curator confirmed active",
                    "slots": ["referral", "diagnosis_confirmed"],
                }
            ],
            [],  # audit_notes SET
        ]
        result = recompute_episode_status(client, "ep-1")

        assert result["changed"] is False
        assert result["status"] == "active"
        assert result.get("respected_review") is True
        assert result.get("would_have_been") == "completed"
        # The audit_notes SET must have run (we updated the trail
        # without changing the status).
        assert client.run.call_count == 2
        notes_call = client.run.call_args_list[1]
        assert "ep.audit_notes = $notes" in notes_call[0][0]
        notes_arg = notes_call.kwargs["notes"]
        assert "recompute skipped" in notes_arg
        assert "curator confirmed active" in notes_arg
        assert "would_flip active -> completed" in notes_arg

    def test_recompute_respect_no_op_when_target_equals_current(self):
        """No audit note is written when the proposed change is a no-op
        even if reviewed_at is set -- nothing actually contradicts the
        reviewed verdict."""

        from services.analytics_api.app.routers._episode_crud_helpers import (
            recompute_episode_status,
        )

        client = MagicMock()
        client.run.side_effect = [
            [
                {
                    "status": "completed",
                    "reviewed_at": "2026-04-20T10:00:00Z",
                    "audit_notes": "",
                    "slots": ["referral", "diagnosis_confirmed"],
                }
            ],
        ]
        result = recompute_episode_status(client, "ep-1")
        assert result["changed"] is False
        # No second call (no audit note written).
        assert client.run.call_count == 1


# ---------------------------------------------------------------------------
# DI-C4CEFA32 -- Manual create writes both review-flag fields and
# canonical default status
# ---------------------------------------------------------------------------


class TestManualCreateLifecycleDefaults:
    """The manual create path must default to canonical
    EpisodeStatus.REVIEW and write both legacy ``needs_review`` and
    canonical ``needs_human_review`` so the v2 detector and dashboards
    stay aligned."""

    def test_create_defaults_to_canonical_review_status(self):
        from services.analytics_api.app.routers.episode_crud import (
            EpisodeCreateRequest,
        )

        req = EpisodeCreateRequest(patient_id="pat-1")
        # Default status is the canonical EpisodeStatus.REVIEW value
        # ("review"), not the legacy "in_review".
        assert req.status == "review"

    def test_create_node_writes_both_review_flags(self):
        from unittest.mock import MagicMock

        from services.analytics_api.app.routers.episode_crud import (
            EpisodeCreateRequest,
            _create_episode_node,
        )
        from libs.auth.org_scope import CallerScope

        client = MagicMock()
        client.run.return_value = [{"episode_id": "ep-test"}]
        scope = CallerScope(
            email="nurse@example.com",
            is_admin=True,
            org_ids=[],
        )
        body = EpisodeCreateRequest(
            patient_id="pat-1", cancer_type="breast"
        )

        _create_episode_node(client, body, scope, "ep-test")

        assert client.run.call_count == 1
        props = client.run.call_args.kwargs["props"]
        assert props["needs_review"] is True
        assert props["needs_human_review"] is True
        assert props["status"] == "review"


# ---------------------------------------------------------------------------
# DI-C4CEFA32 -- mission_control.patch_episode_review parity
# ---------------------------------------------------------------------------


def test_patch_episode_review_clears_both_review_flags():
    """The Cypher used by patch_episode_review must clear BOTH
    legacy ``needs_review`` and canonical ``needs_human_review`` so
    the two parallel review-flag fields cannot drift."""
    import re
    from pathlib import Path

    src = Path(
        "services/analytics_api/app/routers/mission_control.py"
    ).read_text(encoding="utf-8")
    # Find the patch_episode_review function body and assert the
    # Cypher clears both flags.
    body = src.split("def patch_episode_review", 1)[1].split("\n\n@", 1)[0]
    assert re.search(
        r"ep\.needs_review\s*=\s*false", body
    ), "patch_episode_review Cypher must clear ep.needs_review"
    assert re.search(
        r"ep\.needs_human_review\s*=\s*false", body
    ), "patch_episode_review Cypher must clear ep.needs_human_review"


def test_close_episode_clears_both_review_flags():
    """dashboards.close_episode must clear BOTH review-flag fields."""
    import re
    from pathlib import Path

    src = Path(
        "services/analytics_api/app/routers/dashboards.py"
    ).read_text(encoding="utf-8")
    body = src.split("def close_episode", 1)[1].split("\n\n@", 1)[0]
    assert re.search(r"ep\.needs_review\s*=\s*false", body)
    assert re.search(r"ep\.needs_human_review\s*=\s*false", body)


def test_merge_endpoint_clears_both_review_flags():
    """dashboards.merge_episodes_endpoint must clear BOTH flags."""
    import re
    from pathlib import Path

    src = Path(
        "services/analytics_api/app/routers/dashboards.py"
    ).read_text(encoding="utf-8")
    body = src.split("def merge_episodes_endpoint", 1)[1].split("\n\n@", 1)[0]
    assert re.search(r"ep\.needs_review\s*=\s*false", body)
    assert re.search(r"ep\.needs_human_review\s*=\s*false", body)


# ---------------------------------------------------------------------------
# VT-900E2453 -- milestone vocabulary parity (backend)
# ---------------------------------------------------------------------------


# Pathway tier -- the AI engine's Milestone.type Literal (eight
# values) plus care_obstruction emitted by the anchor detector.
# These feed episode date roll-ups. Mirrored on the front-end in
# services/ui/src/components/mission-control/milestoneOptions.ts as
# the group="pathway" entries.
_PATHWAY_MILESTONE_TYPES = frozenset(
    {
        "first_presentation",
        "referral",
        "first_seen",
        "outcome_letter",
        "diagnosis_confirmed",
        "treatment_started",
        "treatment_completed",
        "benign_closure",
        "care_obstruction",
    }
)

# Context tier -- supporting evidence the curator can attach but the
# AI engine does NOT emit. They never feed date roll-ups; they exist
# so the timeline carries the full reviewer narrative. DI-50C7E89C.
_CONTEXT_MILESTONE_TYPES = frozenset(
    {
        "related_gp_visit",
        "primary_care_investigations",
        "referral_admin",
        "referral_sent",
        "related_specialist_visit",
        "specialist_diagnostics",
        "related_correspondence",
    }
)


# These values exist on historical :IS_PART_OF edges and must stay
# readable through milestoneLabel(), but must NOT be assignable by
# manual curators going forward. Note: referral_sent has been
# promoted out of this set into _CONTEXT_MILESTONE_TYPES because
# curators now request it as a supporting-context tag.
_LEGACY_MILESTONE_TYPES = frozenset(
    {
        "presentation",
        "specialist_visit",
        "first_clinic_visit",
        "clinic_visit",
        "first_clinic",
        "investigation",
        "diagnosis",
        "treatment_decision",
        "treatment",
        "first_treatment",
        "related",
    }
)


class TestMilestoneVocabularyParity:
    """VT-900E2453 -- backend allow-list parity with the AI engine."""

    def test_helpers_pathway_tier_equals_canonical_nine(self):
        from services.analytics_api.app.routers._episode_crud_helpers import (
            PATHWAY_MILESTONE_TYPES,
        )

        assert PATHWAY_MILESTONE_TYPES == _PATHWAY_MILESTONE_TYPES

    def test_helpers_context_tier_equals_expected_seven(self):
        # DI-A30F36C7 -- supporting-context milestones are curator-only
        # and never fed by the AI engine.
        from services.analytics_api.app.routers._episode_crud_helpers import (
            CONTEXT_MILESTONE_TYPES,
        )

        assert CONTEXT_MILESTONE_TYPES == _CONTEXT_MILESTONE_TYPES

    def test_helpers_milestone_types_is_pathway_plus_context(self):
        from services.analytics_api.app.routers._episode_crud_helpers import (
            CONTEXT_MILESTONE_TYPES,
            MILESTONE_TYPES,
            PATHWAY_MILESTONE_TYPES,
        )

        assert MILESTONE_TYPES == (
            PATHWAY_MILESTONE_TYPES | CONTEXT_MILESTONE_TYPES
        )

    def test_helpers_milestone_types_excludes_legacy_values(self):
        from services.analytics_api.app.routers._episode_crud_helpers import (
            MILESTONE_TYPES,
        )

        leaked = MILESTONE_TYPES & _LEGACY_MILESTONE_TYPES
        assert leaked == frozenset(), (
            f"Backend allow-list still accepts legacy milestone types: "
            f"{sorted(leaked)}"
        )

    def test_engine_schema_literal_matches_pathway_eight(self):
        # The AI engine's Milestone.type Literal is the upstream
        # source of truth. care_obstruction is added by the anchor
        # detector and is not in this Literal. The context tier must
        # NOT leak into the engine schema -- those are manual-only.
        from typing import get_args

        from services.analysis_worker.app.episode_engine.schemas import (
            Milestone,
        )

        engine_values = frozenset(
            get_args(Milestone.model_fields["type"].annotation)
        )
        expected = _PATHWAY_MILESTONE_TYPES - {"care_obstruction"}
        assert engine_values == expected
        # Drift guard: the engine MUST NOT learn the context tier.
        assert engine_values & _CONTEXT_MILESTONE_TYPES == frozenset()

    def test_treatment_completed_in_treatment_rollup_set(self):
        # The new canonical end-of-treatment marker must participate
        # in the episode end_date roll-up.
        from services.analytics_api.app.routers import _episode_crud_helpers

        assert (
            "treatment_completed"
            in _episode_crud_helpers._TREATMENT_MILESTONES
        )

    def test_dashboards_edit_milestone_imports_shared_allow_list(self):
        # dashboards.py edit_milestone validates against the shared
        # MILESTONE_TYPES, not an inline literal set.
        from pathlib import Path

        src = (
            Path(__file__).resolve().parents[1]
            / "services/analytics_api/app/routers/dashboards.py"
        ).read_text()
        assert "from ._episode_crud_helpers import MILESTONE_TYPES" in src
        # The legacy inline valid_types literal block is gone.
        assert '"first_clinic_visit"' not in src
        assert '"specialist_visit"' not in src
        assert '"referral_sent"' not in src

    def test_edit_milestone_rejects_legacy_value(self):
        from services.analytics_api.app.routers.dashboards import (
            MilestoneUpdateRequest,
            edit_milestone,
        )

        with pytest.raises(HTTPException) as exc:
            edit_milestone(
                episode_id="ep-1",
                encounter_id="E-1",
                body=MilestoneUpdateRequest(milestone_type="first_clinic"),
                scope=_admin_scope(),
            )
        assert exc.value.status_code == 400
        assert "milestone_type" in exc.value.detail

    def test_edit_milestone_accepts_new_canonical_value(self):
        from services.analytics_api.app.routers.dashboards import (
            MilestoneUpdateRequest,
            edit_milestone,
        )

        with patch(
            "services.analytics_api.app.routers.dashboards.PatientGraphClient"
        ) as MockPG:
            client = MockPG.return_value
            client.run.return_value = [
                {"encounter_id": "E-1", "episode_id": "ep-1"}
            ]
            result = edit_milestone(
                episode_id="ep-1",
                encounter_id="E-1",
                body=MilestoneUpdateRequest(
                    milestone_type="first_seen"
                ),
                scope=_admin_scope(),
            )
        assert result["success"] is True
        assert result["milestone_type"] == "first_seen"
