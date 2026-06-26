"""Tests for analytics domain configuration API (two-level hierarchy).

Tests the AuditDomain -> Subdomain (ValueSet) -> SNOMED concept model.
ValueSet nodes use flat properties (milestoneType, semanticTags, etc.)
rather than FHIR JSON blobs.
"""

from __future__ import annotations

import json
from unittest.mock import patch, MagicMock

import pytest
from fastapi import HTTPException

# ── Domain CRUD ───────────────────────────────────────────────────────────


class TestListDomains:

    @patch("services.analytics_api.app.routers.domains._ensure_default_domain")
    @patch("services.analytics_api.app.routers.domains.KnowledgeGraphClient")
    def test_returns_domains(self, MockKG, mock_ensure):
        from services.analytics_api.app.routers.domains import list_domains

        MockKG.return_value.run.return_value = [
            {
                "id": "cancer_audit",
                "name": "Cancer Audit",
                "description": "NCDA domains",
                "subdomain_count": 5,
                "minimum_dataset_subdomain_count": 2,
            },
        ]

        result = list_domains()
        assert len(result) == 1
        assert result[0].id == "cancer_audit"
        assert result[0].name == "Cancer Audit"
        assert result[0].subdomain_count == 5
        assert result[0].minimum_dataset_domain is True
        assert result[0].minimum_dataset_subdomain_count == 2
        MockKG.return_value.close.assert_called_once()

    @patch("services.analytics_api.app.routers.domains._ensure_default_domain")
    @patch("services.analytics_api.app.routers.domains.KnowledgeGraphClient")
    def test_empty_list(self, MockKG, mock_ensure):
        from services.analytics_api.app.routers.domains import list_domains

        MockKG.return_value.run.return_value = []
        result = list_domains()
        assert result == []


class TestCreateDomain:

    @patch("services.analytics_api.app.routers.domains.KnowledgeGraphClient")
    def test_creates_domain(self, MockKG):
        from services.analytics_api.app.routers.domains import (
            create_domain,
            DomainCreateRequest,
        )

        MockKG.return_value.run.side_effect = [
            [],  # no existing domain
            [],  # CREATE result
        ]

        body = DomainCreateRequest(name="Cardiology Audit", description="Heart")
        result = create_domain(body)
        assert result.id == "cardiology_audit"
        assert result.name == "Cardiology Audit"
        assert result.description == "Heart"
        assert result.subdomain_count == 0

    @patch("services.analytics_api.app.routers.domains.KnowledgeGraphClient")
    def test_rejects_duplicate(self, MockKG):
        from services.analytics_api.app.routers.domains import (
            create_domain,
            DomainCreateRequest,
        )

        MockKG.return_value.run.return_value = [{"id": "cancer_audit"}]

        with pytest.raises(HTTPException) as exc_info:
            create_domain(DomainCreateRequest(name="Cancer Audit"))
        assert exc_info.value.status_code == 400


