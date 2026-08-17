"""Pick a lab reference band for one patient.

Atlas trace:
  UN: UN-15EEDC06
  DI: DI-6EFB48AB
  DO: DO-669C4B13
  Risk: R-B8C4F461
  VT: VT-F4377BA4
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class LabReferenceRange:
    range_id: str
    low: float | None
    high: float | None
    critical_low: float | None
    critical_high: float | None
    source: str
    sex: str | None = None
    age_min: float | None = None
    age_max: float | None = None
    org_id: str = ""


def range_org_id(band: LabReferenceRange) -> str:
    return str(getattr(band, "org_id", "") or "").strip()


def select_reference_range(
    ranges: Iterable[LabReferenceRange],
    *,
    sex: str | None,
    age_years: float | None,
    org_id: str | None = None,
) -> LabReferenceRange | None:
    """Return the matching org overlay, else the platform default.

    A matching organisation band is used as a whole. Thresholds are
    never mixed with the platform default. Other organisations are
    ignored. If no matching band exists, return None (fail closed).
    """
    org = str(org_id or "").strip()
    visible = [band for band in ranges if _is_visible(band, org)]
    overlay = [band for band in visible if range_org_id(band) == org and org]
    defaults = [band for band in visible if not range_org_id(band)]
    return _pick_band(overlay, sex, age_years) or _pick_band(defaults, sex, age_years)


def _is_visible(band: LabReferenceRange, org: str) -> bool:
    owner = range_org_id(band)
    return not owner or owner == org


def _pick_band(
    ranges: list[LabReferenceRange],
    sex: str | None,
    age_years: float | None,
) -> LabReferenceRange | None:
    sex_norm = str(sex or "").strip().lower() or None
    candidates: list[tuple[int, LabReferenceRange]] = []
    for band in ranges:
        if not _band_matches(band, sex=sex_norm, age_years=age_years):
            continue
        candidates.append((_band_specificity(band), band))
    if not candidates:
        return None
    candidates.sort(key=lambda pair: pair[0], reverse=True)
    return candidates[0][1]


def _band_matches(
    band: LabReferenceRange,
    *,
    sex: str | None,
    age_years: float | None,
) -> bool:
    band_sex = _norm_optional(band.sex)
    if band_sex and band_sex != "all" and band_sex != sex:
        return False
    if band.age_min is not None and (age_years is None or age_years < band.age_min):
        return False
    if band.age_max is not None and (age_years is None or age_years > band.age_max):
        return False
    return True


def _band_specificity(band: LabReferenceRange) -> int:
    score = 0
    if _norm_optional(band.sex) not in {None, "all"}:
        score += 2
    if band.age_min is not None:
        score += 1
    if band.age_max is not None:
        score += 1
    return score


def _norm_optional(value: object) -> str | None:
    text = str(value or "").strip().lower()
    return text or None
