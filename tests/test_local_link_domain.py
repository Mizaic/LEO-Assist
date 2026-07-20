"""TDD: local guideline link-domain endpoint."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

_API_ROOT = Path(__file__).parent.parent / "services" / "api"
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))

from app.routers.local_guidance import LinkDomainRequest, link_domain
from libs.auth.org_scope import CallerScope


def _scope() -> CallerScope:
    return CallerScope(email="admin@example.test", is_admin=True)


def test_link_domain_merges_has_domain() -> None:
    """link-domain returns the linked domain id on success."""
    client = MagicMock()
    client.run.return_value = [{"domain_id": "cancer_audit"}]
    with patch("app.routers.local_guidance.CodingGraphClient", return_value=client):
        result = asyncio.run(
            link_domain(
                "SEL-MSK-01",
                LinkDomainRequest(domain_id="cancer_audit"),
                _scope(),
            )
        )
    assert result == {"guideline_id": "SEL-MSK-01", "domain_id": "cancer_audit"}
    client.run.assert_called_once()
    client.close.assert_called_once()


def test_link_domain_404_when_missing() -> None:
    """Missing guideline or domain must return 404."""
    client = MagicMock()
    client.run.return_value = []
    with patch("app.routers.local_guidance.CodingGraphClient", return_value=client):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                link_domain(
                    "MISSING",
                    LinkDomainRequest(domain_id="cancer_audit"),
                    _scope(),
                )
            )
    assert exc.value.status_code == 404
