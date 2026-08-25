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


def _investigation_app(monkeypatch: Any, **patch_attrs: Any) -> TestClient:
    from app.routers import validation_lab_investigation as mod

    for name, value in patch_attrs.items():
        monkeypatch.setattr(mod, name, value)
    app = FastAPI()
    app.include_router(mod.router)
    app.dependency_overrides[mod.require_admin_or_service] = lambda: object()
    return TestClient(app)


def test_put_cases_keeps_nhs_number(monkeypatch: Any) -> None:
    captured: dict[str, Any] = {}

    def fake_save(nc_id: str, cases: list[dict[str, Any]], title: str = "") -> dict:
        captured["nc_id"] = nc_id
        captured["cases"] = cases
        return {"nc_id": nc_id, "cases": cases}

    client = _investigation_app(monkeypatch, save_cases=fake_save)
    res = client.put(
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
    client = _investigation_app(
        monkeypatch,
        log_event=lambda nc_id, kind, text: {
            "atlas_ok": True,
            "atlas_text": "[NHS_NUMBER] note",
        },
    )
    res = client.post(
        "/validation-lab/ncrs/nc-1/investigation/events",
        json={"kind": "review_opened", "text": "Opened NHS 943 476 5919"},
    )
    assert res.status_code == 200
    assert res.json()["atlas_ok"] is True


def test_get_activity_proxies_atlas(monkeypatch: Any) -> None:
    client = _investigation_app(
        monkeypatch,
        list_product_ncr_activity=lambda nc_id: [{"text": "Added a case. Local run r1."}],
    )
    res = client.get("/validation-lab/ncrs/nc-1/activity")
    assert res.status_code == 200
    assert res.json()["items"][0]["text"].startswith("Added a case")