class TestGetDomain:

    @patch("services.analytics_api.app.routers.domains._ensure_default_domain")
    @patch("services.analytics_api.app.routers.domains.KnowledgeGraphClient")
    def test_returns_domain_with_subdomains_from_flat_properties(
        self, MockKG, mock_ensure
    ):
        from services.analytics_api.app.routers.domains import get_domain

        raw = json.dumps(
            {
                "compose": {
                    "include": [
                        {
                            "system": "http://snomed.info/sct",
                            "concept": [
                                {"code": "254837009", "display": "Breast cancer"}
                            ],
                        }
                    ]
                },
            }
        )

        MockKG.return_value.run.side_effect = [
            [{"id": "cancer_audit", "name": "Cancer Audit", "description": "NCDA"}],
            [
                {
                    "vid": "ncda-cancer-types",
                    "name": "cancer_types",
                    "description": "Cancer type diagnosis concepts",
                    "milestoneType": "diagnosis",
                    "timeWindowMonths": None,
                    "semanticTags": ["Disease"],
                    "completeness_schema": json.dumps(
                        {
                            "groups": [
                                {
                                    "name": "Diagnosis",
                                    "required": True,
                                    "semantic_categories": ["disorder"],
                                    "concept_ids": [254837009],
                                }
                            ]
                        }
                    ),
                    "rawJson": raw,
                }
            ],
            [],
        ]

        result = get_domain("cancer_audit")
        assert result.id == "cancer_audit"
        assert len(result.subdomains) == 1
        sub = result.subdomains[0]
        assert sub.name == "cancer_types"
        assert sub.milestone_type == "diagnosis"
        assert sub.semantic_tags == ["Disease"]
        assert sub.concept_count == 1
        assert result.minimum_dataset_domain is True
        assert result.minimum_dataset_subdomain_count == 1

    @patch("services.analytics_api.app.routers.domains._ensure_default_domain")
    @patch("services.analytics_api.app.routers.domains.KnowledgeGraphClient")
    def test_handles_string_semantic_tags(self, MockKG, mock_ensure):
        """semanticTags might come back as a JSON string from some drivers."""
        from services.analytics_api.app.routers.domains import get_domain

        MockKG.return_value.run.side_effect = [
            [{"id": "cancer_audit", "name": "Cancer Audit", "description": "NCDA"}],
            [
                {
                    "vid": "ncda-symptoms",
                    "name": "symptoms",
                    "description": "Presenting symptoms",
                    "milestoneType": None,
                    "timeWindowMonths": 12,
                    "semanticTags": '["Clinical_finding", "Situation"]',
                    "rawJson": None,
                }
            ],
        ]

        result = get_domain("cancer_audit")
        assert result.subdomains[0].semantic_tags == ["Clinical_finding", "Situation"]
        assert result.subdomains[0].time_window_months == 12

    @patch("services.analytics_api.app.routers.domains._ensure_default_domain")
    @patch("services.analytics_api.app.routers.domains.KnowledgeGraphClient")
    def test_404_when_not_found(self, MockKG, mock_ensure):
        from services.analytics_api.app.routers.domains import get_domain

        MockKG.return_value.run.return_value = []

        with pytest.raises(HTTPException) as exc_info:
            get_domain("nonexistent")
        assert exc_info.value.status_code == 404


class TestDeleteDomain:

    @patch("services.analytics_api.app.routers.domains.KnowledgeGraphClient")
    def test_deletes_existing(self, MockKG):
        from services.analytics_api.app.routers.domains import delete_domain

        MockKG.return_value.run.side_effect = [
            [{"id": "test_audit"}],
            [],
        ]

        delete_domain("test_audit")
        calls = [call[0][0] for call in MockKG.return_value.run.call_args_list]
        assert any("DETACH DELETE" in query for query in calls)

    @patch("services.analytics_api.app.routers.domains.KnowledgeGraphClient")
    def test_404_when_not_found(self, MockKG):
        from services.analytics_api.app.routers.domains import delete_domain

        MockKG.return_value.run.return_value = []

        with pytest.raises(HTTPException) as exc_info:
            delete_domain("nonexistent")
        assert exc_info.value.status_code == 404


# ── Subdomain CRUD ────────────────────────────────────────────────────────


class TestCreateSubdomain:

    @patch("services.analytics_api.app.routers.domains.DomainRegistry")
    @patch("services.analytics_api.app.routers.domains._upsert_valueset_flat")
    @patch("services.analytics_api.app.routers.domains.KnowledgeGraphClient")
    def test_creates_and_links(self, MockKG, mock_upsert, mock_reg):
        from services.analytics_api.app.routers.domains import (
            create_subdomain,
            SubdomainCreateRequest,
        )

        MockKG.return_value.run.side_effect = [
            [{"id": "cancer_audit"}],  # domain exists
            [],  # no duplicate VS
            [],  # MERGE link
        ]

        body = SubdomainCreateRequest(
            name="tumour markers",
            description="Tumour marker tests",
            semantic_tags=["Procedure"],
        )
        result = create_subdomain("cancer_audit", body)
        assert result.name == "tumour_markers"
        assert result.description == "Tumour marker tests"
        assert result.concept_count == 0

        mock_upsert.assert_called_once()
        vs_id, resource = mock_upsert.call_args[0]
        assert vs_id == "ncda-tumour-markers"
        assert resource["resourceType"] == "ValueSet"

    @patch("services.analytics_api.app.routers.domains.KnowledgeGraphClient")
    def test_rejects_duplicate_subdomain(self, MockKG):
        from services.analytics_api.app.routers.domains import (
            create_subdomain,
            SubdomainCreateRequest,
        )

        MockKG.return_value.run.side_effect = [
            [{"id": "cancer_audit"}],  # domain exists
            [{"id": "ncda-cancer-types"}],  # VS already exists
        ]

        with pytest.raises(HTTPException) as exc_info:
            create_subdomain(
                "cancer_audit",
                SubdomainCreateRequest(name="cancer types"),
            )
        assert exc_info.value.status_code == 400


