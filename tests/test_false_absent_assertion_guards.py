"""VT-A1919820 -- False-absent assertion guards.

Atlas:
  DI: DI-0F9542BF
  DO: DO-15449C6E
  VT: VT-A1919820
  Risk: R-19CAF7E3

Covers treatment-failure ConText PSEUDO rules, lifestyle-status restoration,
PMH background-of false-absent restoration, and true negation remaining absent.
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
