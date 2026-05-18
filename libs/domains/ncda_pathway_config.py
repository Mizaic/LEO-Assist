"""Per-site NCDA pathway configuration.

Defines typical-time bands per cancer-site for the reviewer UI traffic-light
rendering and the auxiliary attachment policy. National breach thresholds
are fixed at the NCDA level (FDS-28, treatment-31, referral-62) and live
in services/ui/src/lib/pathwayRisk.ts. The bands here are *site-local*
typical maxima -- under typical-max = green, between typical-max and
national breach = amber, over national breach = red.

Defaults derived from tidied reviewed-cohort medians where >= 5 cases
exist; hand-set otherwise per the plan (breast = same-day one-stop;
skin = 14d FTR-to-Dx; prostate = 42d; colorectal = 28d).

Site keys are normalised (lower-case canonical) so head_neck / Head_Neck /
head-and-neck all resolve to the same entry.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict


@dataclass(frozen=True)
class PathwayBands:
    """Per-site typical-time bands (in days)."""

    site_key: str
    ftr_to_seen_typical_max_days: int
    seen_to_dx_typical_max_days: int
    dx_to_treatment_typical_max_days: int
    ftr_to_dx_typical_max_days: int
    ftr_to_treatment_typical_max_days: int

    def to_dict(self) -> dict:
        return asdict(self)


# Defaults derived from the reviewed cohort + clinical-pathway literature.
# Always set typical_max <= national_breach to keep the UI semantics correct.
DEFAULT_BANDS: dict[str, PathwayBands] = {
    "breast": PathwayBands(
        site_key="breast",
        ftr_to_seen_typical_max_days=7,
        seen_to_dx_typical_max_days=0,  # one-stop clinic
        dx_to_treatment_typical_max_days=21,
        ftr_to_dx_typical_max_days=14,
        ftr_to_treatment_typical_max_days=42,
    ),
    "skin": PathwayBands(
        site_key="skin",
        ftr_to_seen_typical_max_days=10,
        seen_to_dx_typical_max_days=7,
        dx_to_treatment_typical_max_days=21,
        ftr_to_dx_typical_max_days=14,
        ftr_to_treatment_typical_max_days=42,
    ),
    "prostate": PathwayBands(
        site_key="prostate",
        ftr_to_seen_typical_max_days=14,
        seen_to_dx_typical_max_days=28,
        dx_to_treatment_typical_max_days=28,
        ftr_to_dx_typical_max_days=42,
        ftr_to_treatment_typical_max_days=62,
    ),
    "colorectal": PathwayBands(
        site_key="colorectal",
        ftr_to_seen_typical_max_days=10,
        seen_to_dx_typical_max_days=14,
        dx_to_treatment_typical_max_days=28,
        ftr_to_dx_typical_max_days=28,
        ftr_to_treatment_typical_max_days=56,
    ),
    "lung": PathwayBands(
        site_key="lung",
        ftr_to_seen_typical_max_days=10,
        seen_to_dx_typical_max_days=14,
        dx_to_treatment_typical_max_days=28,
        ftr_to_dx_typical_max_days=28,
        ftr_to_treatment_typical_max_days=56,
    ),
    "head-and-neck": PathwayBands(
        site_key="head-and-neck",
        ftr_to_seen_typical_max_days=10,
        seen_to_dx_typical_max_days=14,
        dx_to_treatment_typical_max_days=28,
        ftr_to_dx_typical_max_days=21,
        ftr_to_treatment_typical_max_days=49,
    ),
    "haematology": PathwayBands(
        site_key="haematology",
        ftr_to_seen_typical_max_days=14,
        seen_to_dx_typical_max_days=14,
        dx_to_treatment_typical_max_days=14,
        ftr_to_dx_typical_max_days=28,
        ftr_to_treatment_typical_max_days=42,
    ),
}


def normalise_site_key(raw: str) -> str:
    """Canonicalise site keys to their lower-case, hyphen-joined form."""
    if not raw:
        return ""
    cleaned = raw.strip().lower().replace("_", "-").replace(" ", "-")
    if cleaned in {"head-neck", "headneck", "head"}:
        return "head-and-neck"
    if cleaned in {"haem", "blood"}:
        return "haematology"
    return cleaned


def get_bands(site_key: str) -> PathwayBands | None:
    """Return defaults for a site_key (normalised). None when unknown."""
    return DEFAULT_BANDS.get(normalise_site_key(site_key))


def list_default_sites() -> list[str]:
    return sorted(DEFAULT_BANDS.keys())