class TestUpdateSubdomain:

    @patch("services.analytics_api.app.routers.domains.DomainRegistry")
    @patch("services.analytics_api.app.routers.domains._ensure_domain_owns_subdomain")
    @patch("services.analytics_api.app.routers.domains.KnowledgeGraphClient")
    def test_updates_flat_properties(self, MockKG, mock_guard, mock_reg):
        from services.analytics_api.app.routers.domains import (
            update_subdomain,
            SubdomainUpdateRequest,
        )

        MockKG.return_value.run.side_effect = [
            [],  # SET result
            [],  # audit write
            [
                {
                    "name": "cancer_types",
                    "description": "Updated desc",
                    "milestoneType": "diagnosis",
                    "timeWindowMonths": None,
                    "semanticTags": ["Disease", "New_tag"],
                    "assertionFilter": [],
                    "constructs": [],
                    "completeness_schema": None,
                    "use_cases": ["extraction", "completeness"],
                    "rawJson": None,
                }
            ],
        ]

        body = SubdomainUpdateRequest(
            description="Updated desc",
            semantic_tags=["Disease", "New_tag"],
            use_cases=["extraction", "completeness"],
        )
        result = update_subdomain("cancer_audit", "cancer_types", body)
        assert result.description == "Updated desc"
        assert result.semantic_tags == ["Disease", "New_tag"]
        assert result.use_cases == ["extraction", "completeness"]

        set_call = MockKG.return_value.run.call_args_list[0][0][0]
        assert "v.description" in set_call
        assert "v.semanticTags" in set_call


# ── Concept management ────────────────────────────────────────────────────


class TestAddConcept:

    @patch("services.analytics_api.app.routers.domains.DomainRegistry")
    @patch("services.analytics_api.app.routers.domains._upsert_valueset_flat")
    @patch("services.analytics_api.app.routers.domains._get_valueset_raw")
    @patch("services.analytics_api.app.routers.domains._ensure_domain_owns_subdomain")
    @patch("services.analytics_api.app.routers.domains.KnowledgeGraphClient")
    def test_adds_concept(
        self, MockKG, mock_guard, mock_get_raw, mock_upsert, mock_reg
    ):
        from services.analytics_api.app.routers.domains import (
            add_concept,
            AddConceptRequest,
        )

        raw_vs = json.dumps(
            {
                "resourceType": "ValueSet",
                "id": "ncda-cancer-types",
                "compose": {
                    "include": [{"system": "http://snomed.info/sct", "concept": []}]
                },
            }
        )
        mock_get_raw.return_value = raw_vs

        updated_raw = json.dumps(
            {
                "compose": {
                    "include": [
                        {
                            "system": "http://snomed.info/sct",
                            "concept": [
                                {
                                    "code": "254837009",
                                    "display": "Breast cancer",
                                    "designation": [
                                        {
                                            "use": {"code": "synonym"},
                                            "value": "breast carcinoma",
                                        }
                                    ],
                                }
                            ],
                        }
                    ]
                },
            }
        )
        MockKG.return_value.run.return_value = [
            {
                "name": "cancer_types",
                "description": "Cancer type diagnosis concepts",
                "milestoneType": "diagnosis",
                "timeWindowMonths": None,
                "semanticTags": ["Disease"],
                "rawJson": updated_raw,
            }
        ]

        body = AddConceptRequest(
            concept_id=254837009,
            term="Breast cancer",
            synonyms=["breast carcinoma"],
        )
        result = add_concept("cancer_audit", "cancer_types", body)
        assert result.concept_count == 1
        assert result.concepts[0]["concept_id"] == 254837009
        assert result.concepts[0]["guideline_synonyms"] == ["breast carcinoma"]

        mock_upsert.assert_called_once()

    @patch("services.analytics_api.app.routers.domains._get_valueset_raw")
    @patch("services.analytics_api.app.routers.domains._ensure_domain_owns_subdomain")
    def test_rejects_duplicate_concept(self, mock_guard, mock_get_raw):
        from services.analytics_api.app.routers.domains import (
            add_concept,
            AddConceptRequest,
        )

        mock_get_raw.return_value = json.dumps(
            {
                "resourceType": "ValueSet",
                "id": "ncda-cancer-types",
                "compose": {
                    "include": [
                        {
                            "system": "http://snomed.info/sct",
                            "concept": [
                                {"code": "254837009", "display": "Breast cancer"}
                            ],
                        }
                    ]
                },
            }
        )

        with pytest.raises(HTTPException) as exc_info:
            add_concept(
                "cancer_audit",
                "cancer_types",
                AddConceptRequest(concept_id=254837009, term="Breast cancer"),
            )
        assert exc_info.value.status_code == 400


