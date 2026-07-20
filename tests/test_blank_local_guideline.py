"""TDD: create a local guideline shell without pasted guideline text."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

_API_ROOT = Path(__file__).parent.parent / "services" / "api"
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))

from app.routers.local_guidance import (
    CreateBlankGuidelineRequest,
    create_blank_guideline,
)
from app.schemas.local_guideline import LocalGuidelineMetadata
from app.services.local_guideline_blank import build_blank_local_draft
from libs.auth.org_scope import CallerScope


def test_build_blank_draft_uses_title_as_recommendation_text() -> None:
    """Without pasted text, the guideline title becomes the stub recommendation."""
    draft = build_blank_local_draft(
        LocalGuidelineMetadata(short_code="TEST-01", title="MSK triage")
    )

    assert draft.likely_incorrect is False
    assert draft.verification_errors == []
    assert len(draft.chapters) == 1
    rec = draft.chapters[0].recommendations[0]
    assert rec.stable_key == "manual-1"
    assert rec.verbatim == "MSK triage"
    assert rec.verification_flag is False


def test_create_blank_guideline_persists_shell() -> None:
    """POST create-blank writes a verified shell via the graph writer."""
    writer = MagicMock()
    writer.upsert_local_guideline.return_value = {
        "guideline_id": "TEST-01",
        "ingest_version": 1,
        "chapter_count": 1,
        "recommendation_count": 1,
    }
    with patch("app.routers.local_guidance.GuidelineGraphWriter", return_value=writer):
        result = asyncio.run(
            create_blank_guideline(
                CreateBlankGuidelineRequest(
                    metadata=LocalGuidelineMetadata(
                        short_code="TEST-01", title="MSK triage"
                    )
                ),
                CallerScope(email="admin@example.test", is_admin=True),
            )
        )

    assert result["guideline_id"] == "TEST-01"
    assert result["recommendation_count"] == 1
    written = writer.upsert_local_guideline.call_args.args[0]
    assert written.likely_incorrect is False
    assert written.chapters[0].recommendations[0].verbatim == "MSK triage"
