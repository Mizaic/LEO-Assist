"""VT for DI-4A012A59 -- engineer panel saves a missed-word teaching example."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from libs.pipeline.span_few_shot import save_span_few_shot, sentence_for_span


def test_sentence_for_span_uses_the_containing_sentence() -> None:
    letter = "Referral for review. Raised HbA1c noted. Family history of diabetes."
    assert sentence_for_span(letter, "HbA1c") == "Raised HbA1c noted."


def test_save_span_few_shot_writes_deidentified_sentence_and_term() -> None:
    written: list[dict] = []
    letter = "NHS 943 476 5919. Missed polyp noted in clinic."
    with patch(
        "libs.pipeline.span_few_shot.persist_review_learning",
        side_effect=lambda **kwargs: written.append(kwargs["few_shot"]),
    ):
        result = save_span_few_shot(
            span="polyp",
            letter=letter,
            semantic_tag="finding",
            assertion="present",
        )
    assert result["deidentified"] is True
    assert "polyp" in result["output"]
    assert "Missed polyp noted in clinic." in result["input"] or "polyp" in result["input"]
    assert "943 476 5919" not in result["input"]
    assert written[0]["category"] == "missed_span"


def test_save_span_few_shot_rejects_empty_span() -> None:
    with pytest.raises(ValueError, match="empty"):
        save_span_few_shot(span="  ", letter="Raised HbA1c noted.")