class TestRemoveConcept:

    @patch("services.analytics_api.app.routers.domains.DomainRegistry")
    @patch("services.analytics_api.app.routers.domains._upsert_valueset_flat")
    @patch("services.analytics_api.app.routers.domains._get_valueset_raw")
    @patch("services.analytics_api.app.routers.domains._ensure_domain_owns_subdomain")
    @patch("services.analytics_api.app.routers.domains.KnowledgeGraphClient")
    def test_removes_concept(
        self, MockKG, mock_guard, mock_get_raw, mock_upsert, mock_reg
    ):
        from services.analytics_api.app.routers.domains import remove_concept

        mock_get_raw.return_value = json.dumps(
            {
                "resourceType": "ValueSet",
                "id": "ncda-cancer-types",
                "compose": {
                    "include": [
                        {
                            "system": "http://snomed.info/sct",
                            "concept": [
                                {"code": "254837009", "display": "Breast cancer"},
                                {"code": "363358000", "display": "Lung cancer"},
                            ],
                        }
                    ]
                },
            }
        )

        updated_raw = json.dumps(
            {
                "compose": {
                    "include": [
                        {
                            "system": "http://snomed.info/sct",
                            "concept": [
                                {"code": "363358000", "display": "Lung cancer"}
                            ],
                        }
                    ]
                },
            }
        )
        MockKG.return_value.run.return_value = [
            {
                "name": "cancer_types",
                "description": "Cancer type diagnosis concepts",
                "milestoneType": "diagnosis",
                "timeWindowMonths": None,
                "semanticTags": ["Disease"],
                "rawJson": updated_raw,
            }
        ]

        result = remove_concept("cancer_audit", "cancer_types", "254837009")
        assert result.concept_count == 1
        assert result.concepts[0]["concept_id"] == 363358000

        mock_upsert.assert_called_once()


# ── Construct management ──────────────────────────────────────────────────


