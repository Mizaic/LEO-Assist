"""VT -- Validation Lab phone-home digest routes.

Atlas: DI-C7DEF132
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

from app.routers.validation_lab_phone_home import router


def test_preview_returns_gated_items(monkeypatch: Any) -> None:
    from app.deps import require_admin_or_service
    from app.routers import validation_lab_phone_home as mod

    monkeypatch.setattr(
        mod,
        "preview_phone_home",
        lambda: {
            "threshold": 20,
            "items": [
                {"family": "uncoded_phrase", "count": 24, "signature": "LEO-PH|x"}
            ],
        },
    )
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_admin_or_service] = lambda: object()
    res = TestClient(app).get("/validation-lab/phone-home/preview")
    assert res.status_code == 200
    assert res.json()["items"][0]["count"] == 24


def test_digest_returns_submit_actions(monkeypatch: Any) -> None:
    from app.deps import require_admin_or_service
    from app.routers import validation_lab_phone_home as mod

    monkeypatch.setattr(
        mod,
        "digest_phone_home",
        lambda: {
            "threshold": 20,
            "results": [{"action": "created", "signature": "LEO-PH|x"}],
        },
    )
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_admin_or_service] = lambda: object()
    res = TestClient(app).post("/validation-lab/phone-home/digest")
    assert res.status_code == 200
    assert res.json()["results"][0]["action"] == "created"
