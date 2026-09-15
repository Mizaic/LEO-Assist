"""FINAL US pelvis report is completed; US Pelvis (Requested) is planned.

Owner: ContextRule pack uk_primary_care_context_rules.json.
SurfaceForm maps 'US pelvis' / 'US Pelvis (Transvaginal)' to the procedure.

Atlas: DI-B3B44F09
"""

from __future__ import annotations

from libs.ner.context_engine import apply_context_detection_to_dicts, reload_nlp
from libs.ner.context_rule_catalog import list_packaged_context_rules, packaged_rule_id

FINAL_REPORT = (
    "US PELVIS: US Pelvis This is a FINAL report. "
    "US Pelvis 07-06-2026: US Pelvis (Transvaginal) 07-06-2026:"
)
REQUESTED = "Pathology Request (Complete): FIT (Requested), US Pelvis (Requested)"


def _entity(text: str, doc: str) -> dict:
    start = doc.lower().index(text.lower())
    return {
        "text": text,
        "start": start,
        "end": start + len(text),
        "entity_type": "procedure",
        "assertion": "present",
    }


def test_uk_pack_marks_requested_as_planned() -> None:
    rows = list_packaged_context_rules()
    hits = [
        r
        for r in rows
        if r["literal"].lower() == "(requested)" and r["source"] == "builtin"
    ]
    assert hits, "(requested) must be in the UK ConText pack"
    assert hits[0]["category"] == "PLANNED"
    assert hits[0]["rule_id"] == packaged_rule_id("uk", "(requested)")


def test_final_us_pelvis_report_stays_present() -> None:
    reload_nlp()
    ent = _entity("US Pelvis", FINAL_REPORT)
    apply_context_detection_to_dicts(FINAL_REPORT, [ent])
    assert ent["assertion"] == "present"


def test_us_pelvis_requested_is_planned() -> None:
    reload_nlp()
    ent = _entity("US Pelvis", REQUESTED)
    apply_context_detection_to_dicts(REQUESTED, [ent])
    assert ent["assertion"] == "planned"
