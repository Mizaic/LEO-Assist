"""VT-A1919820 -- locally affirmed findings must not flip to absent.

Five-patient referral faults: nearby form 'No' / ConText historical
cues inverted present observations (vulval sores noted, uses Vaseline,
new postmenopausal bleeding, urine is clear).
"""

from __future__ import annotations

from typing import Any

from libs.ner.affirmed_finding_guard import fix_locally_affirmed_assertions
from libs.ner.context_engine import apply_context_detection_to_dicts, reload_nlp
from libs.pipeline.post_processing import (
    apply_false_absent_assertion_guards,
    fix_polarity_encoded_findings,
)


def _span_ent(text: str, phrase: str, assertion: str = "present") -> dict[str, Any]:
    start = text.lower().index(phrase.lower())
    return {
        "text": phrase,
        "evidence": phrase,
        "start": start,
        "end": start + len(phrase),
        "assertion": assertion,
        "evidence_sentence": text,
    }


def test_vulval_sores_noted_stays_present_beside_form_no() -> None:
    text = "Cognitive Impairment - Yes [ ] No [X] " "Two open vulval sores noted."
    ent = _span_ent(text, "vulval sores", "absent")
    fix_locally_affirmed_assertions([ent])
    assert ent["assertion"] == "present"
    assert ent["_assertion_guard"] == "locally_affirmed"


def test_uses_vaseline_stays_present() -> None:
    text = "Uses Vaseline (petroleum jelly) to the vulva."
    ent = _span_ent(text, "Vaseline", "absent")
    fix_locally_affirmed_assertions([ent])
    assert ent["assertion"] == "present"


def test_new_postmenopausal_bleeding_is_not_historical() -> None:
    text = (
        "She is 20 years postmenopausal and has new postmenopausal "
        "bleeding for 4 days."
    )
    ent = _span_ent(text, "postmenopausal bleeding", "historical")
    fix_locally_affirmed_assertions([ent])
    assert ent["assertion"] == "present"


def test_urine_is_clear_is_present() -> None:
    text = "Urine is clear. Denies urinary frequency."
    ent = _span_ent(text, "Urine is clear", "absent")
    fix_locally_affirmed_assertions([ent])
    assert ent["assertion"] == "present"


def test_no_chest_pain_stays_absent() -> None:
    text = "No chest pain noted."
    ent = _span_ent(text, "chest pain", "absent")
    fix_locally_affirmed_assertions([ent])
    assert ent["assertion"] == "absent"


def test_no_bleeding_noted_stays_absent_when_span_starts_at_zero() -> None:
    """Negation anywhere in the span must block restore, not only a prefix.

    Atlas: DI-0B907354 / VT-24D1E4F6
    """
    text = "no bleeding noted"
    ent = {
        "text": "bleeding noted",
        "start": 0,
        "end": len("bleeding noted"),
        "assertion": "absent",
        "evidence_sentence": text,
    }
    fix_locally_affirmed_assertions([ent])
    assert ent["assertion"] == "absent"


def test_discharge_observed_restored_after_context() -> None:
    reload_nlp()
    text = "Cognitive Impairment - Yes [ ] No [X] " "Mild vaginal discharge observed."
    ents = [_span_ent(text, "vaginal discharge")]
    apply_context_detection_to_dicts(text, ents)
    apply_false_absent_assertion_guards(ents)
    assert ents[0]["assertion"] == "present"


def test_cervix_not_seen_polarity_restored() -> None:
    ent = {
        "assertion": "absent",
        "semantic_tag": "finding",
        "term": "Cervix not seen (finding)",
        "text": "Cervix could not be fully visualised",
    }
    fix_polarity_encoded_findings([ent])
    assert ent["assertion"] == "present"
    assert ent["_assertion_guard"] == "polarity_encoded_finding"


def test_apply_guards_include_locally_affirmed() -> None:
    text = "Two open vulval sores noted."
    ent = _span_ent(text, "vulval sores", "absent")
    apply_false_absent_assertion_guards([ent])
    assert ent["assertion"] == "present"


def test_context_absent_not_restored_by_later_noted() -> None:
    """ConText already owns 'no'. A later 'noted' must not flip absent.

    Atlas: DI-0F9542BF / DO-15449C6E / VT-A1919820
    """
    text = "There is no pelvic pain. Discharge noted on examination."
    ent = {
        "text": "pelvic pain",
        "start": 0,
        "end": 3,
        "assertion": "absent",
        "_assertion_source": "context",
        "evidence_sentence": text,
    }
    fix_locally_affirmed_assertions([ent])
    apply_false_absent_assertion_guards([ent])
    assert ent["assertion"] == "absent"