class TestConstructs:

    @patch("services.analytics_api.app.routers.domains._ensure_domain_owns_subdomain")
    @patch("services.analytics_api.app.routers.domains.KnowledgeGraphClient")
    def test_lists_constructs(self, MockKG, mock_guard):
        from services.analytics_api.app.routers.domains import list_constructs

        MockKG.return_value.run.return_value = [
            {
                "constructs": [
                    {
                        "id": "cg_1",
                        "display_name": "Pruritus with bleeding",
                        "logic": "ALL",
                        "roles": [
                            {"role": "condition", "concept_ids": [111], "required": True}
                        ],
                    }
                ]
            }
        ]

        result = list_constructs("cancer_audit", "symptoms")
        assert len(result) == 1
        assert result[0]["id"] == "cg_1"
        assert result[0]["display_name"] == "Pruritus with bleeding"

    @patch("services.analytics_api.app.routers.domains.DomainRegistry")
    @patch("services.analytics_api.app.routers.domains._upsert_valueset_flat")
    @patch("services.analytics_api.app.routers.domains._get_valueset_raw")
    @patch("services.analytics_api.app.routers.domains._ensure_domain_owns_subdomain")
    @patch("services.analytics_api.app.routers.domains.KnowledgeGraphClient")
    def test_replaces_constructs(
        self, MockKG, mock_guard, mock_get_raw, mock_upsert, mock_reg
    ):
        from services.analytics_api.app.routers.domains import (
            replace_constructs,
            ConstructDefinitionRequest,
            ConstructRoleRequest,
        )

        mock_get_raw.return_value = json.dumps(
            {"resourceType": "ValueSet", "id": "ncda-symptoms", "compose": {"include": []}}
        )
        MockKG.return_value.run.return_value = [
            {
                "name": "symptoms",
                "description": "Symptoms",
                "milestoneType": None,
                "timeWindowMonths": None,
                "semanticTags": ["Clinical_finding"],
                "assertionFilter": [],
                "constructs": [
                    {
                        "id": "cg_1",
                        "display_name": "Pruritus with bleeding",
                        "logic": "ALL",
                        "roles": [
                            {"role": "condition", "concept_ids": [111], "required": True}
                        ],
                    }
                ],
                "rawJson": json.dumps({"compose": {"include": []}}),
            }
        ]

        result = replace_constructs(
            "cancer_audit",
            "symptoms",
            [
                ConstructDefinitionRequest(
                    id="cg_1",
                    display_name="Pruritus with bleeding",
                    logic="ALL",
                    roles=[
                        ConstructRoleRequest(
                            role="condition", concept_ids=[111], required=True
                        )
                    ],
                )
            ],
        )

        assert result.construct_count == 1
        assert result.constructs[0]["id"] == "cg_1"
        mock_upsert.assert_called_once()


# ── Ensure default domain ────────────────────────────────────────────────


class TestEnsureDefaultDomain:

    @patch("services.analytics_api.app.routers.domains.KnowledgeGraphClient")
    def test_creates_default_when_none_exist(self, MockKG):
        from services.analytics_api.app.routers.domains import _ensure_default_domain

        MockKG.return_value.run.side_effect = [
            [{"cnt": 0}],  # no AuditDomain nodes
            [{"id": "ncda-cancer-types"}, {"id": "ncda-treatment"}],  # VS list
            [],  # MERGE domain
            [],  # link vs 1
            [],  # link vs 2
        ]

        _ensure_default_domain()
        calls = MockKG.return_value.run.call_args_list
        assert "AuditDomain" in calls[2][0][0]
        assert "HAS_SUBDOMAIN" in calls[3][0][0]

    @patch("services.analytics_api.app.routers.domains.KnowledgeGraphClient")
    def test_skips_when_domains_exist(self, MockKG):
        from services.analytics_api.app.routers.domains import _ensure_default_domain

        MockKG.return_value.run.return_value = [{"cnt": 3}]

        _ensure_default_domain()
        # Two calls: the existence check + the duplicate-relationship cleanup.
        assert MockKG.return_value.run.call_count == 2
        cleanup_call = MockKG.return_value.run.call_args_list[1]
        assert "HAS_SUBDOMAIN" in cleanup_call[0][0]


# -- Completeness schema ---------------------------------------------------


