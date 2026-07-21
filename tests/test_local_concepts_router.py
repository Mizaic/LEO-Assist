"""Local concept CRUD API -- happy and non-happy paths (mocked Neo4j)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

_KG = "services.terminology_api.app.routers.local_concepts.KnowledgeGraphClient"


class TestCreateLocalConceptHappy:
    @patch(_KG)
    def test_creates_finding_and_indexes_term(self, MockKG):
        mock = MagicMock()
        MockKG.return_value = mock
        mock.run.side_effect = [
            [],  # CONFLICTING_SNOMED
            [
                {
                    "id": "LEO-LOCAL-ACNE-FULMINANS",
                    "fsn": "Acne fulminans (LEO local)",
                    "preferred_term": "Acne fulminans",
                    "semantic_tag": "finding",
                    "code_system": "leo_local",
                    "concept_kind": "finding",
                    "is_local": True,
                    "active": True,
                    "description": None,
                }
            ],
            [{"normalized_form": "acne fulminans"}],  # ENSURE_LOCAL_TERM
        ]
        from services.terminology_api.app.routers.local_concepts import (
            LocalConceptCreate,
            create_local_concept,
        )

        out = create_local_concept(
            LocalConceptCreate(display_name="Acne fulminans", concept_kind="finding")
        )
        assert out.id == "LEO-LOCAL-ACNE-FULMINANS"
        assert out.code_system == "leo_local"
        assert out.is_local is True
        assert mock.run.call_count == 3


class TestCreateLocalConceptUnhappy:
    @patch(_KG)
    def test_rejects_invalid_id(self, MockKG):
        from services.terminology_api.app.routers.local_concepts import (
            LocalConceptCreate,
            create_local_concept,
        )

        with pytest.raises(HTTPException) as exc:
            create_local_concept(
                LocalConceptCreate(
                    display_name="X",
                    concept_id="73211009",
                    concept_kind="finding",
                )
            )
        assert exc.value.status_code == 422
        MockKG.assert_not_called()

    @patch(_KG)
    def test_conflict_with_existing_snomed(self, MockKG):
        mock = MagicMock()
        MockKG.return_value = mock
        mock.run.side_effect = [[{"id": "LEO-LOCAL-X", "fsn": "SNOMED clash"}]]
        from services.terminology_api.app.routers.local_concepts import (
            LocalConceptCreate,
            create_local_concept,
        )

        with pytest.raises(HTTPException) as exc:
            create_local_concept(
                LocalConceptCreate(
                    display_name="X",
                    concept_id="LEO-LOCAL-X",
                    concept_kind="finding",
                )
            )
        assert exc.value.status_code == 409


class TestGetDeactivate:
    @patch(_KG)
    def test_get_404(self, MockKG):
        mock = MagicMock()
        MockKG.return_value = mock
        mock.run.return_value = []
        from services.terminology_api.app.routers.local_concepts import (
            get_local_concept,
        )

        with pytest.raises(HTTPException) as exc:
            get_local_concept("LEO-LOCAL-MISSING")
        assert exc.value.status_code == 404

    def test_get_rejects_non_local_id(self):
        from services.terminology_api.app.routers.local_concepts import (
            get_local_concept,
        )

        with pytest.raises(HTTPException) as exc:
            get_local_concept("73211009")
        assert exc.value.status_code == 422

    @patch(_KG)
    def test_deactivate_happy(self, MockKG):
        mock = MagicMock()
        MockKG.return_value = mock
        mock.run.side_effect = [
            [{"id": "LEO-LOCAL-X", "active": False}],
            [
                {
                    "id": "LEO-LOCAL-X",
                    "fsn": "X (LEO local)",
                    "preferred_term": "X",
                    "semantic_tag": "finding",
                    "code_system": "leo_local",
                    "concept_kind": "finding",
                    "is_local": True,
                    "active": False,
                    "description": None,
                }
            ],
        ]
        from services.terminology_api.app.routers.local_concepts import (
            deactivate_local_concept,
        )

        out = deactivate_local_concept("LEO-LOCAL-X")
        assert out.active is False


class TestSearchCodeSystemField:
    def test_terminology_search_query_returns_code_system(self):
        from services.terminology_api.app.queries.terminology import (
            TERMINOLOGY_SEARCH,
            TERMINOLOGY_SEARCH_FILTERED,
        )

        assert "code_system" in TERMINOLOGY_SEARCH
        assert "is_local" in TERMINOLOGY_SEARCH
        assert "code_system" in TERMINOLOGY_SEARCH_FILTERED


class TestDryRunRecovery:
    def test_happy_match(self):
        from services.terminology_api.app.routers.local_concepts import (
            DryRunAlias,
            DryRunRecoveryRequest,
            dry_run_recovery,
        )

        out = dry_run_recovery(
            DryRunRecoveryRequest(
                sample_text="Refer acne fulminans today",
                aliases=[
                    DryRunAlias(
                        form="acne fulminans",
                        concept_id="LEO-LOCAL-ACNE-FULMINANS",
                    )
                ],
            )
        )
        assert out["matched_count"] == 1

    def test_empty_sample_422(self):
        from services.terminology_api.app.routers.local_concepts import (
            DryRunRecoveryRequest,
            dry_run_recovery,
        )
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            dry_run_recovery(DryRunRecoveryRequest(sample_text="  ", aliases=[]))
        assert exc.value.status_code == 422
