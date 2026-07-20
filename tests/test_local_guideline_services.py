"""Tests for local guideline structuring and fail-closed validation."""

from __future__ import annotations

import sys
from pathlib import Path

_API_ROOT = Path(__file__).parent.parent / "services" / "api"
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))

from app.schemas.local_guideline import LocalGuidelineMetadata
from app.services.local_guideline_chunker import chunk_by_heading
from app.services.local_guideline_structurer import structure_local_guideline
from app.services.local_guideline_verifier import verify_local_guideline


def test_chunker_keeps_heading_and_text() -> None:
    """Heading-aware chunks retain the source text."""
    chunks = chunk_by_heading("Referral\nOffer same-day assessment.")

    assert chunks == [{"title": "Referral", "text": "Offer same-day assessment."}]


def test_verifier_fails_closed_when_recommendation_is_not_source_backed() -> None:
    """Unsupported recommendation text always blocks import."""
    metadata = LocalGuidelineMetadata(short_code="SEL-MSK-01", title="MSK pathway")
    draft = structure_local_guideline(
        metadata, "Referral\nOffer same-day assessment for red flags."
    )
    draft.chapters[0].recommendations[0].verbatim = "Unsupported instruction."

    verified = verify_local_guideline(draft, "Referral\nOffer same-day assessment.")

    assert verified.likely_incorrect is True
    assert verified.verification_errors