class TestCompletenessSchema:

    @patch("services.analytics_api.app.routers.domains._ensure_domain_owns_subdomain")
    @patch("services.analytics_api.app.routers.domains.KnowledgeGraphClient")
    def test_save_schema_persists_json_and_audit(self, MockKG, mock_guard):
        from libs.auth.org_scope import CallerScope
        from services.analytics_api.app.routers.domains import (
            CompletenessConceptGroup,
            CompletenessSchemaRequest,
            save_completeness_schema,
        )

        body = CompletenessSchemaRequest(
            groups=[
                CompletenessConceptGroup(
                    name="Diagnosis", required=True, concept_ids=[254837009]
                )
            ]
        )
        scope = CallerScope(email="admin@example.com", is_admin=True)

        result = save_completeness_schema("cancer_audit", "breast", body, scope)

        assert result.groups[0]["name"] == "Diagnosis"
        calls = MockKG.return_value.run.call_args_list
        assert "completeness_schema" in calls[0][0][0]
        assert calls[0][1]["schema"]
        assert "DomainConfigAuditLog" in calls[1][0][0]
        assert calls[1][1]["actor"] == "admin@example.com"

    @patch("services.analytics_api.app.routers.domains._ensure_domain_owns_subdomain")
    def test_rejects_schema_without_required_group(self, mock_guard):
        from services.analytics_api.app.routers.domains import (
            CompletenessConceptGroup,
            CompletenessSchemaRequest,
            save_completeness_schema,
        )

        body = CompletenessSchemaRequest(
            groups=[
                CompletenessConceptGroup(
                    name="Optional", required=False, concept_ids=[123]
                )
            ]
        )

        with pytest.raises(HTTPException) as exc_info:
            save_completeness_schema("cancer_audit", "breast", body)

        assert exc_info.value.status_code == 422
        assert "at least one required group" in exc_info.value.detail

    @patch("services.analytics_api.app.routers.domains._ensure_domain_owns_subdomain")
    @patch("services.analytics_api.app.routers.domains.KnowledgeGraphClient")
    def test_missing_schema_returns_explicit_error(self, MockKG, mock_guard):
        from services.analytics_api.app.routers.domains import get_completeness_schema

        MockKG.return_value.run.return_value = [{"completeness_schema": None}]

        with pytest.raises(HTTPException) as exc_info:
            get_completeness_schema("cancer_audit", "breast")

        assert exc_info.value.status_code == 422
        assert "No active completeness schema configured" in exc_info.value.detail

    @patch("services.analytics_api.app.routers.domains._ensure_domain_owns_subdomain")
    @patch("services.analytics_api.app.routers.domains.KnowledgeGraphClient")
    def test_preview_reports_matched_and_missing_without_persisting(
        self, MockKG, mock_guard
    ):
        from services.analytics_api.app.routers.domains import (
            CompletenessConceptGroup,
            CompletenessPreviewRequest,
            CompletenessSchemaRequest,
            preview_completeness_schema,
        )

        MockKG.return_value.run.return_value = []
        body = CompletenessPreviewRequest(
            concept_ids=[111],
            candidate_schema=CompletenessSchemaRequest(
                groups=[
                    CompletenessConceptGroup(
                        name="Presenting symptom", required=True, concept_ids=[111]
                    ),
                    CompletenessConceptGroup(
                        name="Diagnosis", required=True, concept_ids=[222]
                    ),
                ]
            ),
        )

        result = preview_completeness_schema("cancer_audit", "breast", body)

        assert result.complete is False
        assert result.matched_groups[0].name == "Presenting symptom"
        assert result.missing_groups[0].missing_concept_ids == [222]

    @patch("services.analytics_api.app.routers.domains._ensure_domain_owns_subdomain")
    @patch("services.analytics_api.app.routers.domains.KnowledgeGraphClient")
    def test_preview_matches_semantic_category(self, MockKG, mock_guard):
        from services.analytics_api.app.routers.domains import (
            CompletenessConceptGroup,
            CompletenessPreviewRequest,
            CompletenessSchemaRequest,
            preview_completeness_schema,
        )

        MockKG.return_value.run.return_value = [
            {"id": "111", "semantic_tag": "disorder"}
        ]
        body = CompletenessPreviewRequest(
            concept_ids=[111],
            candidate_schema=CompletenessSchemaRequest(
                groups=[
                    CompletenessConceptGroup(
                        name="Any disorder",
                        required=True,
                        semantic_categories=["disorder"],
                    )
                ]
            ),
        )

        result = preview_completeness_schema("cancer_audit", "breast", body)

        assert result.complete is True
        assert result.matched_groups[0].name == "Any disorder"

    @patch("services.analytics_api.app.routers.domains._semantic_tags_for_concepts")
    @patch("services.analytics_api.app.routers.domains._load_completeness_schema")
    @patch("services.analytics_api.app.routers.domains._ensure_domain_owns_subdomain")
    def test_runtime_lower_gi_completeness_ignores_extra_codes(
        self, mock_guard, mock_load_schema, mock_tags
    ):
        from services.analytics_api.app.routers.domains import (
            CompletenessPreviewRequest,
            preview_completeness_schema,
        )

        mock_load_schema.return_value = [
            {
                "name": "FIT result",
                "required": True,
                "semantic_categories": [],
                "concept_ids": [123],
            },
            {
                "name": "Blood results",
                "required": True,
                "semantic_categories": [],
                "concept_ids": [101],
            },
            {
                "name": "Presenting symptom",
                "required": True,
                "semantic_categories": ["finding"],
                "concept_ids": [],
            },
        ]
        mock_tags.side_effect = lambda ids: {
            cid: "finding" for cid in ids if cid == 201
        }

        cases = [
            ([123, 101, 201], True, []),
            ([123, 201], False, ["Blood results"]),
            ([123, 101, 201, 999], True, []),
            ([123, 999], False, ["Blood results", "Presenting symptom"]),
        ]
        for concept_ids, expected_complete, missing_names in cases:
            result = preview_completeness_schema(
                "cancer_referrals",
                "lower_gi",
                CompletenessPreviewRequest(concept_ids=concept_ids),
            )
            assert result.complete is expected_complete
            assert [group.name for group in result.missing_groups] == missing_names

        mock_load_schema.assert_called_with("ncda-lower-gi", "lower_gi")


