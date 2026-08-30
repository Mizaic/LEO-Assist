"""Decide whether a stored referral reason matches the receiving clinic.

Atlas:
  DO: DO-FE774247
  DI: DI-ED65569C
"""

from __future__ import annotations

_CLINIC_SITES: dict[str, tuple[str, ...]] = {
    "2WW_GYNAECOLOGY": (
        "gynaecological",
        "endometrial",
        "cervical",
        "ovarian",
        "vulval",
    ),
    "2WW_BREAST": ("breast",),
}


def reason_matches_clinic(reason: str, clinic_type: str) -> bool:
    """True when the reason fits the clinic, or the clinic is unknown."""
    text = str(reason or "").strip()
    key = str(clinic_type or "").strip().upper()
    sites = _CLINIC_SITES.get(key)
    if not text or not sites:
        return True
    from libs.clinical_scoping.specialty_markers import SPECIALTY_MARKERS

    return any(
        SPECIALTY_MARKERS[site].search(text)
        for site in sites
        if site in SPECIALTY_MARKERS
    )
