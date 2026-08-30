"""VT-BA44A8B3 -- Suspected cancer and FH situation assertion present.

Atlas:
  DI: DI-95CB940F
  DO: DO-847F1ED5
  VT: VT-BA44A8B3
  Risk: R-54048593
"""

from __future__ import annotations

import json

from libs.pipeline.post_processing import (
    apply_false_absent_assertion_guards,
    fix_situation_present_assertions,
)
from libs.prompts.annotation_guidelines_v1 import ANNOTATION_GUIDELINES_V1
from libs.prompts.extraction_examples import EXTRACTION_EXAMPLES
from libs.prompts.extraction_v1 import EXTRACTION_SYSTEM_V1


def test_suspected_cancer_situation_possible_restored() -> None:
    ent = {
        "label": "situation",
        "assertion": "possible",
        "text": "suspected cancer pathway for stomach cancer",
        "lookup_term": ("malignant neoplasm of upper gastrointestinal tract suspected"),
        "term": (
            "Malignant neoplasm of upper gastrointestinal tract "
            "suspected (situation)"
        ),
    }
    fix_situation_present_assertions([ent])
    assert ent["assertion"] == "present"
    assert ent["_assertion_guard"] == "situation_suspected_cancer"


def test_family_history_situation_family_restored() -> None:
    ent = {
        "label": "situation",
        "assertion": "family",
        "text": "Mother had breast cancer",
        "lookup_term": "family history of malignant neoplasm of breast",
        "term": "Family history of malignant neoplasm of breast (situation)",
    }
    fix_situation_present_assertions([ent])
    assert ent["assertion"] == "present"
    assert ent["_assertion_guard"] == "situation_family_history"


def test_apply_guards_includes_situation_present() -> None:
    ents = [
        {
            "label": "situation",
            "assertion": "possible",
            "text": "breast suspected cancer pathway",
            "lookup_term": "malignant neoplasm of breast suspected",
        }
    ]
    apply_false_absent_assertion_guards(ents)
    assert ents[0]["assertion"] == "present"


def test_disorder_possible_not_rewritten() -> None:
    ent = {
        "label": "disorder",
        "assertion": "possible",
        "text": "stomach cancer",
        "lookup_term": "stomach cancer",
    }
    fix_situation_present_assertions([ent])
    assert ent["assertion"] == "possible"
    assert "_assertion_guard" not in ent


def test_breast_pathway_few_shot_is_situation_present() -> None:
    example = next(
        ex
        for ex in EXTRACTION_EXAMPLES
        if "Breast suspected pathway" in str(ex.get("description", ""))
    )
    terms = json.loads(example["output"])["terms"]
    assert len(terms) == 1
    assert terms[0]["semantic_tag"] == "situation"
    assert terms[0]["assertion"] == "present"
    assert "breast" in terms[0]["lookup_term"]


def test_fh_few_shot_is_situation_present() -> None:
    example = next(
        ex for ex in EXTRACTION_EXAMPLES if ex.get("description") == "Family history"
    )
    terms = json.loads(example["output"])["terms"]
    assert terms[0]["semantic_tag"] == "situation"
    assert terms[0]["assertion"] == "present"
    assert "family history" in terms[0]["lookup_term"]


def test_prompt_keeps_site_named_suspected_cancer() -> None:
    assert "site-named suspected cancer as situation" in EXTRACTION_SYSTEM_V1
    assert "Family history of * (situation)" in EXTRACTION_SYSTEM_V1


def test_guidelines_fh_assertion_present() -> None:
    assert "FH of breast cancer | situation | present" in ANNOTATION_GUIDELINES_V1


def test_situation_guard_does_not_restore_negated_family_history() -> None:
    """A denied family history must not be rewritten as present.

    Atlas: DI-95CB940F / VT-BA44A8B3
    """
    ent = {
        "label": "situation",
        "assertion": "family",
        "text": "There is no known family history of breast cancer "
        "on either the maternal or paternal side",
        "evidence_sentence": "There is no known family history of breast cancer "
        "on either the maternal or paternal side",
        "lookup_term": "family history of malignant neoplasm of breast",
        "term": "Family history of malignant neoplasm of breast (situation)",
    }
    fix_situation_present_assertions([ent])
    assert ent["assertion"] != "present"
    assert "_assertion_guard" not in ent


def test_negated_family_history_present_is_forced_absent() -> None:
    """Extractor present on 'no known family history' must become absent.

    Atlas: DI-95CB940F / VT-BA44A8B3
    """
    ent = {
        "label": "situation",
        "assertion": "present",
        "text": "There is no known family history of breast cancer "
        "on either the maternal or paternal side",
        "evidence_sentence": "There is no known family history of breast cancer "
        "on either the maternal or paternal side",
        "term": "Family history of malignant neoplasm of breast (situation)",
        "concept_id": "429740004",
    }
    apply_false_absent_assertion_guards([ent])
    assert ent["assertion"] == "absent"


def test_situation_guard_does_not_match_preferred_term() -> None:
    """A SNOMED preferred term must not restore present on its own.

    Atlas: DI-0B907354 / VT-24D1E4F6
    """
    ent = {
        "label": "situation",
        "assertion": "possible",
        "text": "ovarian cyst",
        "evidence_sentence": "Ultrasound shows an ovarian cyst.",
        "term": "Malignant neoplasm of ovary suspected (situation)",
        "lookup_term": "malignant neoplasm of ovary suspected",
        "normalized": "Malignant neoplasm of ovary suspected",
    }
    fix_situation_present_assertions([ent])
    assert ent["assertion"] == "possible"
    assert "_assertion_guard" not in ent
