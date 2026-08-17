"""VT -- Validation Lab investigation routes keep cases local.

Atlas: DI-ED5A9AC3
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

from app.routers.validation_lab_investigation import router


def test_put_cases_keeps_nhs_number(monkeypatch: Any) -> None:
    from app.deps import require_admin_or_service
    from app.routers import validation_lab_investigation as mod

    captured: dict[str, Any] = {}

    def fake_save(nc_id: str, cases: list[dict[str, Any]], title: str = "") -> dict:
        captured["nc_id"] = nc_id
        captured["cases"] = cases
        return {"nc_id": nc_id, "cases": cases}

    monkeypatch.setattr(mod, "save_cases", fake_save)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_admin_or_service] = lambda: object()
    res = TestClient(app).put(
        "/validation-lab/ncrs/nc-1/investigation/cases",
        json={
            "cases": [
                {
                    "run_id": "r1",
                    "nhs_number": "9434765919",
                    "ubrn": "000012345678",
                }
            ]
        },
    )
    assert res.status_code == 200
    assert captured["cases"][0]["nhs_number"] == "9434765919"
    assert captured["cases"][0]["ubrn"] == "000012345678"


def test_post_event_uses_store(monkeypatch: Any) -> None:
    from app.deps import require_admin_or_service
    from app.routers import validation_lab_investigation as mod

    monkeypatch.setattr(
        mod,
        "log_event",
        lambda nc_id, kind, text: {
            "atlas_ok": True,
            "atlas_text": "[NHS_NUMBER] note",
        },
    )
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_admin_or_service] = lambda: object()
    res = TestClient(app).post(
        "/validation-lab/ncrs/nc-1/investigation/events",
        json={"kind": "review_opened", "text": "Opened NHS 943 476 5919"},
    )
    assert res.status_code == 200
    assert res.json()["atlas_ok"] is True


def test_get_activity_proxies_atlas(monkeypatch: Any) -> None:
    from app.deps import require_admin_or_service
    from app.routers import validation_lab_investigation as mod

    monkeypatch.setattr(
        mod,
        "list_product_ncr_activity",
        lambda nc_id: [{"text": "Added a case. Local run r1."}],
    )
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_admin_or_service] = lambda: object()
    res = TestClient(app).get("/validation-lab/ncrs/nc-1/activity")
    assert res.status_code == 200
    assert res.json()["items"][0]["text"].startswith("Added a case")
