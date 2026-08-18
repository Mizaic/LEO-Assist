"""VT-A1919820 -- False-absent assertion guards.

Atlas:
  DI: DI-0F9542BF
  DO: DO-15449C6E
  VT: VT-A1919820
  Risk: R-19CAF7E3

Covers treatment-failure ConText PSEUDO rules, lifestyle-status restoration,
PMH background-of false-absent restoration, true negation remaining absent,
and same-sentence ConText so 'to exclude' does not flip the next sentence.
"""

from __future__ import annotations

from typing import Any

from libs.ner.context_engine import apply_context_detection_to_dicts, reload_nlp
from libs.pipeline.post_processing import (
    apply_false_absent_assertion_guards,
    fix_lifestyle_status_assertions,
    fix_pmh_list_false_absent,
)


def _span_ent(text: str, phrase: str, assertion: str = "present") -> dict[str, Any]:
    start = text.index(phrase)
    return {
        "text": phrase,
        "evidence": phrase,
        "start": start,
        "end": start + len(phrase),
        "assertion": assertion,
        "evidence_sentence": text,
    }


def test_ac1_treatment_failure_omeprazole_stays_present() -> None:
    """AC1: not-responded PSEUDO keeps omeprazole present."""
    reload_nlp()
    text = (
        "which has not responded adequately to proton pump inhibitor "
        "therapy (omeprazole 20 mg daily)."
    )
    ents = [
        _span_ent(text, "omeprazole 20 mg daily"),
        _span_ent(text, "proton pump inhibitor therapy"),
    ]
    apply_context_detection_to_dicts(text, ents)
    assert ents[0]["assertion"] == "present"
    assert ents[1]["assertion"] == "present"


def test_ac2_true_negation_remains_absent() -> None:
    """AC2: No chest pain / no dysphagia stay absent after ConText."""
    reload_nlp()
    no_pain = "No chest pain."
    pain = [_span_ent(no_pain, "chest pain")]
    apply_context_detection_to_dicts(no_pain, pain)
    assert pain[0]["assertion"] == "absent"

    no_dysphagia = "He reports no dysphagia at present."
    ents = [_span_ent(no_dysphagia, "dysphagia")]
    apply_context_detection_to_dicts(no_dysphagia, ents)
    assert ents[0]["assertion"] == "absent"


def test_ac3_ex_smoker_absent_restored_to_present() -> None:
    """AC3: lifestyle-status guard restores Ex-smoker present."""
    ent = {
        "assertion": "absent",
        "term": "Ex-smoker (finding)",
        "concept_id": "8517006",
        "evidence": "former smoker",
        "text": "former smoker",
    }
    fix_lifestyle_status_assertions([ent])
    assert ent["assertion"] == "present"
    assert ent["_assertion_guard"] == "lifestyle_status"

    never = {
        "assertion": "absent",
        "term": "Never smoked tobacco (finding)",
        "concept_id": "266919005",
        "text": "never smoked",
    }
    fix_lifestyle_status_assertions([never])
    assert never["assertion"] == "present"


_ROBERT_LETTER = (
    "Dear Colleague,\n\n"
    "I am writing to refer Robert for urgent direct access ultrasound "
    "of the abdomen. He has presented with a 2-month history of "
    "dyspeptic symptoms that have not responded to standard proton "
    "pump inhibitor therapy. He reports early satiety and a sensation "
    "of upper abdominal fullness.\n\n"
    "On examination, I have identified a firm, palpable mass in the "
    "epigastric region, which is consistent with an enlarged gall "
    "bladder. Given the clinical findings and the treatment-resistant "
    "nature of his symptoms, I am concerned about underlying gall "
    "bladder pathology and would like urgent imaging to exclude "
    "malignancy.\n\n"
    "Robert has a background of GORD and obesity. He is otherwise well."
)


def _letter_ent(phrase: str) -> dict[str, Any]:
    start = _ROBERT_LETTER.index(phrase)
    return {
        "text": phrase,
        "evidence": phrase,
        "start": start,
        "end": start + len(phrase),
        "assertion": "present",
        "evidence_sentence": _ROBERT_LETTER,
    }


def test_ac5_exclude_does_not_cross_sentence_onto_pmh() -> None:
    """AC5: to exclude malignancy does not mark GORD or obesity absent."""
    reload_nlp()
    ents = [
        _letter_ent("malignancy"),
        _letter_ent("GORD"),
        _letter_ent("obesity"),
    ]
    apply_context_detection_to_dicts(_ROBERT_LETTER, ents)
    by_text = {ent["text"]: ent["assertion"] for ent in ents}
    assert by_text["malignancy"] == "absent"
    assert by_text["GORD"] == "historical"
    assert by_text["obesity"] == "historical"


def test_ac4_background_of_gord_false_absent_restored() -> None:
    """AC4: PMH guard restores GORD absent inside background-of list."""
    sentence = "Robert has a background of GORD and obesity. He is otherwise well."
    gord = {
        "assertion": "absent",
        "text": "GORD",
        "evidence": "GORD",
        "evidence_sentence": sentence,
    }
    obesity = {
        "assertion": "present",
        "text": "obesity",
        "evidence": "obesity",
        "evidence_sentence": sentence,
    }
    fix_pmh_list_false_absent([gord, obesity])
    assert gord["assertion"] == "present"
    assert gord["_assertion_guard"] == "pmh_list_false_absent"
    assert obesity["assertion"] == "present"


def test_pmh_guard_leaves_no_history_of_absent() -> None:
    sentence = "He has no history of GORD or peptic ulcer disease."
    ent = {
        "assertion": "absent",
        "text": "GORD",
        "evidence": "GORD",
        "evidence_sentence": sentence,
    }
    fix_pmh_list_false_absent([ent])
    assert ent["assertion"] == "absent"


def test_lifestyle_guard_does_not_flip_bare_smoker_denial() -> None:
    ent = {
        "assertion": "absent",
        "term": "Smoker (finding)",
        "concept_id": "77176002",
        "text": "smoker",
        "evidence": "smoker",
        "evidence_sentence": "He denies being a smoker.",
    }
    fix_lifestyle_status_assertions([ent])
    assert ent["assertion"] == "absent"


def test_apply_false_absent_assertion_guards_combined() -> None:
    ents = [
        {
            "assertion": "absent",
            "term": "Ex-smoker (finding)",
            "concept_id": "8517006",
            "text": "former smoker",
        },
        {
            "assertion": "absent",
            "text": "GORD",
            "evidence": "GORD",
            "evidence_sentence": "background of GORD and obesity",
        },
    ]
    apply_false_absent_assertion_guards(ents)
    assert ents[0]["assertion"] == "present"
    assert ents[1]["assertion"] == "present"
