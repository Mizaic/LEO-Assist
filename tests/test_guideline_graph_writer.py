"""Tests for local guideline graph writer parameters."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

_API_ROOT = Path(__file__).parent.parent / "services" / "api"
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))

from app.schemas.local_guideline import (
    LocalChapterDraft,
    LocalGuidelineDraft,
    LocalGuidelineMetadata,
    LocalRecommendationDraft,
)
from app.services.guideline_graph_writer import GuidelineGraphWriter


def test_writer_stores_stable_key_in_recommendation_number() -> None:
    """The curator key is supplied to the Recommendation.number Cypher parameter."""
    session = MagicMock()
    session.run.return_value.single.return_value = {"version": 1}
    driver = MagicMock()
    driver.session.return_value.__enter__.return_value = session
    draft = LocalGuidelineDraft(
        metadata=LocalGuidelineMetadata(short_code="DERM-01", title="Dermatology"),
        chapters=[
            LocalChapterDraft(
                title="Referral",
                order=0,
                recommendations=[
                    LocalRecommendationDraft(
                        stable_key="REF-1", verbatim="Refer urgently."
                    )
                ],
            )
        ],
        likely_incorrect=False,
    )

    with patch(
        "app.services.guideline_graph_writer._driver",
        return_value=driver,
    ):
        GuidelineGraphWriter().upsert_local_guideline(draft)

    recommendation_calls = [
        call for call in session.run.call_args_list if call.kwargs.get("stable_key")
    ]
    assert recommendation_calls[0].kwargs["stable_key"] == "REF-1"
