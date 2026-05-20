"""Unit tests for the shared extraction term normaliser.

Atlas trace:
  UN: UN-89E2AE36
  DI: DI-B5C78811
  VT: VT-29880CC8
"""

from __future__ import annotations

import pytest

from libs.pipeline.extraction_term_normaliser import (
    clean_observable_surface_text,
    is_bare_numeric,
    strip_value_unit_tail,
)


class TestStripValueUnitTail:
    def test_strips_lab_value_with_unit_and_range(self):
        assert strip_value_unit_tail("Haemoglobin 124 g/L (115-160)") == "Haemoglobin"

    def test_strips_value_with_compound_unit(self):
        result = strip_value_unit_tail("Neutrophil count 5.14 x10^9/L")
        assert result == "Neutrophil count"

    def test_strips_percent_value(self):
        assert strip_value_unit_tail("HbA1c: 48 %") == "HbA1c"

    def test_strips_less_than_value(self):
        assert strip_value_unit_tail("LDL <2.0 mmol/L") == "LDL"

    def test_strips_egfr_unit(self):
        assert (
            strip_value_unit_tail("eGFR 65 mL/min/1.73m2")
            == "eGFR"
        )

    def test_collapses_internal_whitespace_and_trims(self):
        assert strip_value_unit_tail("   FIT \t result  ") == "FIT result"

    def test_returns_input_when_no_tail_found(self):
        assert strip_value_unit_tail("Patient reported chest pain") == (
            "Patient reported chest pain"
        )

    def test_handles_empty_string(self):
        assert strip_value_unit_tail("") == ""

    def test_strips_trailing_punctuation(self):
        assert strip_value_unit_tail("CRP: 5 mg/L,") == "CRP"


class TestIsBareNumeric:
    @pytest.mark.parametrize(
        "value",
        [
            "5",
            "5.2",
            "<10",
            ">100",
            "10%",
            "120/80",
            "10^9/L",
        ],
    )
    def test_detects_bare_numbers(self, value):
        assert is_bare_numeric(value)

    @pytest.mark.parametrize(
        "value",
        [
            "Haemoglobin",
            "FIT 5",
            "",
        ],
    )
    def test_rejects_non_bare(self, value):
        assert not is_bare_numeric(value)

    def test_treats_value_plus_unit_as_bare(self):
        """A bare number plus a unit token is still noise -- it has no name."""
        assert is_bare_numeric("5 mg/L")
        assert is_bare_numeric("124 g/L")


class TestCleanObservableSurfaceText:
    def test_strips_tail_and_returns_name(self):
        assert (
            clean_observable_surface_text("Haemoglobin 124 g/L (115-160)")
            == "Haemoglobin"
        )

    def test_drops_bare_numeric_after_strip(self):
        # "5.2 g/L" -> after strip becomes "" (whole input was the tail)
        # so the fallback returns the input, which is bare-numeric => drop.
        assert clean_observable_surface_text("5.2 g/L") == ""

    def test_preserves_clean_name(self):
        assert clean_observable_surface_text("Platelet count") == "Platelet count"

    def test_handles_empty_string(self):
        assert clean_observable_surface_text("") == ""
