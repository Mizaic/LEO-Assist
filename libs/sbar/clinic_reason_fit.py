"""Decide whether a stored referral reason matches the receiving clinic.

Atlas trace:
  DO: DO-FE774247
  DI: DI-ED65569C
"""

from __future__ import annotations

from libs.clinical_scoping.specialty_markers import SPECIALTY_MARKERS

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


_EMPTY_REASON_CUES = (
    "no presenting symptom",
    "does not state any presenting",
    "no specific symptom",
    "no clinical concern",
    "not documented",
    "no symptom details",
)


def reason_names_a_finding(reason: str) -> bool:
    """False when the stored reason only says nothing was documented."""
    text = str(reason or "").strip()
    if not text:
        return False
    low = text.lower()
    return not any(cue in low for cue in _EMPTY_REASON_CUES)


def term_fits_clinic(term: str, clinic_type: str = "") -> bool:
    """True when the term names the receiving clinic site, or any 2WW site."""
    text = str(term or "").strip()
    if not text:
        return False
    key = str(clinic_type or "").strip().upper()
    sites = _CLINIC_SITES.get(key)
    if not sites:
        sites = tuple(site for group in _CLINIC_SITES.values() for site in group)
    return _any_site_marker(text, sites)


def reason_matches_clinic(reason: str, clinic_type: str) -> bool:
    """True when the reason fits the clinic, or the clinic is unknown."""
    text = str(reason or "").strip()
    if not reason_names_a_finding(text):
        return False
    key = str(clinic_type or "").strip().upper()
    sites = _CLINIC_SITES.get(key)
    if not sites:
        return True
    return _any_site_marker(text, sites)


def _any_site_marker(text: str, sites: tuple[str, ...]) -> bool:
    return any(
        SPECIALTY_MARKERS[site].search(text)
        for site in sites
        if site in SPECIALTY_MARKERS
    )
