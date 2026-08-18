"""Resolve filing-cabinet folder labels for patient documents.

Atlas trace:
  DO: DO-AA3B7FCC
  DI: DI-9456E5BE
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-AA3B7FCC")
"""

from __future__ import annotations

_KNOWN_CLINIC_TYPES: dict[str, str] = {
    "2WW_BREAST": "Breast",
    "2WW_LUNG": "Lung",
    "2WW_UPPER_GI": "Upper GI",
    "2WW_LOWER_GI": "Lower GI",
    "2WW_COLORECTAL": "Colorectal",
    "2WW_UROLOGY": "Urology",
    "2WW_SKIN": "Skin",
    "2WW_HEAD_AND_NECK": "Head and neck",
    "2WW_GYNAECOLOGY": "Gynaecology",
    "2WW_HAEMATOLOGY": "Haematology",
    "2WW_PROSTATE": "Prostate",
}


def _label_from_clinic_type(clinic_type: str | None) -> str | None:
    raw = str(clinic_type or "").strip()
    if not raw:
        return None
    known = _KNOWN_CLINIC_TYPES.get(raw.upper())
    if known:
        return known
    if "_" in raw:
        tail = "_".join(raw.split("_")[1:])
        if tail:
            return tail.replace("_", " ").title()
    return raw.replace("_", " ").title()


def _label_from_episode(episode_label: str | None) -> str | None:
    raw = str(episode_label or "").strip()
    if not raw or raw.lower() == "general":
        return None
    return raw.replace("_", " ").title()


def resolve_document_folder_label(
    *,
    episode_label: str | None = None,
    clinic_type: str | None = None,
    referral_specialty: str | None = None,
    service_name: str | None = None,
) -> str:
    """Pick a human folder name for the Documents filing cabinet."""
    clinic_label = _label_from_clinic_type(clinic_type)
    if clinic_label:
        return clinic_label

    episode = _label_from_episode(episode_label)
    if episode:
        return episode

    service = str(service_name or "").strip()
    if service:
        return service

    specialty = str(referral_specialty or "").strip()
    if specialty and specialty.lower() != "general":
        return specialty

    return "General"
