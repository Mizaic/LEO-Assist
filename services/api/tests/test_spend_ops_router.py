"""Admin true-up and quota routes.

Atlas trace:
  DI: DI-3E297B23
  Look up via: get_design_control(dc_type="design-input", dc_id="DI-3E297B23")
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.routers.spend_ops import _require_admin, get_true_up
from libs.auth.org_scope import CallerScope


def test_true_up_rejects_non_admin():
    with pytest.raises(HTTPException) as err:
        _require_admin(CallerScope(email="x@y.com", is_admin=False, org_ids=[]))
    assert err.value.status_code == 403


def test_true_up_returns_latest_check():
    mock_pg = MagicMock()
    mock_pg.run.return_value = [
        {
            "date": "2026-09-16",
            "ourInputTokens": 2000000,
            "azurePromptTokens": 3000000,
            "ourCostUsd": 2.11,
            "azureCostGbp": 2.61,
            "status": "warn",
        }
    ]
    with patch("app.routers.spend_ops.PatientGraphClient", return_value=mock_pg):
        body = get_true_up(
            scope=CallerScope(email="a@b.com", is_admin=True, org_ids=[])
        )
    assert body["check"]["date"] == "2026-09-16"
    assert "whole shared account" in body["note"]
