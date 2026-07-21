"""Catalog fields (title/summary/tags) for Validation Lab variants.

Atlas trace:
  DO: DO-A0ADDB38
  DI: DI-EB716E68
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-A0ADDB38")

Atlas: DI-EB716E68
"""

from __future__ import annotations

from typing import Any

_PLACEHOLDER_TITLE = ("variant", "brainstorm variant", "test patient")


def _pick(raw: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in raw and raw[key] is not None:
            return raw[key]
    return default


def clean_tag(raw: Any) -> str:
    tag = " ".join(str(raw or "").strip().split())
    if not tag or len(tag) > 40:
        return ""
    return tag


def is_placeholder_title(value: str) -> bool:
    cleaned = value.strip().lower()
    if not cleaned:
        return True
    if cleaned in _PLACEHOLDER_TITLE:
        return True
    if cleaned.startswith("variant ") and cleaned[8:].strip().isdigit():
        return True
    return cleaned.startswith("variant-") and cleaned[8:].replace("-", "").isdigit()


def derive_summary(row: dict[str, Any], rationale: str) -> str:
    summary = str(
        _pick(row, "summary", "description", "blurb", default="") or ""
    ).strip()
    if summary:
        return summary[:200]
    if rationale and rationale != "Proposed as a representative test-patient variant.":
        return rationale[:200]
    referral = str(_pick(row, "referralText", "referral_text", default="") or "")
    compact = " ".join(referral.split())
    return compact[:160] if compact else ""


def derive_tags(row: dict[str, Any]) -> list[str]:
    raw_tags = _pick(row, "tags", "labels", "chips", default=[]) or []
    tags: list[str] = []
    if isinstance(raw_tags, list):
        for item in raw_tags:
            tag = clean_tag(item)
            if tag and tag not in tags:
                tags.append(tag)
    equity = row.get("equity") if isinstance(row.get("equity"), dict) else {}
    for key, prefix in (
        ("plusGroup", "plus"),
        ("comorbidityBand", "comorbidity"),
        ("core20Decile", "Core20"),
    ):
        val = equity.get(key) if equity else None
        if val is None or val == "" or val == "none":
            continue
        label = f"Core20-{val}" if prefix == "Core20" else f"{prefix}:{val}"
        tag = clean_tag(label)
        if tag and tag not in tags:
            tags.append(tag)
    sex = str(_pick(row, "patientSex", "patient_sex", default="") or "").strip()
    if sex and sex not in tags:
        tags.append(sex)
    for obs in row.get("observations") or []:
        if not isinstance(obs, dict):
            continue
        term = clean_tag(obs.get("term") or obs.get("observableId"))
        if term and term not in tags:
            tags.append(term)
        if len(tags) >= 6:
            break
    return tags[:6]
