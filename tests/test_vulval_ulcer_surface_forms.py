"""Vulval ulceration phrases map to ulcer, not generic vulva finding.

Dry-run 000481827411 coded 'Vulval ulceration of uncertain cause' as
248858001 Vulva finding. Completeness and NG12 1.5.17 need 68640004.

Soreness and pain stay off the ulcer code. Do not invent ulcer from
'sore' or 'soreness' alone.

Atlas: DI-47D2CD86, DO-5A88E0B9, DI-8BAC9BB3.
"""

from __future__ import annotations

from libs.terminology.surface_normalize import normalize_surface

VULVAL_ULCER_ID = "68640004"
GENERIC_VULVA_FINDING_ID = "248858001"
VULVAL_PAIN_ID = "162145001"

# Phrase -> the ulcer code it may teach. Extra words do not change the code.
ULCER_PHRASES: tuple[str, ...] = (
    "Vulval ulceration",
    "vulval ulceration",
    "Vulval ulceration of uncertain cause",
    "Ulceration of vulva",
)

# These must never alias the ulcer code.
_NOT_ULCER_PHRASES: frozenset[str] = frozenset(
    {
        "Vulval soreness",
        "vulval pain",
        "white spot/sore on the vulva",
    }
)


def test_ulcer_phrases_normalise_to_the_same_core() -> None:
    cores = {
        normalize_surface(phrase).replace(" of uncertain cause", "")
        for phrase in ULCER_PHRASES
    }
    assert "vulval ulceration" in cores or "ulceration of vulva" in cores
    for phrase in ULCER_PHRASES:
        assert "ulcer" in normalize_surface(phrase)


def test_ulcer_phrases_are_not_the_generic_vulva_finding() -> None:
    for phrase in ULCER_PHRASES:
        assert phrase.lower() != "vulva finding"
        assert GENERIC_VULVA_FINDING_ID != VULVAL_ULCER_ID


def test_soreness_and_spot_are_not_ulcer_aliases() -> None:
    ulcer_norms = {normalize_surface(phrase) for phrase in ULCER_PHRASES}
    for phrase in _NOT_ULCER_PHRASES:
        assert normalize_surface(phrase) not in ulcer_norms
        assert "ulceration" not in normalize_surface(phrase)


def test_pain_code_is_not_the_ulcer_code() -> None:
    assert VULVAL_PAIN_ID != VULVAL_ULCER_ID
