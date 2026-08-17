"""VT -- Validation Lab NCR routes lock the product.

Atlas: DI-287FFFD0
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

_API_ROOT = Path(__file__).parent.parent / "services" / "api"
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))

from app.routers.validation_lab_ncr import router
from libs.atlas_qms.ncr_shape import LEO_CDS_PRODUCT_ID


def test_list_ncrs_returns_product_only(monkeypatch: Any) -> None:
    from app.routers import validation_lab_ncr as mod
    from app.deps import require_admin_or_service

    monkeypatch.setattr(
        mod,
        "list_product_ncrs",
        lambda query="": [{"id": "n1", "title": "Missed", "product_id": LEO_CDS_PRODUCT_ID}],
    )
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_admin_or_service] = lambda: object()
    client = TestClient(app)
    res = client.get("/validation-lab/ncrs?q=missed")
    assert res.status_code == 200
    body = res.json()
    assert body["product_id"] == LEO_CDS_PRODUCT_ID
    assert body["items"][0]["id"] == "n1"


def test_create_ncr_ignores_client_product_id(monkeypatch: Any) -> None:
    from app.routers import validation_lab_ncr as mod
    from app.deps import require_admin_or_service

    captured: dict[str, str] = {}

    def fake_create(**kwargs: str) -> dict[str, str]:
        captured.update(kwargs)
        return {"id": "n2", "title": kwargs["title"], "product_id": LEO_CDS_PRODUCT_ID}

    monkeypatch.setattr(mod, "create_product_ncr", fake_create)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_admin_or_service] = lambda: object()
    client = TestClient(app)
    res = client.post(
        "/validation-lab/ncrs",
        json={
            "title": "Missed code",
            "description": "LEO missed a present finding.",
            "severity": "minor",
            "product_id": "PROD-SOME-OTHER",
            "run_id": "run-1",
        },
    )
    assert res.status_code == 201
    assert captured["title"] == "Missed code"
    assert "run-1" in captured["description"]
    assert "PROD-SOME-OTHER" not in captured.get("description", "")


def test_get_ncr_uses_facade_get(monkeypatch: Any) -> None:
    from app.routers import validation_lab_ncr as mod
    from app.deps import require_admin_or_service

    monkeypatch.setattr(
        mod,
        "get_product_ncr",
        lambda nc_id: {"id": nc_id, "title": "Missed", "product_id": LEO_CDS_PRODUCT_ID},
    )
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_admin_or_service] = lambda: object()
    client = TestClient(app)
    res = client.get("/validation-lab/ncrs/ncr-9")
    assert res.status_code == 200
    assert res.json()["id"] == "ncr-9"
