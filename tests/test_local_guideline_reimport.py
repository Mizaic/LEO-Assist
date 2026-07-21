"""Tests for local guideline re-structure / re-import diff recomputation."""

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

from app.routers import local_guidance as lg
from app.schemas.local_guideline import (
    LocalChapterDraft,
    LocalGuidelineDraft,
    LocalGuidelineMetadata,
    LocalRecommendationDraft,
)


def _draft(code: str, verbatim: str, key: str = "rec-1") -> LocalGuidelineDraft:
    return LocalGuidelineDraft(
        metadata=LocalGuidelineMetadata(short_code=code, title="Local MSK"),
        chapters=[
            LocalChapterDraft(
                title="Triage",
                order=0,
                recommendations=[
                    LocalRecommendationDraft(
                        stable_key=key, title="Refer", verbatim=verbatim
                    )
                ],
            )
        ],
        likely_incorrect=False,
        verification_errors=[],
    )


@patch.object(lg, "_load_stored_draft")
@patch.object(lg, "GuidelineGraphWriter")
def test_reimport_recomputes_diff(MockWriter: MagicMock, mock_load: MagicMock) -> None:
    mock_load.return_value = _draft("SEL-MSK", "old text")
    MockWriter.return_value.upsert_local_guideline.return_value = {
        "guideline_id": "SEL-MSK",
        "ingest_version": 2,
        "chapter_count": 1,
        "recommendation_count": 1,
    }
    body = lg.ReimportRequest(draft=_draft("SEL-MSK", "new text"), diff_job_id="stale")
    result = asyncio.run(lg.reimport_guideline("SEL-MSK", body, scope=MagicMock()))
    assert result["diff"]["modified"] == ["rec-1"]
    assert result["ingest_version"] == 2


@patch.object(lg, "_load_stored_draft")
def test_restructure_rejects_short_code_mismatch(mock_load: MagicMock) -> None:
    mock_load.return_value = _draft("SEL-MSK", "old")
    body = lg.RestructureRequest(
        text="A" * 40,
        metadata=LocalGuidelineMetadata(short_code="OTHER", title="Other"),
    )
    with pytest.raises(HTTPException) as exc:
        asyncio.run(lg.restructure_guideline("SEL-MSK", body, scope=MagicMock()))
    assert exc.value.status_code == 400
