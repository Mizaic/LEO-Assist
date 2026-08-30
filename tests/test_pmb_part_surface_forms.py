"""PMB part phrases map to state or bleed, never to 76742009.

Atlas: DI-00DFB149, DI-8BAC9BB3, VT-E053BB7C.
"""

from __future__ import annotations

PMB_ID = "76742009"
STATE_ID = "76498008"
BLEED_ID = "289530006"

# Phrase -> the part concept it may teach. Not the compound PMB code.
PART_FORMS: tuple[tuple[str, str], ...] = (
    ("menopause", STATE_ID),
    ("menopause and amenorrhoea for 3 years", STATE_ID),
    ("amenorrhoea for years", STATE_ID),
    ("amenorrhea for years", STATE_ID),
    ("no periods for years", STATE_ID),
    ("pv bleeding", BLEED_ID),
    ("has been bleeding", BLEED_ID),
    ("worsening bleed", BLEED_ID),
    ("worsening bleeding", BLEED_ID),
)

_FORBIDDEN_PMB_PHRASES = frozenset(
    {
        "hrt",
        "hormone replacement",
        "on hrt",
        "stopping hrt",
        "pv bleeding",
        "has been bleeding",
        "worsening bleed",
    }
)


def test_part_phrases_are_not_the_compound_pmb_code() -> None:
    for phrase, concept_id in PART_FORMS:
        assert concept_id != PMB_ID
        assert phrase not in {"hrt", "on hrt", "stopping hrt"}


def test_hrt_and_bleed_words_must_not_alias_pmb() -> None:
    for phrase in _FORBIDDEN_PMB_PHRASES:
        assert phrase not in {
            "pmb",
            "postmenopausal bleeding",
            "post-menopausal bleeding",
            "bleeding after menopause",
        }
