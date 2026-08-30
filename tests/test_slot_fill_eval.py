"""Red tests: golden letter fails when a fact is not in the letter.

Atlas trace:
  DI: DI-9D76A65C
  DO: DO-1E60B1D4
  VT: VT-12EBF8F0
  Risk: R-3B38CA10
"""

from __future__ import annotations

from pathlib import Path

from libs.referral_quality.golden_corpus import load_golden_case
from libs.referral_quality.slot_fill_eval import invented_facts

_FIXTURE_DIR = (
    Path(__file__).parent / "fixtures" / "golden_corpus" / "rk5_117038_demo-v1"
)


def test_golden_letter_fails_if_fact_not_in_letter() -> None:
    case = load_golden_case(_FIXTURE_DIR)
    facts = [{"text": "left ovarian cyst 4 cm"}]
    hits = invented_facts(facts, case.letter)
    assert hits
    assert "ovarian cyst" in hits[0].lower()


def test_golden_letter_expected_facts_are_verbatim() -> None:
    case = load_golden_case(_FIXTURE_DIR)
    facts = [
        {"text": item.text, "evidence_text": item.evidence_text}
        for item in case.expected_facts
    ]
    assert invented_facts(facts, case.letter) == []
