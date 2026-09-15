"""A documented benign result must become a no-evidence-of-cancer fact.

Run 40dc9da6 (patient 4242677553) read "The biopsy was reported as benign"
and produced no fact at all. The extract prompt only recognised a benign
result after a completed 2WW or fast-track workup, so the model emitted the
bare word "benign". Terminology returned zero candidates for it and the span
was dropped with a warning.

Atlas: DI-F03B0113 / VT-BDD72AC6 / R-1D675A0D
"""

from __future__ import annotations

import json
import re

from libs.prompts.extraction_examples import EXTRACTION_EXAMPLES
from libs.prompts.extraction_v1 import EXTRACTION_SYSTEM_V1
from libs.prompts.referral_extraction_v1 import REFERRAL_EXTRACTION_SYSTEM_V1
from libs.terminology.no_cancer_phrases import (
    NEVER_NO_CANCER_PHRASES,
    NO_CANCER_RESULT_PHRASES,
    NO_EVIDENCE_OF_CANCER_CONCEPT_ID,
)
from libs.terminology.surface_normalize import normalize_surface
from scripts.seed_prompt_configs import SEED_PROMPTS


def _flat(prompt: str) -> str:
    """Collapse whitespace so a rule can be reflowed without breaking a test."""
    return re.sub(r"\s+", " ", prompt)


_NO_PATHWAY_NEEDED = "whether or not the letter names a 2WW or fast-track pathway"
_NOT_BARE_BENIGN = 'Do not emit the bare word "benign"'
_OLD_NARROW_RULE = "If a completed 2WW / fast-track workup is documented as benign"
_BENIGN_INPUT = "The biopsy was reported as benign"
_NO_CANCER_TERM = "no evidence of cancer found"

# The GP-letter phrasings that produced nothing on run 40dc9da6.
_GP_LETTER_PHRASES = (
    "reported as benign",
    "was reported as benign",
    "biopsy was reported as benign",
    "biopsy was benign",
    "benign biopsy",
)


def test_extract_prompt_drops_the_named_pathway_precondition() -> None:
    extraction = _flat(EXTRACTION_SYSTEM_V1)
    assert _OLD_NARROW_RULE not in extraction
    assert _NO_PATHWAY_NEEDED in extraction


def test_extract_prompt_asks_for_the_result_phrase_not_the_bare_word() -> None:
    assert _NOT_BARE_BENIGN in _flat(EXTRACTION_SYSTEM_V1)


def test_referral_prompt_carries_the_same_rule() -> None:
    referral = _flat(REFERRAL_EXTRACTION_SYSTEM_V1)
    assert _NO_PATHWAY_NEEDED in referral
    assert _NOT_BARE_BENIGN in referral


def test_few_shot_codes_a_benign_biopsy_as_no_evidence_of_cancer() -> None:
    matches = [row for row in EXTRACTION_EXAMPLES if _BENIGN_INPUT in row["input"]]
    assert len(matches) == 1
    terms = json.loads(matches[0]["output"])["terms"]
    assert len(terms) == 1
    assert terms[0]["lookup_term"].lower() == _NO_CANCER_TERM
    assert terms[0]["assertion"] == "present"
    assert terms[0]["text"] != "benign"


def test_seed_carries_the_rule_and_the_benign_example() -> None:
    for name in ("extraction", "referral_extraction"):
        row = next(item for item in SEED_PROMPTS if item["name"] == name)
        assert _NO_PATHWAY_NEEDED in _flat(row["system_prompt"])
        inputs = [shot["input"] for shot in row["few_shot_examples"]]
        assert any(_BENIGN_INPUT in text for text in inputs)


def test_gp_letter_phrases_are_in_the_approved_list() -> None:
    approved = {normalize_surface(phrase) for phrase in NO_CANCER_RESULT_PHRASES}
    for phrase in _GP_LETTER_PHRASES:
        assert normalize_surface(phrase) in approved


def test_the_target_concept_is_no_evidence_of_cancer_found() -> None:
    assert NO_EVIDENCE_OF_CANCER_CONCEPT_ID == "395100000"


def test_bare_benign_and_benign_disorders_stay_out() -> None:
    approved = {normalize_surface(phrase) for phrase in NO_CANCER_RESULT_PHRASES}
    for phrase in NEVER_NO_CANCER_PHRASES:
        assert normalize_surface(phrase) not in approved
    assert "benign" in NEVER_NO_CANCER_PHRASES
    assert "benign prostatic hyperplasia" in NEVER_NO_CANCER_PHRASES


def test_every_approved_phrase_carries_a_result_word() -> None:
    """A polarity word alone is not a result. It must name what was tested."""
    for phrase in NO_CANCER_RESULT_PHRASES:
        assert len(normalize_surface(phrase).split()) >= 2, phrase
