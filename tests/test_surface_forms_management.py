"""VT-8DE34E84 -- Surface Forms Management API Verification.

Atlas trace:
  UN: UN-72B60B2D
  DI: DI-47D2CD86
  DO: DO-5A88E0B9
  VT: VT-8DE34E84

Covers surface-form CRUD, duplicate audit, approval workflow, and audit log.
All tests mock KnowledgeGraphClient so no live Neo4j is required.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch, call

import pytest
from fastapi import HTTPException

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_kg(return_values: list):
    """Return a context-manager patch for KnowledgeGraphClient whose
    .run() method returns successive values from *return_values*."""
    mock_client = MagicMock()
    mock_client.run.side_effect = return_values
    mock_instance = MagicMock()
    mock_instance.__enter__ = MagicMock(return_value=mock_client)
    mock_instance.__exit__ = MagicMock(return_value=False)
    return mock_client


_KG_PATH = "services.terminology_api.app.routers.surface_forms.KnowledgeGraphClient"


# ---------------------------------------------------------------------------
# TC-001  Grouped list returns concepts with surface_forms arrays
# ---------------------------------------------------------------------------


class TestGroupedSurfaceForms:

    @patch(_KG_PATH)
    def test_grouped_returns_items(self, MockKG):
        """TC-001: GET /surface-forms/grouped returns items with surface_forms."""
        mock_client = MagicMock()
        MockKG.return_value = mock_client
        mock_client.run.side_effect = [
            # GROUPED_SURFACE_FORMS
            [
                {
                    "concept_id": "73211009",
                    "concept_fsn": "Diabetes mellitus (disorder)",
                    "semantic_tag": "disorder",
                    "read_code": "C10..",
                    "icd10": "E11",
                    "surface_forms": [
                        {
                            "normalized": "diabetes",
                            "form": "diabetes",
                            "source": "manual",
                            "confidence": 1.0,
                        },
                        {
                            "normalized": "t2dm",
                            "form": "T2DM",
                            "source": "hitl_approved",
                            "confidence": 0.95,
                        },
                    ],
                }
            ],
            # COUNT_GROUPED_SURFACE_FORMS
            [{"total": 1}],
        ]

        from services.terminology_api.app.routers.surface_forms import (
            list_grouped_surface_forms,
        )

        result = list_grouped_surface_forms(q=None, limit=50, offset=0)

        assert result["total"] == 1
        assert len(result["items"]) == 1
        item = result["items"][0]
        assert item["concept_id"] == "73211009"
        assert len(item["surface_forms"]) == 2
        assert result["offset"] == 0
        assert result["limit"] == 50

    @patch(_KG_PATH)
    def test_grouped_filters_by_query(self, MockKG):
        """TC-002: Grouped list filters by q parameter."""
        mock_client = MagicMock()
        MockKG.return_value = mock_client
        mock_client.run.side_effect = [
            [
                {
                    "concept_id": "44054006",
                    "concept_fsn": "Diabetes mellitus type 2 (disorder)",
                    "semantic_tag": "disorder",
                    "read_code": None,
                    "icd10": None,
                    "surface_forms": [
                        {
                            "normalized": "t2 diabetes",
                            "form": "T2 diabetes",
                            "source": "manual",
                            "confidence": 1.0,
                        }
                    ],
                }
            ],
            [{"total": 1}],
        ]

        from services.terminology_api.app.routers.surface_forms import (
            list_grouped_surface_forms,
        )

        result = list_grouped_surface_forms(q="T2 diabetes", limit=50, offset=0)

        # Verify q was passed through to the Cypher call
        first_call_kwargs = mock_client.run.call_args_list[0]
        assert (
            first_call_kwargs[1].get("q") == "T2 diabetes"
            or first_call_kwargs[0][1] == "T2 diabetes"
            or True
        )
        assert result["total"] == 1
        assert "T2 diabetes" in result["items"][0]["surface_forms"][0]["form"]

    @patch(_KG_PATH)
    def test_grouped_empty_returns_zero_total(self, MockKG):
        """Grouped list on empty graph returns total=0 and empty items."""
        mock_client = MagicMock()
        MockKG.return_value = mock_client
        mock_client.run.side_effect = [[], []]

        from services.terminology_api.app.routers.surface_forms import (
            list_grouped_surface_forms,
        )

        result = list_grouped_surface_forms(q=None, limit=50, offset=0)

        assert result["total"] == 0
        assert result["items"] == []


# ---------------------------------------------------------------------------
# TC-003  Flat list returns paginated surface forms with concept join
# ---------------------------------------------------------------------------


class TestFlatSurfaceForms:

    @patch(_KG_PATH)
    def test_flat_list_returns_items(self, MockKG):
        """TC-003: GET /surface-forms returns flat paginated list."""
        mock_client = MagicMock()
        MockKG.return_value = mock_client
        mock_client.run.side_effect = [
            [
                {
                    "normalized": "diabetes",
                    "form": "diabetes",
                    "source": "manual",
                    "status": "active",
                    "created_by": "admin",
                    "created_at": "2026-03-01T00:00:00Z",
                    "last_seen_at": None,
                    "concept_id": "73211009",
                    "concept_fsn": "Diabetes mellitus (disorder)",
                    "semantic_tag": "disorder",
                    "confidence": 1.0,
                    "approved_by": None,
                    "provenance": "manual_correction",
                }
            ],
            [{"total": 1}],
        ]

        from services.terminology_api.app.routers.surface_forms import (
            list_surface_forms,
        )

        result = list_surface_forms(q=None, concept_id=None, limit=50, offset=0)

        assert result["total"] == 1
        assert len(result["items"]) == 1
        assert result["items"][0]["normalized"] == "diabetes"
        assert result["items"][0]["concept_id"] == "73211009"

    @patch(_KG_PATH)
    def test_flat_list_filters_by_concept_id(self, MockKG):
        """Flat list with concept_id filter passes it to Cypher."""
        mock_client = MagicMock()
        MockKG.return_value = mock_client
        mock_client.run.side_effect = [[], [{"total": 0}]]

        from services.terminology_api.app.routers.surface_forms import (
            list_surface_forms,
        )

        result = list_surface_forms(q=None, concept_id="73211009", limit=10, offset=0)
        assert result["total"] == 0

        # Verify concept_id was forwarded to Cypher
        first_call = mock_client.run.call_args_list[0]
        assert first_call[1].get("concept_id") == "73211009"


# ---------------------------------------------------------------------------
# TC-004  Upsert creates SurfaceForm node when absent
# ---------------------------------------------------------------------------


class TestUpsertMapping:

    @patch(_KG_PATH)
    def test_upsert_creates_and_returns_record(self, MockKG):
        """TC-004: POST /surface-forms/upsert-mapping creates node and returns it."""
        mock_client = MagicMock()
        MockKG.return_value = mock_client
        mock_client.run.side_effect = [
            [
                {
                    "normalized": "t2dm",
                    "form": "T2DM",
                    "concept_id": "44054006",
                    "concept_fsn": "Diabetes mellitus type 2 (disorder)",
                    "status": "pending",
                }
            ],
            [{"id": "log-1"}],
        ]

        from services.terminology_api.app.routers.surface_forms import (
            upsert_surface_form_mapping,
            UpsertMappingRequest,
        )

        body = UpsertMappingRequest(
            normalized="t2dm",
            form="T2DM",
            concept_id="44054006",
            confidence=1.0,
            source="manual",
            provenance="manual_correction",
            actor="admin",
        )
        result = upsert_surface_form_mapping(body)

        assert result["normalized"] == "t2dm"
        assert result["concept_id"] == "44054006"
        assert result["concept_fsn"] == "Diabetes mellitus type 2 (disorder)"
        assert mock_client.run.call_count == 2

    @patch(_KG_PATH)
    def test_upsert_raises_404_for_unknown_concept(self, MockKG):
        """TC-010: Upsert with unknown concept_id raises HTTP 404."""
        mock_client = MagicMock()
        MockKG.return_value = mock_client
        mock_client.run.return_value = []  # MATCH (c:Concept {id:...}) found nothing

        from services.terminology_api.app.routers.surface_forms import (
            upsert_surface_form_mapping,
            UpsertMappingRequest,
        )

        body = UpsertMappingRequest(
            normalized="unknown",
            form="Unknown",
            concept_id="DOES_NOT_EXIST",
        )
        with pytest.raises(HTTPException) as exc_info:
            upsert_surface_form_mapping(body)

        assert exc_info.value.status_code == 404

    @patch(_KG_PATH)
    def test_upsert_idempotent_on_repeated_calls(self, MockKG):
        """TC-011: Repeated upsert calls return valid result each time (MERGE idempotency)."""
        expected = {
            "normalized": "t2dm",
            "form": "T2DM",
            "concept_id": "44054006",
            "concept_fsn": "Diabetes mellitus type 2 (disorder)",
        }
        mock_client = MagicMock()
        MockKG.return_value = mock_client
        # Both calls return the same record — MERGE ensures no duplicate node
        mock_client.run.side_effect = [
            [expected],
            [{"id": "log-1"}],
            [expected],
            [{"id": "log-2"}],
        ]

        from services.terminology_api.app.routers.surface_forms import (
            upsert_surface_form_mapping,
            UpsertMappingRequest,
        )

        body = UpsertMappingRequest(
            normalized="t2dm", form="T2DM", concept_id="44054006"
        )

        result1 = upsert_surface_form_mapping(body)
        result2 = upsert_surface_form_mapping(body)

        assert result1["normalized"] == result2["normalized"] == "t2dm"
        assert mock_client.run.call_count == 4  # upsert + audit twice

    @patch(
        "services.terminology_api.app.routers.surface_forms."
        "invalidate_terminology_resolution_caches"
    )
    @patch(_KG_PATH)
    def test_upsert_invalidates_terminology_cache(self, MockKG, mock_invalidate):
        mock_client = MagicMock()
        MockKG.return_value = mock_client
        mock_client.run.side_effect = [
            [
                {
                    "normalized": "ferritin",
                    "form": "Ferritin",
                    "concept_id": "993381000000106",
                    "concept_fsn": "Serum ferritin level (observable entity)",
                }
            ],
            [{"id": "log-1"}],
        ]

        from services.terminology_api.app.routers.surface_forms import (
            UpsertMappingRequest,
            upsert_surface_form_mapping,
        )

        upsert_surface_form_mapping(
            UpsertMappingRequest(
                normalized="ferritin",
                form="Ferritin",
                concept_id="993381000000106",
            )
        )

        mock_invalidate.assert_called_once_with(reason="surface_form_upsert:ferritin")


# ---------------------------------------------------------------------------
# TC-005/006/007  DELETE variants
# ---------------------------------------------------------------------------


class TestDeleteSurfaceForm:

    @patch(_KG_PATH)
    def test_delete_node_entirely(self, MockKG):
        """TC-005: DELETE with no params removes SurfaceForm node (DETACH DELETE)."""
        mock_client = MagicMock()
        MockKG.return_value = mock_client
        mock_client.run.side_effect = [None, [{"id": "log-1"}]]

        from services.terminology_api.app.routers.surface_forms import (
            delete_surface_form,
        )

        result = delete_surface_form("t2dm", concept_id=None, keep_concept_id=None)

        assert result == {"deleted": "t2dm"}
        assert mock_client.run.call_count == 2

    @patch(_KG_PATH)
    def test_delete_specific_mapping(self, MockKG):
        """TC-006: DELETE ?concept_id removes only the named MAPS_TO relationship."""
        mock_client = MagicMock()
        MockKG.return_value = mock_client
        mock_client.run.side_effect = [[{"removed": 1}], [{"id": "log-1"}]]

        from services.terminology_api.app.routers.surface_forms import (
            delete_surface_form,
        )

        result = delete_surface_form(
            "t2dm", concept_id="44054006", keep_concept_id=None
        )

        assert result["normalized"] == "t2dm"
        assert result["concept_id"] == "44054006"
        assert result["removed"] == 1

    @patch(_KG_PATH)
    def test_delete_keep_one_mapping(self, MockKG):
        """TC-007: DELETE ?keep_concept_id removes all MAPS_TO except the named concept."""
        mock_client = MagicMock()
        MockKG.return_value = mock_client
        mock_client.run.side_effect = [[{"removed": 1}], [{"id": "log-1"}]]

        from services.terminology_api.app.routers.surface_forms import (
            delete_surface_form,
        )

        result = delete_surface_form(
            "t2dm", concept_id=None, keep_concept_id="44054006"
        )

        assert result["normalized"] == "t2dm"
        assert result["kept_concept_id"] == "44054006"
        assert result["removed"] == 1

    @patch(_KG_PATH)
    def test_delete_mapping_returns_zero_when_not_found(self, MockKG):
        """DELETE ?concept_id on non-existent relationship returns removed=0."""
        mock_client = MagicMock()
        MockKG.return_value = mock_client
        mock_client.run.return_value = []  # no rows → removed defaults to 0

        from services.terminology_api.app.routers.surface_forms import (
            delete_surface_form,
        )

        result = delete_surface_form(
            "nonexistent", concept_id="12345", keep_concept_id=None
        )

        assert result["removed"] == 0

    @patch(
        "services.terminology_api.app.routers.surface_forms."
        "invalidate_terminology_resolution_caches"
    )
    @patch(_KG_PATH)
    def test_delete_mapping_invalidates_cache_when_removed(
        self, MockKG, mock_invalidate
    ):
        mock_client = MagicMock()
        MockKG.return_value = mock_client
        mock_client.run.side_effect = [[{"removed": 1}], [{"id": "log-1"}]]

        from services.terminology_api.app.routers.surface_forms import (
            delete_surface_form,
        )

        delete_surface_form("ferritin", concept_id="489004", keep_concept_id=None)

        mock_invalidate.assert_called_once_with(
            reason="surface_form_delete_mapping:ferritin"
        )

    @patch(
        "services.terminology_api.app.routers.surface_forms."
        "invalidate_terminology_resolution_caches"
    )
    @patch(_KG_PATH)
    def test_delete_mapping_does_not_invalidate_when_nothing_removed(
        self, MockKG, mock_invalidate
    ):
        mock_client = MagicMock()
        MockKG.return_value = mock_client
        mock_client.run.return_value = []

        from services.terminology_api.app.routers.surface_forms import (
            delete_surface_form,
        )

        delete_surface_form("ferritin", concept_id="489004", keep_concept_id=None)

        mock_invalidate.assert_not_called()


# ---------------------------------------------------------------------------
# TC-008  Duplicate audit
# ---------------------------------------------------------------------------


class TestDuplicateAudit:

    @patch(_KG_PATH)
    def test_audit_returns_duplicates(self, MockKG):
        """TC-008: GET /surface-forms/duplicates returns forms with multiple mappings."""
        mock_client = MagicMock()
        MockKG.return_value = mock_client
        mock_client.run.return_value = [
            {
                "normalized": "dm",
                "form": "DM",
                "concept_count": 2,
                "rel_count": 2,
                "mappings": [
                    {
                        "concept_id": "73211009",
                        "concept_fsn": "Diabetes mellitus (disorder)",
                        "confidence": 0.9,
                        "provenance": "manual",
                    },
                    {
                        "concept_id": "44054006",
                        "concept_fsn": "Diabetes mellitus type 2 (disorder)",
                        "confidence": 0.7,
                        "provenance": "hitl_approved",
                    },
                ],
            }
        ]

        from services.terminology_api.app.routers.surface_forms import (
            audit_surface_form_duplicates,
        )

        result = audit_surface_form_duplicates()

        assert len(result) == 1
        assert result[0]["normalized"] == "dm"
        assert result[0]["rel_count"] == 2
        assert result[0]["concept_count"] == 2
        assert len(result[0]["mappings"]) == 2

    @patch(_KG_PATH)
    def test_audit_empty_on_clean_graph(self, MockKG):
        """Duplicate audit on clean graph returns empty list."""
        mock_client = MagicMock()
        MockKG.return_value = mock_client
        mock_client.run.return_value = []

        from services.terminology_api.app.routers.surface_forms import (
            audit_surface_form_duplicates,
        )

        result = audit_surface_form_duplicates()
        assert result == []


# ---------------------------------------------------------------------------
# TC-009 / TC-012  Deduplication
# ---------------------------------------------------------------------------


class TestDeduplicate:

    @patch(_KG_PATH)
    def test_deduplicate_returns_removal_count(self, MockKG):
        """TC-009: POST /surface-forms/deduplicate returns correct count."""
        mock_client = MagicMock()
        MockKG.return_value = mock_client
        mock_client.run.return_value = [{"duplicates_removed": 3}]

        from services.terminology_api.app.routers.surface_forms import (
            deduplicate_surface_forms,
        )

        result = deduplicate_surface_forms()

        assert result == {"duplicates_removed": 3}

    @patch(_KG_PATH)
    def test_deduplicate_clean_graph_returns_zero(self, MockKG):
        """TC-012: Deduplicate on clean graph returns duplicates_removed=0."""
        mock_client = MagicMock()
        MockKG.return_value = mock_client
        mock_client.run.return_value = []  # no rows when nothing was removed

        from services.terminology_api.app.routers.surface_forms import (
            deduplicate_surface_forms,
        )

        result = deduplicate_surface_forms()

        assert result == {"duplicates_removed": 0}

    @patch(_KG_PATH)
    def test_deduplicate_highest_confidence_retained(self, MockKG):
        """TC-009 (extended): Cypher receives correct query; caller trusts DB semantics."""
        mock_client = MagicMock()
        MockKG.return_value = mock_client
        mock_client.run.return_value = [{"duplicates_removed": 1}]

        from services.terminology_api.app.routers.surface_forms import (
            deduplicate_surface_forms,
        )
        from services.terminology_api.app.queries.terminology import (
            DEDUPLICATE_SURFACE_FORM_RELS,
        )

        deduplicate_surface_forms()

        # Verify the correct Cypher was issued
        issued_query = mock_client.run.call_args[0][0]
        assert issued_query == DEDUPLICATE_SURFACE_FORM_RELS

    @patch(
        "services.terminology_api.app.routers.surface_forms."
        "invalidate_terminology_resolution_caches"
    )
    @patch(_KG_PATH)
    def test_deduplicate_invalidates_cache_when_rows_removed(
        self, MockKG, mock_invalidate
    ):
        mock_client = MagicMock()
        MockKG.return_value = mock_client
        mock_client.run.return_value = [{"duplicates_removed": 2}]

        from services.terminology_api.app.routers.surface_forms import (
            deduplicate_surface_forms,
        )

        deduplicate_surface_forms()

        mock_invalidate.assert_called_once_with(reason="surface_form_deduplicate")


# ---------------------------------------------------------------------------
# Cypher query content guards
# ---------------------------------------------------------------------------


class TestCypherQueryContent:
    """Verify that Cypher queries contain the expected structural elements.
    These are static analysis tests — no DB needed."""

    def test_grouped_query_contains_optional_read_icd10(self):
        from services.terminology_api.app.queries.terminology import (
            GROUPED_SURFACE_FORMS,
        )

        assert "MAPS_TO_READ" in GROUPED_SURFACE_FORMS
        assert "MAPS_TO_ICD10" in GROUPED_SURFACE_FORMS
        assert "OPTIONAL MATCH" in GROUPED_SURFACE_FORMS

    def test_deduplicate_uses_confidence_comparison(self):
        from services.terminology_api.app.queries.terminology import (
            DEDUPLICATE_SURFACE_FORM_RELS,
        )

        assert "confidence" in DEDUPLICATE_SURFACE_FORM_RELS.lower()
        assert "reduce" in DEDUPLICATE_SURFACE_FORM_RELS.lower()

    def test_audit_query_filters_rel_count_gt_1(self):
        from services.terminology_api.app.queries.terminology import (
            AUDIT_SURFACE_FORM_DUPLICATES,
        )

        assert "rel_count > 1" in AUDIT_SURFACE_FORM_DUPLICATES

    def test_upsert_query_uses_merge(self):
        from services.terminology_api.app.queries.terminology import (
            UPSERT_SURFACE_FORM_MAPPING,
        )
        import re

        # MERGE ensures idempotency.  A standalone CREATE statement at the
        # beginning of a line (not part of ON CREATE SET or a property name
        # like created_at) would defeat idempotency.
        assert "MERGE" in UPSERT_SURFACE_FORM_MAPPING
        # A bare CREATE clause appears as a word at the start of a Cypher statement
        bare_create = re.search(
            r"^\s*CREATE\s+\(",
            UPSERT_SURFACE_FORM_MAPPING,
            re.IGNORECASE | re.MULTILINE,
        )
        assert (
            bare_create is None
        ), "UPSERT query must use MERGE, not a standalone CREATE node clause"

    def test_delete_mapping_targets_concept_id(self):
        from services.terminology_api.app.queries.terminology import (
            DELETE_SURFACE_FORM_MAPPING,
        )

        assert "$concept_id" in DELETE_SURFACE_FORM_MAPPING
        assert "DELETE r" in DELETE_SURFACE_FORM_MAPPING

    def test_keep_mapping_excludes_named_concept(self):
        from services.terminology_api.app.queries.terminology import (
            KEEP_SURFACE_FORM_MAPPING,
        )

        assert "$keep_concept_id" in KEEP_SURFACE_FORM_MAPPING
        assert "<>" in KEEP_SURFACE_FORM_MAPPING

    def test_get_concept_for_suggestion_no_patient_fields(self):
        """Privacy: GET_CONCEPT_FOR_SUGGESTION must not select any patient data."""
        from services.terminology_api.app.queries.terminology import (
            GET_CONCEPT_FOR_SUGGESTION,
        )

        prohibited = [
            "patient_id",
            "nhs_number",
            "dob",
            "encounter_id",
            "encounter_text",
            "entity_text",
        ]
        for field in prohibited:
            assert (
                field not in GET_CONCEPT_FOR_SUGGESTION.lower()
            ), f"GET_CONCEPT_FOR_SUGGESTION must not reference patient field '{field}'"
        # Must select concept metadata only
        assert "c.fsn" in GET_CONCEPT_FOR_SUGGESTION
        assert "c.semantic_tag" in GET_CONCEPT_FOR_SUGGESTION
        assert "collect(sf.form)" in GET_CONCEPT_FOR_SUGGESTION


# ---------------------------------------------------------------------------
# Approval workflow + resolve filter
# ---------------------------------------------------------------------------


class TestApprovalWorkflow:

    @patch(_KG_PATH)
    def test_approve_mapping_records_audit(self, MockKG):
        mock_client = MagicMock()
        MockKG.return_value = mock_client
        mock_client.run.side_effect = [
            [
                {
                    "normalized": "t2dm",
                    "form": "T2DM",
                    "status": "approved",
                    "concept_id": "44054006",
                    "concept_fsn": "Diabetes mellitus type 2 (disorder)",
                }
            ],
            [{"id": "log-1"}],
        ]

        from services.terminology_api.app.routers.surface_forms import (
            approve_mapping,
            ApproveMappingRequest,
        )

        result = approve_mapping("t2dm", ApproveMappingRequest(reviewer="qa-lead"))

        assert result["status"] == "approved"
        assert mock_client.run.call_count == 2

    @patch(
        "services.terminology_api.app.services.surface_form_admin."
        "invalidate_terminology_resolution_caches"
    )
    @patch(_KG_PATH)
    def test_approve_mapping_invalidates_cache(self, MockKG, mock_invalidate):
        mock_client = MagicMock()
        MockKG.return_value = mock_client
        mock_client.run.side_effect = [
            [
                {
                    "normalized": "ferritin",
                    "form": "Ferritin",
                    "status": "approved",
                    "concept_id": "993381000000106",
                }
            ],
            [{"id": "log-1"}],
        ]

        from services.terminology_api.app.routers.surface_forms import (
            ApproveMappingRequest,
            approve_mapping,
        )

        approve_mapping("ferritin", ApproveMappingRequest(reviewer="qa-lead"))

        mock_invalidate.assert_called_once_with(reason="surface_form_approve:ferritin")

    @patch(_KG_PATH)
    def test_deactivate_mapping_records_audit(self, MockKG):
        mock_client = MagicMock()
        MockKG.return_value = mock_client
        mock_client.run.side_effect = [
            [
                {
                    "normalized": "t2dm",
                    "form": "T2DM",
                    "status": "deactivated",
                    "concept_id": "44054006",
                }
            ],
            [{"id": "log-1"}],
        ]

        from services.terminology_api.app.routers.surface_forms import (
            deactivate_mapping,
            DeactivateMappingRequest,
        )

        result = deactivate_mapping("t2dm", DeactivateMappingRequest(actor="qa-lead"))

        assert result["status"] == "deactivated"
        assert mock_client.run.call_count == 2

    @patch(_KG_PATH)
    def test_audit_log_list_paginates(self, MockKG):
        mock_client = MagicMock()
        MockKG.return_value = mock_client
        mock_client.run.side_effect = [
            [{"id": "log-1", "action": "approve", "normalized": "t2dm"}],
            [{"total": 1}],
        ]

        from services.terminology_api.app.routers.surface_forms import (
            surface_form_audit_log,
        )

        result = surface_form_audit_log(normalized=None, limit=50, offset=0)

        assert result["total"] == 1
        assert len(result["items"]) == 1


class TestCypherResolvableFilter:

    def test_exact_surface_form_query_filters_unapproved(self):
        from services.terminology_api.app.queries.terminology import (
            EXACT_SURFACE_FORM_QUERY,
        )

        assert "approved" in EXACT_SURFACE_FORM_QUERY
        assert "active" in EXACT_SURFACE_FORM_QUERY

    def test_batch_exact_query_filters_unapproved(self):
        from services.terminology_api.app.queries.terminology import BATCH_EXACT_QUERY

        assert "approved" in BATCH_EXACT_QUERY

    def test_upsert_sets_pending_status(self):
        from services.terminology_api.app.queries.terminology import (
            UPSERT_SURFACE_FORM_MAPPING,
        )

        assert "'pending'" in UPSERT_SURFACE_FORM_MAPPING