# ── Helper functions ──────────────────────────────────────────────────────


class TestParseConceptsFromRaw:

    def test_extracts_concepts_from_rawjson(self):
        from services.analytics_api.app.routers.domains import (
            _parse_concepts_from_raw,
            _count_concepts_from_raw,
        )

        raw = json.dumps(
            {
                "compose": {
                    "include": [
                        {
                            "system": "http://snomed.info/sct",
                            "concept": [
                                {
                                    "code": "254837009",
                                    "display": "Breast cancer",
                                    "designation": [
                                        {
                                            "use": {"code": "synonym"},
                                            "value": "breast carcinoma",
                                        },
                                    ],
                                },
                                {"code": "363358000", "display": "Lung cancer"},
                            ],
                        }
                    ]
                },
            }
        )

        concepts = _parse_concepts_from_raw(raw)
        assert len(concepts) == 2
        assert concepts[0]["concept_id"] == 254837009
        assert concepts[0]["guideline_synonyms"] == ["breast carcinoma"]
        assert concepts[1]["concept_id"] == 363358000

        assert _count_concepts_from_raw(raw) == 2

    def test_returns_empty_for_none(self):
        from services.analytics_api.app.routers.domains import (
            _parse_concepts_from_raw,
            _count_concepts_from_raw,
        )

        assert _parse_concepts_from_raw(None) == []
        assert _count_concepts_from_raw(None) == 0

    def test_returns_empty_for_no_concepts(self):
        from services.analytics_api.app.routers.domains import _count_concepts_from_raw

        raw = json.dumps({"compose": {"include": []}})
        assert _count_concepts_from_raw(raw) == 0

    def test_extracts_stage_of_diagnosis_concepts(self):
        from services.analytics_api.app.routers.domains import _parse_concepts_from_raw

        raw = json.dumps(
            {
                "compose": {
                    "include": [
                        {
                            "system": "http://snomed.info/sct",
                            "concept": [
                                {
                                    "code": "254372002",
                                    "display": "Ann Arbor lymphoma staging system (tumor staging)",
                                    "designation": [
                                        {
                                            "use": {"code": "synonym"},
                                            "value": "Ann Arbor stage",
                                        },
                                        {
                                            "use": {"code": "benchmark_key"},
                                            "value": "ann_arbor_lymphoma_staging_system",
                                        },
                                    ],
                                },
                            ],
                        }
                    ],
                },
            }
        )

        concepts = _parse_concepts_from_raw(raw)
        assert len(concepts) == 1
        assert concepts[0]["concept_id"] == 254372002
        assert "Ann Arbor stage" in concepts[0]["guideline_synonyms"]
        assert concepts[0]["benchmark_key"] == "ann_arbor_lymphoma_staging_system"
