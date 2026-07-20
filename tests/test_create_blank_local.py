"""TDD: create-blank gates for local guideline recommendations."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

_API_ROOT = Path(__file__).parent.parent / "services" / "api"
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))

from app.routers.guidance_rules import CreateBlankRuleRequest, create_blank_rule
from libs.auth.org_scope import CallerScope


def _scope() -> CallerScope:
    return CallerScope(email="admin@example.test", is_admin=True)


def test_create_blank_rejects_likely_incorrect() -> None:
    """likelyIncorrect recommendations must not get a blank rule stub."""
    client = MagicMock()
    client.run.side_effect = [
        [],
        [{"id": "local:rec-bad"}],
    ]
    with patch("app.routers.guidance_rules._kg_client", return_value=client):
        with pytest.raises(HTTPException) as exc:
            create_blank_rule(CreateBlankRuleRequest(rec_id="local:rec-bad"), _scope())
    assert exc.value.status_code == 422
    assert "verification" in str(exc.value.detail).lower()


def test_create_blank_succeeds_for_verified_local_rec() -> None:
    """Verified local recommendations get a pending_review stub."""
    client = MagicMock()
    client.run.return_value = [
        {
            "rule_id": "rule:new",
            "name": "Same-day",
            "status": "pending_review",
            "schema_version": 2,
            "logic_json": "{}",
            "created_at": "2026-07-20",
            "recommendation_text": "Offer same-day assessment.",
            "guideline_id": "SEL-MSK-01",
            "chapter_title": "Triage",
        }
    ]
    with patch("app.routers.guidance_rules._kg_client", return_value=client):
        result = create_blank_rule(
            CreateBlankRuleRequest(rec_id="local:rec-1"), _scope()
        )
    assert result["rule_id"] == "rule:new"
    assert result["rule"]["status"] == "pending_review"
