"""DO-LEO-AI-191 v1.1 -- pin the v2 SBAR prompt contract.

The v2 SBAR prompts (Situation, Background, Recommendation) must:

1. Forbid inline encounter / document / chunk ids and the literal
   ``SOURCE:`` token in the narrative -- source ids stay in the
   structured ``citations`` array.
2. Set an explicit plain-English directive (reading age of 11, NHS
   clinical terms allowed, active voice).
3. Keep the prompt-injection rule that treats CONTEXT free text as
   data not instructions.
4. Be wired up in the runtime as version 2 (``_default_prompt`` resolves
   to v2 via ``_SBAR_PROMPT_VERSIONS``).
5. Be registered in the seed script at both v1 (legacy) and v2
   (current) so a fresh dev environment seeds both.
"""

from __future__ import annotations

import pathlib
import re

from libs.prompts.sbar_background_v1 import SBAR_BACKGROUND_SYSTEM_V1
from libs.prompts.sbar_recommendation_v1 import SBAR_RECOMMENDATION_SYSTEM_V1
from libs.prompts.sbar_situation_v1 import SBAR_SITUATION_SYSTEM_V1
from libs.sbar.prompt_calls import (
    _LEGACY_SBAR_PROMPT_VERSIONS,
    _PROMPT_NAME_BACKGROUND,
    _PROMPT_NAME_RECALL,
    _PROMPT_NAME_RECOMMENDATION,
    _PROMPT_NAME_SITUATION,
)
from libs.workflow.referral_policy import DEFAULT_REFERRAL_POLICY

ALL_PROMPTS = {
    "situation": SBAR_SITUATION_SYSTEM_V1,
    "background": SBAR_BACKGROUND_SYSTEM_V1,
    "recommendation": SBAR_RECOMMENDATION_SYSTEM_V1,
}


def test_no_legacy_source_marker_rule():
    """The old ``[SOURCE: <type> <id> <date>]`` rule must be gone."""
    for name, txt in ALL_PROMPTS.items():
        assert (
            "<type> <id>" not in txt
        ), f"{name}: legacy SOURCE marker rule must be removed"
        assert (
            "[SOURCE: <Encounter|DocumentReference|Chunk>" not in txt
        ), f"{name}: legacy SOURCE format must be removed"


def _flatten(txt: str) -> str:
    """Collapse all whitespace runs to a single space so substring checks
    are not defeated by source-line wrapping in the prompt files."""
    return re.sub(r"\s+", " ", txt)


def test_inline_uuid_prohibition_present():
    """Each prompt must explicitly ban inline encounter / document ids."""
    for name, txt in ALL_PROMPTS.items():
        flat = _flatten(txt)
        assert (
            "UUID-like reference" in flat
        ), f"{name}: must forbid UUID-like references in narrative"
        assert (
            "encounter ids" in flat
        ), f"{name}: must explicitly call out encounter ids"

    # Situation + Background additionally forbid the literal SOURCE:
    # token inline. Recommendation uses [RULE: ...] markers and so does
    # not need to mention SOURCE: literally.
    for name in ("situation", "background"):
        flat = _flatten(ALL_PROMPTS[name])
        assert (
            "SOURCE:" in flat
        ), f"{name}: must reference the literal SOURCE: token to ban it"


def test_plain_english_rule_present():
    """Reading age 11 + NHS clinical terms allowed + active voice."""
    for name, txt in ALL_PROMPTS.items():
        flat = _flatten(txt)
        assert "reading age of 11" in flat, f"{name}: must set reading age of 11"
        assert (
            "NHS clinical terms" in flat
        ), f"{name}: must allow standard NHS clinical terms"
        assert "active voice" in flat, f"{name}: must require active voice"
        assert "British English" in flat, f"{name}: must require British English"


def test_legacy_reading_age_directive_replaced():
    """The vague ``target reading age 9-11`` line must be gone."""
    for name, txt in ALL_PROMPTS.items():
        assert "9-11" not in txt, (
            f"{name}: legacy '9-11' reading age must be replaced by the v2 "
            f"reading-age-11 directive"
        )


def test_prompt_injection_rule_intact():
    """CONTEXT free text must still be treated as data, not instructions."""
    for name, txt in ALL_PROMPTS.items():
        assert (
            "untrusted data" in txt
        ), f"{name}: prompt-injection rule must still be present"


def test_legacy_fallback_pins_sbar_prompts():
    """Legacy fallback pins section prompts to v2 and recall to v1."""
    assert _LEGACY_SBAR_PROMPT_VERSIONS == {
        _PROMPT_NAME_SITUATION: 2,
        _PROMPT_NAME_BACKGROUND: 2,
        _PROMPT_NAME_RECOMMENDATION: 2,
        _PROMPT_NAME_RECALL: 1,
    }


def test_default_referral_policy_pins_all_three_to_v2():
    prompts = DEFAULT_REFERRAL_POLICY["prompts"]
    assert prompts["situation"]["version"] == 2
    assert prompts["background"]["version"] == 2
    assert prompts["recommendation"]["version"] == 2


def test_seed_script_registers_both_v1_and_v2():
    """Seed script must register all three SBAR prompts at v1 + v2."""
    seed_path = pathlib.Path("scripts/seed_prompt_configs.py")
    src = seed_path.read_text(encoding="utf-8")

    # Match a line like:
    #   "sbar_situation",
    #   <whitespace>2,
    pattern = re.compile(
        r'"(sbar_situation|sbar_background|sbar_recommendation)",\s*(\d+),'
    )
    found: dict[tuple[str, int], int] = {}
    for name, version in pattern.findall(src):
        key = (name, int(version))
        found[key] = found.get(key, 0) + 1

    for name in ("sbar_situation", "sbar_background", "sbar_recommendation"):
        assert found.get((name, 1), 0) >= 1, f"{name} v1 not registered"
        assert found.get((name, 2), 0) >= 1, f"{name} v2 not registered"
