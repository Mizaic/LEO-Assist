"""VT for DI-0C766F85 -- document extraction quality score."""

from __future__ import annotations

from libs.pipeline.document_quality import (
    form_fingerprint,
    score_document_quality,
)


NSS_FORM = """
Appendix A: Referral criteria
| Unexplained DVT | [ ] |
| GP gut feeling of cancer diagnosis | [X] |
"""

GYNAE_FORM = """
Section A: Gynaecological Cancer type suspected
Ovary [ ] Cervix [X] Endometrium [ ]
Please take a Ca125 by the time of referral
Section B: Signs/symptoms
B1. Lesion suspicious of cancer of cervix | Yes [X] No [ ]
"""

GYNAE_FORM_OTHER_PATIENT = """
Section A: Gynaecological Cancer type suspected
Ovary [X] Cervix [ ] Endometrium [ ]
Please take a Ca125 by the time of referral
Section B: Signs/symptoms
B1. Lesion suspicious of cancer of cervix | Yes [ ] No [X]
"""


def test_score_is_between_zero_and_one_and_ignores_llm_confidence() -> None:
    low = score_document_quality(
        GYNAE_FORM,
        few_shot_max_similarity=0.12,
        known_fingerprints={},
        llm_confidence=0.99,
    )
    same = score_document_quality(
        GYNAE_FORM,
        few_shot_max_similarity=0.12,
        known_fingerprints={},
        llm_confidence=0.10,
    )
    assert 0.0 <= low.document_quality_score <= 1.0
    assert low.document_quality_score == same.document_quality_score
    assert "few_shot_ood" in low.quality_reasons
    assert low.few_shot_max_similarity == 0.12
    assert low.form_fingerprint_id == "unknown"


def test_same_template_different_values_share_fingerprint() -> None:
    a = form_fingerprint(GYNAE_FORM)
    b = form_fingerprint(GYNAE_FORM_OTHER_PATIENT)
    assert a
    assert a == b


def test_known_and_unknown_templates_do_not_match() -> None:
    nss_id = form_fingerprint(NSS_FORM)
    gynae_id = form_fingerprint(GYNAE_FORM)
    assert nss_id != gynae_id
    scored = score_document_quality(
        GYNAE_FORM,
        few_shot_max_similarity=0.80,
        known_fingerprints={"nss": nss_id},
    )
    assert scored.form_fingerprint_id == "unknown"
    assert "unknown_form_template" in scored.quality_reasons


def test_merge_results_stores_document_quality() -> None:
    from libs.pipeline_graph.subgraphs.extraction import merge_results

    out = merge_results(
        {
            "encounter_text": GYNAE_FORM,
            "entities": [{"text": "Cervix"}],
            "few_shot_max_similarity": 0.11,
        }
    )
    quality = out["document_quality"]
    assert 0.0 <= quality["document_quality_score"] <= 1.0
    assert "few_shot_ood" in quality["quality_reasons"]
    assert "few_shot_max_similarity" in quality
    assert out["encounter_text"] == GYNAE_FORM


def test_known_fingerprint_raises_match_id() -> None:
    gynae_id = form_fingerprint(GYNAE_FORM)
    scored = score_document_quality(
        GYNAE_FORM_OTHER_PATIENT,
        few_shot_max_similarity=0.80,
        known_fingerprints={"gynae-2ww": gynae_id},
    )
    assert scored.form_fingerprint_id == "gynae-2ww"
    assert "unknown_form_template" not in scored.quality_reasons
    assert scored.document_quality_score >= 0.6
