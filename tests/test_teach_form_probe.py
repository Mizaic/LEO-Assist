"""Teach-form probe skips a ticked No that is not a present fact.

Atlas:
  DI: DI-5C9CA57B
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".cursor/skills/teach-paused-form/scripts"))

from probe_form_schema import unmatched_ticks  # noqa: E402


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
