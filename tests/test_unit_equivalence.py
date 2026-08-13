"""Unit tests for lab unit equivalence.

Atlas trace: DI-D6AEFFBC
"""

from __future__ import annotations

import pytest

from libs.units.observable_units import (
    UnitConversionError,
    canonicalise_value_for_observation,
)
from libs.units.unit_equivalence import normalise_unit, units_are_equivalent


FIT_OBS = "1049361000000101"


def test_microgram_symbol_and_faeces_words_match_rule_unit() -> None:
    patient = "\u00b5g Hb/g faeces"
    assert units_are_equivalent(patient, "microgram/g") is True
    assert (
        canonicalise_value_for_observation(
            FIT_OBS, 126.0, patient, rule_canonical_unit="microgram/g"
        )
        == 126.0
    )


def test_ug_per_litre_is_not_ug_per_gram() -> None:
    assert units_are_equivalent("ug/L", "ug/g") is False
    with pytest.raises(UnitConversionError):
        canonicalise_value_for_observation(
            FIT_OBS, 15.0, "ug/L", rule_canonical_unit="ug/g"
        )


def test_normalise_unit_strips_haemoglobin_and_faeces() -> None:
    assert normalise_unit("ug Hb/g faeces") == "ug/g"
    assert normalise_unit("microgram/g") == "ug/g"
