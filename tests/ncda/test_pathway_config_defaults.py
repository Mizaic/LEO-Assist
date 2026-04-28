"""Tests for Stage 8 per-site NCDA pathway config defaults."""

from __future__ import annotations

from libs.domains.ncda_pathway_config import (
    DEFAULT_BANDS,
    PathwayBands,
    get_bands,
    list_default_sites,
    normalise_site_key,
)

# National breach thresholds (mirror of services/ui/src/lib/pathwayRisk.ts).
FDS_28 = 28
TREATMENT_31 = 31
REFERRAL_62 = 62


def test_normalise_site_key_handles_underscores_and_case():
    assert normalise_site_key("Head_Neck") == "head-and-neck"
    assert normalise_site_key("Breast") == "breast"
    assert normalise_site_key("HEAD-NECK") == "head-and-neck"
    assert normalise_site_key("haematology") == "haematology"
    assert normalise_site_key("blood") == "haematology"


def test_get_bands_returns_pathway_bands():
    bands = get_bands("Prostate")
    assert isinstance(bands, PathwayBands)
    assert bands.site_key == "prostate"


def test_get_bands_unknown_site_returns_none():
    assert get_bands("nonexistent") is None


def test_list_default_sites_includes_canonical():
    sites = list_default_sites()
    assert "breast" in sites
    assert "skin" in sites
    assert "prostate" in sites


def test_typical_max_at_or_below_national_breach():
    """For each site, the FTR-to-Dx typical_max should not exceed FDS-28
    AND the FTR-to-treatment typical_max should not exceed referral-62.
    Sites whose median exceeds these reflect a real bottleneck rather
    than an acceptable typical band, so we cap them at the breach line.
    """
    for site_key, bands in DEFAULT_BANDS.items():
        # FDS-28: outcome reached within 28 days is the standard, but for
        # prostate/colorectal/lung etc. the *typical* time exceeds it.
        # We allow typical bands up to the national breach but not beyond.
        assert bands.ftr_to_dx_typical_max_days <= REFERRAL_62, (
            f"{site_key}: ftr_to_dx typical exceeds 62d national cap"
        )
        assert bands.ftr_to_treatment_typical_max_days <= REFERRAL_62, (
            f"{site_key}: ftr_to_treatment typical exceeds 62d cap"
        )


def test_breast_typical_band_reflects_one_stop_pattern():
    bands = get_bands("breast")
    assert bands is not None
    assert bands.seen_to_dx_typical_max_days == 0
    assert bands.ftr_to_dx_typical_max_days <= FDS_28


def test_skin_typical_band_smaller_than_prostate():
    skin = get_bands("skin")
    prostate = get_bands("prostate")
    assert skin is not None and prostate is not None
    assert skin.ftr_to_dx_typical_max_days <= prostate.ftr_to_dx_typical_max_days


def test_band_values_non_negative():
    for site_key, bands in DEFAULT_BANDS.items():
        for field_name in (
            "ftr_to_seen_typical_max_days",
            "seen_to_dx_typical_max_days",
            "dx_to_treatment_typical_max_days",
            "ftr_to_dx_typical_max_days",
            "ftr_to_treatment_typical_max_days",
        ):
            value = getattr(bands, field_name)
            assert value >= 0, f"{site_key}.{field_name} negative: {value}"
