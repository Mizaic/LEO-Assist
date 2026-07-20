"""TDD: clean delete of a local guideline and its content."""

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

from app.routers.local_guidance import delete_local_guideline
from app.services.guideline_graph_writer import GuidelineGraphWriter
from libs.auth.org_scope import CallerScope


def test_writer_delete_runs_clean_cypher() -> None:
    """Delete must target local guideline content and return counts."""
    session = MagicMock()
    session.run.return_value.single.return_value = {
        "guideline_id": "TEST",
        "chapters": 1,
        "recommendations": 1,
        "rules": 1,
    }
    driver = MagicMock()
    driver.session.return_value.__enter__.return_value = session
    with patch("app.services.guideline_graph_writer._driver", return_value=driver):
        result = GuidelineGraphWriter().delete_local_guideline("TEST")

    assert result["guideline_id"] == "TEST"
    assert result["chapters_deleted"] == 1
    assert result["recommendations_deleted"] == 1
    assert result["rules_deleted"] == 1
    cypher = session.run.call_args.args[0]
    assert "source: 'local_guideline'" in cypher
    assert "DETACH DELETE" in cypher
    assert "AuditDomain" not in cypher or "NOT" in cypher


def test_delete_endpoint_404_when_missing() -> None:
    """Missing local guideline returns 404."""
    writer = MagicMock()
    writer.delete_local_guideline.return_value = None
    with patch("app.routers.local_guidance.GuidelineGraphWriter", return_value=writer):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                delete_local_guideline(
                    "MISSING",
                    CallerScope(email="admin@example.test", is_admin=True),
                )
            )
    assert exc.value.status_code == 404


def test_delete_endpoint_returns_counts() -> None:
    """Successful delete returns removal counts."""
    writer = MagicMock()
    writer.delete_local_guideline.return_value = {
        "guideline_id": "TEST",
        "chapters_deleted": 1,
        "recommendations_deleted": 1,
        "rules_deleted": 0,
    }
    with patch("app.routers.local_guidance.GuidelineGraphWriter", return_value=writer):
        result = asyncio.run(
            delete_local_guideline(
                "TEST",
                CallerScope(email="admin@example.test", is_admin=True),
            )
        )
    assert result["guideline_id"] == "TEST"
    assert result["recommendations_deleted"] == 1
