"""VT for DI-D90542E5: persist skipped phrases into UncodedPhrase inbox."""

from __future__ import annotations

from pathlib import Path

from libs.pipeline.uncoded_phrase import normalise_phrase, record_uncoded_phrases
from libs.pipeline_graph.subgraphs.terminology import _merge_resolution
from libs.terminology.client import ResolvedTerm


def test_normalise_phrase_collapses_case_and_space() -> None:
    assert normalise_phrase("  PSA  Level ") == "psa level"


def test_record_uncoded_phrases_groups_by_normalised_key() -> None:
    calls: list[dict] = []

    def run(_query: str, **params: object) -> list[dict]:
        calls.append(params)
        return [
            {"phrase_key": params["phrase_key"], "note_count": 1, "status": "inbox"}
        ]

    written = record_uncoded_phrases(
        [
            {
                "text": "PSA",
                "semantic_tag": "procedure",
                "score": 0.42,
                "terminology_unresolved": True,
                "rejected_term": "PSA measurement",
                "rejected_concept_id": "63476009",
                "rejected_tag": "procedure",
                "__sentence_id": "s1",
            }
        ],
        [{"sentence_id": "s1", "text": "Repeat PSA 12.4 ng/ml."}],
        run=run,
    )
    assert written == 1
    assert calls[0]["phrase_key"] == "psa"
    assert calls[0]["extracted_tag"] == "procedure"
    assert calls[0]["last_best_term"] == "PSA measurement"
    assert "12.4" in str(calls[0]["sample_sentence"])


def test_merge_resolution_keeps_rejected_guess_without_code() -> None:
    merged = _merge_resolution(
        {"text": "PSA", "label": "procedure"},
        [
            ResolvedTerm(
                text="PSA",
                concept_id="63476009",
                term="PSA measurement",
                semantic_tag="procedure",
                score=0.42,
            )
        ],
        min_score=0.55,
    )
    assert merged["terminology_unresolved"] is True
    assert merged["concept_id"] is None
    assert merged["rejected_term"] == "PSA measurement"


def test_persist_queues_uncoded_and_stamps_left_uncoded() -> None:
    persist_source = Path("libs/pipeline_graph/subgraphs/persist.py").read_text()
    assert "record_uncoded_phrases" in persist_source
    assert 'if not concept_id or entity.get("terminology_unresolved"):' in persist_source
    assert 'decision = "left_uncoded" if unresolved else "auto_coded"' in persist_source
