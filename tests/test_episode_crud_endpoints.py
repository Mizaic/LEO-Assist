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
        "episode_crud.recompute_episode_dates"
    )
    @patch(
        "services.analytics_api.app.routers."
        "episode_crud.PatientGraphClient"
    )
    def test_attach_invokes_recompute(self, MockPG, mock_recompute):
        from services.analytics_api.app.routers.episode_crud import (
            EpisodeAttachEncounterRequest,
            attach_encounter_to_episode,
        )

        client = MockPG.return_value
        client.run.side_effect = [
            [{"patient_id": "P-1", "gp_id": "ORG-1"}],  # require_episode_in_scope
            [{"props": {}}],  # before snapshot
            [{"encounter_id": "E-1"}],  # MERGE IS_PART_OF
            [{"props": {"referral_date": "2024-01-01"}}],  # after snapshot
            [],  # AuditEvent CREATE
            [],  # AUDIT_FOR MERGE
        ]
        mock_recompute.return_value = {"referral_date": "2024-01-01"}

        result = attach_encounter_to_episode(
            episode_id="ep-1",
            body=EpisodeAttachEncounterRequest(
                encounter_id="E-1", milestone_type="referral"
            ),
            scope=_admin_scope(),
        )
        assert mock_recompute.called
        assert result["derived_dates"] == {"referral_date": "2024-01-01"}

    @patch(
        "services.analytics_api.app.routers."
        "episode_crud.recompute_episode_dates"
    )
    @patch(
        "services.analytics_api.app.routers."
        "episode_crud.PatientGraphClient"
    )
    def test_detach_invokes_recompute(self, MockPG, mock_recompute):
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

        result = detach_encounter_from_episode(
            episode_id="ep-1",
            encounter_id="E-1",
            scope=_admin_scope(),
        )
        assert mock_recompute.called
        assert result["derived_dates"]["referral_date"] is None

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
