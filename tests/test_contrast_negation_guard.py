"""VT-A1919820 -- contrast after denies must not mark present findings absent.

Atlas:
  DI: DI-0F9542BF
  DO: DO-15449C6E
  VT: VT-A1919820
  Risk: R-19CAF7E3
"""

from __future__ import annotations

from typing import Any

from libs.ner.contrast_negation_guard import (
    contrast_terminates_modifier,
    fix_contrast_positive_false_absent,
)


def _ents(
    text: str, phrases: list[str], assertion: str = "absent"
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    cursor = 0
    for phrase in phrases:
        start = text.lower().index(phrase.lower(), cursor)
        out.append(
            {
                "text": phrase,
                "evidence": phrase,
                "start": start,
                "end": start + len(phrase),
                "assertion": assertion,
                "evidence_sentence": text,
            }
        )
        cursor = start + len(phrase)
    return out


def test_denies_but_does_have_keeps_first_absent_restores_later() -> None:
    """AC: denies X, but does have Y, Z -- X stays absent, Y and Z become present."""
    text = "Patient denies chest pain, but does have cough, fever, nausea, vomiting."
    ents = _ents(text, ["chest pain", "cough", "fever", "nausea", "vomiting"])
    fix_contrast_positive_false_absent(ents)
    by_text = {ent["text"]: ent["assertion"] for ent in ents}
    assert by_text["chest pain"] == "absent"
    assert by_text["cough"] == "present"
    assert by_text["fever"] == "present"
    assert by_text["nausea"] == "present"
    assert by_text["vomiting"] == "present"
    assert ents[1]["_assertion_guard"] == "contrast_positive"


def test_plain_denies_list_stays_absent() -> None:
    text = "Patient denies cough, fever, nausea, vomiting."
    ents = _ents(text, ["cough", "fever", "nausea", "vomiting"])
    fix_contrast_positive_false_absent(ents)
    assert all(ent["assertion"] == "absent" for ent in ents)


def test_contrast_terminates_modifier_between_denies_and_later_symptom() -> None:
    text = "Patient denies chest pain, but does have cough, fever."
    denies_end = text.index("denies") + len("denies")
    cough_start = text.index("cough")
    pain_start = text.index("chest pain")
    assert contrast_terminates_modifier(text, denies_end, cough_start) is True
    assert contrast_terminates_modifier(text, denies_end, pain_start) is False


def test_post_processing_calls_contrast_guard() -> None:
    from pathlib import Path

    src = Path("libs/pipeline/post_processing.py").read_text(encoding="utf-8")
    assert "fix_contrast_positive_false_absent" in src


def test_local_no_after_contrast_stays_absent() -> None:
    text = "Patient denies chest pain, but does have cough, no fever."
    ents = _ents(text, ["chest pain", "cough", "fever"])
    fix_contrast_positive_false_absent(ents)
    by_text = {ent["text"]: ent["assertion"] for ent in ents}
    assert by_text["chest pain"] == "absent"
    assert by_text["cough"] == "present"
    assert by_text["fever"] == "absent"
