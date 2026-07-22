"""Gate 3 A3.4 -- uncoded sentence coverage analyser."""

from __future__ import annotations

from libs.sbar.uncoded_coverage import (
    ChunkText,
    CodeEvidenceSpan,
    analyse_uncoded_coverage,
)


def test_salvages_uncoded_qualifier_sentence() -> None:
    chunk = ChunkText(
        chunk_id="c1",
        text="Dear colleague.\nWeight loss for 3 weeks.\nPlan routine referral.",
    )
    spans = [
        CodeEvidenceSpan(
            chunk_id="c1",
            sentence_index=2,
            evidence_start=None,
            evidence_end=None,
        )
    ]
    report = analyse_uncoded_coverage(
        [chunk],
        spans,
        salvage_policy={"maxSentences": 10, "includeQualifiers": True},
    )
    assert report.total_sentences >= 2
    assert any("Weight loss" in s.text for s in report.salvage_sentences)
    assert report.omitted_filler >= 1


def test_omits_filler_without_salvage() -> None:
    chunk = ChunkText(chunk_id="c1", text="Yours sincerely.\nNo clinical detail.")
    report = analyse_uncoded_coverage([chunk], [], salvage_policy={"maxSentences": 5})
    assert report.salvage_sentences == []
    assert report.omitted_filler >= 1
