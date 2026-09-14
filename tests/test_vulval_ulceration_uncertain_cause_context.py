"""ConText must not hide unexplained vulval ulceration.

NHS 4245590920: 'Vulval ulceration of uncertain cause' then
'Does not appear consistent with lichen sclerosus' was marked absent.
That dropped NG12 1.5.17.

Owner: ContextRule pack uk_primary_care_context_rules.json.

Atlas: DI-0F9542BF, DO-15449C6E, VT-DE22B021.
"""

from __future__ import annotations

from libs.ner.context_engine import apply_context_detection_to_dicts, reload_nlp
from libs.ner.context_rule_catalog import list_packaged_context_rules, packaged_rule_id

# Same clause, no sentence break -- the GP letter and the stored
# evidence_sentence both run these words together.
DOC = (
    "Impression Vulval ulceration of uncertain cause "
    "Does not appear consistent with lichen sclerosus "
    "Meets criteria for urgent two-week wait referral due to unexplained "
    "vulval ulceration."
)

# Real letter shape: many earlier 'No' ticks, then the impression.
LETTER = (
    "BMI: 19.96 Kg/m2 Co-morbidities including mobility concerns: "
    "Cognitive Impairment - Yes [ ] No x [ ] Consultation. "
    "Presenting Complaint Vulval soreness and presence of sores/blisters "
    "for several months. No internal vaginal pain or bleeding. "
    "No postmenopausal bleeding. Symptoms are external only. "
    "No palpable mass or unexplained bleeding. "
    "Examination Two open vulval sores noted. "
    "Impression Vulval ulceration of uncertain cause "
    "Does not appear consistent with lichen sclerosus "
    "Meets criteria for urgent two-week wait referral due to unexplained "
    "vulval ulceration."
)

ULCER = "Vulval ulceration of uncertain cause"
LICHEN = "lichen sclerosus"


def _entity(text: str, doc: str) -> dict:
    start = doc.index(text)
    return {
        "text": text,
        "start": start,
        "end": start + len(text),
        "entity_type": "finding",
        "assertion": "present",
    }


def test_uk_pack_blocks_does_not_appear_consistent_with() -> None:
    rows = list_packaged_context_rules()
    hits = [
        r
        for r in rows
        if r["literal"].lower() == "does not appear consistent with"
        and r["source"] == "builtin"
    ]
    assert hits, "does not appear consistent with must be in the UK ConText pack"
    assert hits[0]["category"] == "NEGATED_EXISTENCE"
    assert hits[0]["direction"] == "PSEUDO"
    assert hits[0]["rule_id"] == packaged_rule_id(
        "uk", "does not appear consistent with"
    )


def test_uk_pack_has_of_uncertain_cause() -> None:
    rows = list_packaged_context_rules()
    hits = [
        r
        for r in rows
        if r["literal"].lower() == "of uncertain cause" and r["source"] == "builtin"
    ]
    assert hits, "of uncertain cause must be in the UK ConText pack"
    assert hits[0]["category"] == "POSSIBLE_EXISTENCE"
    assert hits[0]["direction"] == "BACKWARD"


def test_ulceration_of_uncertain_cause_is_not_absent() -> None:
    reload_nlp()
    ent = _entity(ULCER, DOC)
    apply_context_detection_to_dicts(DOC, [ent])
    assert ent["assertion"] != "absent", (
        "uncertain cause plus 'does not appear consistent with' "
        "must not mark ulceration absent"
    )
    assert ent["assertion"] in {"present", "possible"}


def test_lichen_sclerosus_after_does_not_appear_is_absent() -> None:
    reload_nlp()
    ent = _entity(LICHEN, DOC)
    apply_context_detection_to_dicts(DOC, [ent])
    assert ent["assertion"] == "absent"


def test_full_letter_ulceration_is_not_absent() -> None:
    reload_nlp()
    ent = _entity(ULCER, LETTER)
    apply_context_detection_to_dicts(LETTER, [ent])
    assert ent["assertion"] != "absent", (
        "earlier form No boxes and 'does not appear consistent with' "
        "must not mark unexplained vulval ulceration absent"
    )
    assert ent["assertion"] in {"present", "possible"}
