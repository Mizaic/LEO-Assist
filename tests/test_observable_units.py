"""Phase 5f -- canonical-unit registry and conversion tests.

Atlas trace:
    UN: UN-26E57FA1
    DI: DI-7790EEA5
    DO: DO-710270EF
    VT: VT-404C1E2C

Covers:

  - get_canonical_unit / canonicalise_value happy and sad paths;
  - linear conversions (g/dL -> g/L, mg/dL -> umol/L for creatinine,
    DCCT% -> IFCC mmol/mol for HbA1c, lb -> kg for weight);
  - get_reference_range demographic banding (sex + age band wins
    over sex-only wins over unbanded);
  - registry sanity (every observable has its canonical unit listed
    among aliases or implicitly accepted);
  - fail-closed behaviour for unknown observables / non-finite values.
"""

from __future__ import annotations

import math

import pytest

from libs.units.observable_units import (
    OBSERVABLE_UNIT_REGISTRY,
    UnitConversionError,
    UnknownObservableError,
    canonicalise_value,
    canonicalise_value_for_observation,
    get_canonical_unit,
    get_reference_range,
    is_known_observable,
    list_known_observables,
    resolve_effective_canonical_unit,
)


# ---------------------------------------------------------------------------
# Registry sanity
# ---------------------------------------------------------------------------


def test_registry_lists_at_least_the_seeded_observables() -> None:
    seeded = {
        "365632008",  # platelets
        "271026005",  # haemoglobin
        "1003671000000109",  # HbA1c
        "1011481000000105",  # eGFR
        "113075003",  # creatinine
        "45896005",  # ALT
        "269078001",  # ferritin
        "313730000",  # PSA
        "271649006",  # systolic BP
        "271650006",  # diastolic BP
        "27113001",  # weight
        "60621009",  # BMI
    }
    known = set(list_known_observables())
    assert seeded.issubset(known), seeded - known


def test_canonical_unit_is_round_trip_safe() -> None:
    for obs_id in list_known_observables():
        canonical = get_canonical_unit(obs_id)
        assert canonicalise_value(obs_id, 42.0, canonical) == 42.0


def test_is_known_observable_matches_registry() -> None:
    for obs_id in list_known_observables():
        assert is_known_observable(obs_id)
    assert not is_known_observable("not-a-real-snomed-id")


# ---------------------------------------------------------------------------
# Linear conversions
# ---------------------------------------------------------------------------


def test_haemoglobin_g_per_dl_to_g_per_l() -> None:
    assert canonicalise_value("271026005", 14.0, "g/dL") == pytest.approx(140.0)


def test_creatinine_mg_per_dl_to_umol_per_l() -> None:
    # Standard conversion: 1 mg/dL = 88.4 umol/L.
    assert canonicalise_value("113075003", 1.0, "mg/dL") == pytest.approx(88.4)


def test_hba1c_dcct_percent_to_ifcc_mmol_mol() -> None:
    # 7.0% DCCT -> 53 mmol/mol IFCC (NGSP master equation, rounded).
    result = canonicalise_value("1003671000000109", 7.0, "%")
    assert result == pytest.approx(53.0, abs=0.5)


def test_weight_pounds_to_kg() -> None:
    assert canonicalise_value("27113001", 220.462, "lb") == pytest.approx(100.0, abs=1e-3)


def test_platelet_aliases_are_idempotent() -> None:
    # Different display strings for 10*9/L should all resolve identity.
    for alias in ("10*9/L", "10^9/L", "x10^9/L", "x10*9/L"):
        assert canonicalise_value("365632008", 482.0, alias) == 482.0


# ---------------------------------------------------------------------------
# Sad paths -- fail-closed at the registry boundary
# ---------------------------------------------------------------------------


def test_unknown_observable_raises() -> None:
    with pytest.raises(UnknownObservableError):
        get_canonical_unit("not-a-real-snomed-id")
    with pytest.raises(UnknownObservableError):
        canonicalise_value("not-a-real-snomed-id", 1.0, "kg")


def test_authored_unit_fallback_for_unregistered_observable() -> None:
    obs_id = "1049361000000101"
    assert resolve_effective_canonical_unit(obs_id, "ug/g") == "ug/g"
    assert (
        canonicalise_value_for_observation(
            obs_id, 15.0, "ug/g", rule_canonical_unit="ug/g"
        )
        == 15.0
    )
    with pytest.raises(UnitConversionError):
        canonicalise_value_for_observation(
            obs_id, 15.0, "ug/L", rule_canonical_unit="ug/g"
        )


def test_resolve_effective_canonical_unit_requires_unit_when_unknown() -> None:
    with pytest.raises(UnknownObservableError):
        resolve_effective_canonical_unit("9999999999", "")


def test_unknown_unit_raises_conversion_error() -> None:
    with pytest.raises(UnitConversionError):
        canonicalise_value("365632008", 482.0, "potatoes")


def test_non_finite_value_raises_conversion_error() -> None:
    with pytest.raises(UnitConversionError):
        canonicalise_value("365632008", float("nan"), "10*9/L")
    with pytest.raises(UnitConversionError):
        canonicalise_value("365632008", float("inf"), "10*9/L")


# ---------------------------------------------------------------------------
# Reference-range banding
# ---------------------------------------------------------------------------


def test_haemoglobin_picks_male_band() -> None:
    band = get_reference_range("271026005", sex="male", age_years=42.0)
    assert band is not None
    assert band.lower == 130.0 and band.upper == 170.0


def test_haemoglobin_picks_female_band() -> None:
    band = get_reference_range("271026005", sex="Female", age_years=35.0)
    assert band is not None
    assert band.lower == 120.0 and band.upper == 155.0


def test_psa_age_band_ge_70_wins_over_50_69() -> None:
    band = get_reference_range("313730000", sex="male", age_years=72.0)
    assert band is not None
    assert band.upper == 5.0


def test_psa_age_band_50_69_when_in_range() -> None:
    band = get_reference_range("313730000", sex="male", age_years=60.0)
    assert band is not None
    assert band.upper == 3.0


def test_reference_range_returns_none_when_no_demographic_match() -> None:
    # PSA bands are male-only; female patient -> no band -> None.
    band = get_reference_range("313730000", sex="female", age_years=60.0)
    assert band is None


def test_reference_range_returns_none_for_observable_without_ranges() -> None:
    # Body weight has no reference range registered.
    band = get_reference_range("27113001", sex="male", age_years=40.0)
    assert band is None


def test_reference_range_returns_none_for_unknown_observable() -> None:
    band = get_reference_range("not-real", sex="male", age_years=40.0)
    assert band is None


# ---------------------------------------------------------------------------
# Registry shape -- guard against silent regressions when adding new units
# ---------------------------------------------------------------------------


def test_every_alias_conversion_is_finite() -> None:
    for obs_id, spec in OBSERVABLE_UNIT_REGISTRY.items():
        for alias, conv in spec.aliases.items():
            assert math.isfinite(conv.factor), f"{obs_id} alias {alias} factor"
            assert math.isfinite(conv.offset), f"{obs_id} alias {alias} offset"
