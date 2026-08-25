"""Route-specific OOD semantics for the document quality score.

Atlas trace:
  VT: VT-53D72FA5
  DI: DI-0C766F85
  Look up via: get_design_control(dc_type="verification-test", dc_id="VT-53D72FA5")

Acceptance criteria (DI-0C766F85):
  - NER route must not emit few_shot_ood (no retrieval happens).
  - Windowed LLM route uses the minimum per-window similarity as the signal.
  - merge_results passes few_shot_max_similarity as-is, including None.
"""

from __future__ import annotations

import pytest

from libs.pipeline.document_quality import score_document_quality

GYNAE_FORM = """
Section A: Gynaecological Cancer type suspected
Ovary [ ] Cervix [X] Endometrium [ ]
Please take a Ca125 by the time of referral
Section B: Signs/symptoms
B1. Lesion suspicious of cancer of cervix | Yes [X] No [ ]
"""


# -- score_document_quality with None -----------------------------------------


def test_none_similarity_does_not_emit_few_shot_ood() -> None:
    """NER route passes None; quality score must not emit few_shot_ood."""
    result = score_document_quality(GYNAE_FORM, few_shot_max_similarity=None)
    assert "few_shot_ood" not in result.quality_reasons


def test_none_similarity_score_in_range() -> None:
    result = score_document_quality(GYNAE_FORM, few_shot_max_similarity=None)
    assert 0.0 <= result.document_quality_score <= 1.0


def test_none_similarity_stored_as_none() -> None:
    result = score_document_quality(GYNAE_FORM, few_shot_max_similarity=None)
    assert result.few_shot_max_similarity is None


def test_low_float_similarity_still_emits_few_shot_ood() -> None:
    """LLM route: a low float similarity must still emit few_shot_ood."""
    result = score_document_quality(GYNAE_FORM, few_shot_max_similarity=0.1)
    assert "few_shot_ood" in result.quality_reasons


# -- merge_results with NER state ---------------------------------------------


def test_merge_results_ner_state_no_few_shot_ood() -> None:
    """merge_results with no few_shot_max_similarity in state (NER route)."""
    from libs.pipeline_graph.subgraphs.extraction import merge_results

    out = merge_results(
        {
            "encounter_text": GYNAE_FORM,
            "entities": [{"text": "Cervix"}],
        }
    )
    quality = out["document_quality"]
    assert "few_shot_ood" not in quality["quality_reasons"]
    assert quality["few_shot_max_similarity"] is None


# -- windowed route min aggregation -------------------------------------------


def test_windowed_route_returns_min_similarity() -> None:
    """run_windowed_llm_extraction returns the minimum similarity across windows."""
    from libs.nlp.sentence_splitter import SentenceChunk
    from libs.pipeline.windowed_llm_extraction import run_windowed_llm_extraction

    call_count = {"n": 0}
    window_sims = [0.9, 0.3]

    def fake_llm(encounter_text, chunks, state, **kwargs):
        sim = window_sims[call_count["n"] % len(window_sims)]
        call_count["n"] += 1
        return {
            "entities": [],
            "llm_tokens": {
                "input_tokens": 1,
                "output_tokens": 1,
                "cached_tokens": 0,
                "cost_usd": 0.0,
            },
            "extraction_route": "llm",
            "few_shot_max_similarity": sim,
            "extraction_model_name": "test",
            "extraction_model_version": "1",
            "extraction_model_requested_version": "",
            "extraction_model_version_mismatch": False,
        }

    chunks = [
        SentenceChunk(
            sentence_id=f"s{i}",
            text=f"Sentence {i} text content.",
            start=i * 25,
            end=i * 25 + 22,
        )
        for i in range(4)
    ]
    result = run_windowed_llm_extraction(
        " ".join(c.text for c in chunks),
        chunks,
        {},
        window_size=2,
        window_overlap=0,
        context_mode="window_local",
        max_window_input_tokens=16000,
        run_llm_extraction=fake_llm,
    )
    assert result.get("few_shot_max_similarity") == pytest.approx(0.3)
