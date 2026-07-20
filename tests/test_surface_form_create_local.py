"""Surface form create-local-with-alias -- package bind happy and non-happy."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

_KG_SF = "services.terminology_api.app.routers.surface_forms.KnowledgeGraphClient"
_KG_LC = "services.terminology_api.app.routers.local_concepts.KnowledgeGraphClient"
_APPROVE = (
    "services.terminology_api.app.routers.surface_forms.approve_surface_form_mapping"
)
_AUDIT = "services.terminology_api.app.routers.surface_forms.record_mapping_audit"
_INVALIDATE = (
    "services.terminology_api.app.routers.surface_forms."
    "invalidate_terminology_resolution_caches"
)


class TestCreateLocalWithAliasHappy:
    @patch(_INVALIDATE)
    @patch(_AUDIT)
    @patch(_APPROVE)
    @patch(_KG_SF)
    @patch(_KG_LC)
    def test_creates_concept_and_binds_package(
        self, MockLC, MockSF, mock_approve, _audit, _inv
    ):
        lc = MagicMock()
        MockLC.return_value = lc
        lc.run.side_effect = [
            [],  # conflict check
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
            [{"normalized_form": "acne fulminans"}],
        ]
        sf = MagicMock()
        MockSF.return_value = sf
        sf.run.side_effect = [
            # GET_PACKAGE
            [
                {
                    "id": "pkg-global-1",
                    "name": "Global",
                    "scope": "global",
                    "org_id": None,
                    "status": "draft",
                    "version": 1,
                    "concept_count": 0,
                }
            ],
            # CONTAINS
            [
                {
                    "package_id": "pkg-global-1",
                    "concept_id": "LEO-LOCAL-ACNE-FULMINANS",
                }
            ],
            # upsert mapping
            [
                {
                    "normalized": "acne fulminans",
                    "form": "acne fulminans",
                    "status": "pending",
                    "reviewer": None,
                    "reviewed_at": None,
                    "effective_at": None,
                    "concept_id": "LEO-LOCAL-ACNE-FULMINANS",
                    "concept_fsn": "Acne fulminans (LEO local)",
                }
            ],
        ]

        from services.terminology_api.app.routers.surface_forms import (
            CreateLocalWithAliasRequest,
            create_local_with_alias,
        )

        out = create_local_with_alias(
            CreateLocalWithAliasRequest(
                display_name="Acne fulminans",
                alias="acne fulminans",
                concept_kind="finding",
                package_id="pkg-global-1",
            )
        )
        assert out["concept"]["id"] == "LEO-LOCAL-ACNE-FULMINANS"
        assert out["package_id"] == "pkg-global-1"
        mock_approve.assert_not_called()


class TestCreateLocalWithAliasUnhappy:
    def test_empty_alias_422(self):
        from services.terminology_api.app.routers.surface_forms import (
            CreateLocalWithAliasRequest,
            create_local_with_alias,
        )

        with pytest.raises(HTTPException) as exc:
            create_local_with_alias(
                CreateLocalWithAliasRequest(
                    display_name="X",
                    alias="  ",
                    package_id="pkg-1",
                )
            )
        assert exc.value.status_code == 422

    def test_missing_package_id_422(self):
        from services.terminology_api.app.routers.surface_forms import (
            CreateLocalWithAliasRequest,
            create_local_with_alias,
        )

        with pytest.raises(HTTPException) as exc:
            create_local_with_alias(
                CreateLocalWithAliasRequest(
                    display_name="X",
                    alias="acne",
                    package_id="  ",
                )
            )
        assert exc.value.status_code == 422

    @patch(_KG_SF)
    def test_wrong_org_package_403(self, MockSF):
        sf = MagicMock()
        MockSF.return_value = sf
        sf.run.return_value = [
            {
                "id": "pkg-tenant",
                "name": "Trust A",
                "scope": "tenant",
                "org_id": "org-A",
                "status": "draft",
                "version": 1,
                "concept_count": 0,
            }
        ]
        from services.terminology_api.app.routers.surface_forms import (
            CreateLocalWithAliasRequest,
            create_local_with_alias,
        )

        with pytest.raises(HTTPException) as exc:
            create_local_with_alias(
                CreateLocalWithAliasRequest(
                    display_name="X",
                    alias="acne",
                    package_id="pkg-tenant",
                    org_id="org-B",
                )
            )
        assert exc.value.status_code == 403
