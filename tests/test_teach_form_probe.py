"""Teach-form probe skips a ticked No that is not a present fact.

The probe also runs the same skip-box fill and save check as the product
save, so a green probe means the save will not be refused.

Atlas:
  DI: DI-5C9CA57B
  DI: DI-455C4EF1 (probe runs the fill and the save check)
"""

from __future__ import annotations

import sys
from pathlib import Path

from tests.test_form_skip_boxes import HOSPITAL_BOXES, LETTER, _detected

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".cursor/skills/teach-paused-form/scripts"))

from probe_form_schema import probe, unmatched_ticks  # noqa: E402


def _payload(sections: list[dict]) -> dict:
    return {
        "fingerprint": "sfh-lower-gi-probe",
        "form_name": "Lower GI",
        "sections": sections,
    }


def test_probe_fills_skip_sections_and_passes_the_save_check() -> None:
    report = probe(LETTER, _payload(_detected()))
    assert report["teach_problems"] == []
    (hospital,) = [s for s in report["filled_sections"] if s["section_id"] == "S5"]
    assert [item["pattern"] for item in hospital["items"]] == HOSPITAL_BOXES


def test_probe_is_red_when_the_save_check_would_refuse() -> None:
    clinical_only = [s for s in _detected() if s["section_type"] != "admin"]
    report = probe(LETTER, _payload(clinical_only))
    assert report["teach_problems"]
    assert "does not match the letter" in report["teach_problems"][0]
    assert report["green"] is False


def test_probe_skips_no_box_after_the_word() -> None:
    letter = (
        "| BMI: 31.78 Kg/m2 Co-morbidities including mobility concerns: "
        "Cognitive Impairment - Yes [ ] No [X] |\n"
    )
    assert unmatched_ticks(letter, set()) == []


def test_probe_skips_ticked_no_before_the_word() -> None:
    letter = (
        "Cognitive Impairment - [ ] Yes [X] No Telephone Consultation "
        "Telephone follow-up: Yes\n"
    )
    assert unmatched_ticks(letter, set()) == []
