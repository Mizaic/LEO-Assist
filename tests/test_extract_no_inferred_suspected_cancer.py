"""A symptom span must not become a suspected-cancer fact.

Run 40dc9da6 (patient 4242677553) coded the span "rash on her left breast"
as 134405005 Malignant neoplasm of breast suspected at 0.98 confidence. The
letter states no suspicion anywhere. The referral extract prompt invited it
by offering "malignant neoplasm of breast suspected" as a ready-made
lookup_term shape for any site-named breast finding.

Atlas: DI-BB3EA22A / VT-0686914B / R-476643F8
"""

from __future__ import annotations

import json
import re

from libs.prompts.extraction_examples import EXTRACTION_EXAMPLES
from libs.prompts.extraction_v1 import EXTRACTION_SYSTEM_V1
from libs.prompts.referral_extraction_v1 import REFERRAL_EXTRACTION_SYSTEM_V1
from scripts.seed_prompt_configs import SEED_PROMPTS


def _flat(prompt: str) -> str:
    """Collapse whitespace so a rule can be reflowed without breaking a test."""
    return re.sub(r"\s+", " ", prompt)


_STATED_SUSPICION = "only when the letter states the suspicion"
_KEEPS_OWN_TERM = "A symptom or sign keeps its own lookup term"
_RASH_NOT_CANCER = "is a rash finding, not suspected breast cancer"
_RASH_INPUT = "rash on her left breast"

_BREAST_CANCER_SUSPECTED = "134405005"
_RASH = "271807003"

# The permissive rule, and the qualifier that must travel with it.
_PERMISSIVE = "site-named suspected cancer as situation (present)"
_QUALIFIER = "when the letter states the suspicion"


def test_referral_prompt_requires_suspicion_stated_in_the_letter() -> None:
    assert _STATED_SUSPICION in _flat(REFERRAL_EXTRACTION_SYSTEM_V1)


def test_referral_prompt_keeps_a_symptom_span_on_its_own_lookup_term() -> None:
    referral = _flat(REFERRAL_EXTRACTION_SYSTEM_V1)
    assert _KEEPS_OWN_TERM in referral
    assert _RASH_NOT_CANCER in referral


def test_extract_prompt_carries_the_same_rule() -> None:
    extraction = _flat(EXTRACTION_SYSTEM_V1)
    assert _STATED_SUSPICION in extraction
    assert _KEEPS_OWN_TERM in extraction


def test_few_shot_keeps_a_breast_rash_as_a_rash() -> None:
    matches = [row for row in EXTRACTION_EXAMPLES if _RASH_INPUT in row["input"]]
    assert len(matches) == 1
    terms = json.loads(matches[0]["output"])["terms"]
    assert [term["lookup_term"] for term in terms] == ["rash"]
    assert terms[0]["semantic_tag"] == "finding"


def test_few_shot_does_not_emit_a_suspected_cancer_situation() -> None:
    matches = [row for row in EXTRACTION_EXAMPLES if _RASH_INPUT in row["input"]]
    assert len(matches) == 1
    output = matches[0]["output"]
    assert "suspected" not in output.lower()
    assert _BREAST_CANCER_SUSPECTED not in output


def test_seed_carries_the_rule_and_the_rash_example() -> None:
    for name in ("extraction", "referral_extraction"):
        row = next(item for item in SEED_PROMPTS if item["name"] == name)
        assert _STATED_SUSPICION in _flat(row["system_prompt"])
        inputs = [shot["input"] for shot in row["few_shot_examples"]]
        assert any(_RASH_INPUT in text for text in inputs)


def test_rash_and_suspected_breast_cancer_are_different_codes() -> None:
    assert _RASH != _BREAST_CANCER_SUSPECTED


def test_every_permissive_keep_rule_is_qualified_in_place() -> None:
    """Both prompts declare that earlier rules win when rules conflict.

    So the constraint cannot live only in a later paragraph: each place that
    permits a site-named suspected-cancer situation has to carry the
    stated-suspicion qualifier with it.
    """
    for prompt in (EXTRACTION_SYSTEM_V1, REFERRAL_EXTRACTION_SYSTEM_V1):
        flat = _flat(prompt).lower()
        found = 0
        start = 0
        while True:
            at = flat.find(_PERMISSIVE, start)
            if at < 0:
                break
            found += 1
            window = flat[at : at + len(_PERMISSIVE) + 100]
            assert _QUALIFIER in window, window
            start = at + 1
        assert found >= 1
