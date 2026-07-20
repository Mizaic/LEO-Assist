"""VT-F266ECFB -- LocalTerminologyPackage CRUD/activate/retire (TDD).

Atlas: DI-FB0066CA, DO-7CF39715, VT-F266ECFB
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

_KG = "services.terminology_api.app.routers.local_packages.KnowledgeGraphClient"


class TestCreatePackageHappy:
    @patch(_KG)
    def test_creates_global_package(self, MockKG):
        mock = MagicMock()
        MockKG.return_value = mock
        mock.run.return_value = [
            {
                "id": "pkg-global-1",
                "name": "Platform local defaults",
                "scope": "global",
                "org_id": None,
                "status": "draft",
                "version": 1,
                "concept_count": 0,
            }
        ]
        from services.terminology_api.app.routers.local_packages import (
            PackageCreate,
            create_package,
        )

        out = create_package(
            PackageCreate(name="Platform local defaults", scope="global")
        )
        assert out.scope == "global"
        assert out.org_id is None
        assert out.status == "draft"


class TestCreatePackageUnhappy:
    def test_tenant_without_org_id_422(self):
        from services.terminology_api.app.routers.local_packages import (
            PackageCreate,
            create_package,
        )

        with pytest.raises(HTTPException) as exc:
            create_package(PackageCreate(name="Trust A", scope="tenant"))
        assert exc.value.status_code == 422

    def test_global_with_org_id_422(self):
        from services.terminology_api.app.routers.local_packages import (
            PackageCreate,
            create_package,
        )

        with pytest.raises(HTTPException) as exc:
            create_package(
                PackageCreate(
                    name="Bad", scope="global", org_id="org-1"
                )
            )
        assert exc.value.status_code == 422


class TestActivateRetire:
    @patch(_KG)
    def test_activate_empty_draft_422(self, MockKG):
        mock = MagicMock()
        MockKG.return_value = mock
        mock.run.return_value = [
            {
                "id": "pkg-1",
                "name": "Empty",
                "scope": "global",
                "org_id": None,
                "status": "draft",
                "version": 1,
                "concept_count": 0,
            }
        ]
        from services.terminology_api.app.routers.local_packages import (
            activate_package,
        )

        with pytest.raises(HTTPException) as exc:
            activate_package("pkg-1")
        assert exc.value.status_code == 422

    @patch(_KG)
    def test_activate_with_concept_then_retire(self, MockKG):
        mock = MagicMock()
        MockKG.return_value = mock
        mock.run.side_effect = [
            # get for activate
            [
                {
                    "id": "pkg-1",
                    "name": "Ready",
                    "scope": "global",
                    "org_id": None,
                    "status": "draft",
                    "version": 1,
                    "concept_count": 1,
                }
            ],
            # activate write
            [
                {
                    "id": "pkg-1",
                    "name": "Ready",
                    "scope": "global",
                    "org_id": None,
                    "status": "active",
                    "version": 1,
                    "concept_count": 1,
                }
            ],
            # get for retire
            [
                {
                    "id": "pkg-1",
                    "name": "Ready",
                    "scope": "global",
                    "org_id": None,
                    "status": "active",
                    "version": 1,
                    "concept_count": 1,
                }
            ],
            # retire write
            [
                {
                    "id": "pkg-1",
                    "name": "Ready",
                    "scope": "global",
                    "org_id": None,
                    "status": "retired",
                    "version": 1,
                    "concept_count": 1,
                }
            ],
            # list active (items + count)
            [],
            [{"total": 0}],
        ]
        from services.terminology_api.app.routers.local_packages import (
            activate_package,
            list_packages,
            retire_package,
        )

        active = activate_package("pkg-1")
        assert active.status == "active"
        retired = retire_package("pkg-1")
        assert retired.status == "retired"
        listed = list_packages(status="active", limit=50, offset=0)
        assert listed.total == 0
