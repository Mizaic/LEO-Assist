"""One-shot generator for libs/episode_detector/defaults/*.json (v0).

Atlas trace:
  DI: DI-951F26E0 (schema), DI-FA3CE229 (loader)

Run once per intentional refresh of the v0 snapshots:

    PYTHONPATH=. python scripts/episode_v2/generate_v0_defaults.py

The output files are byte-identical given the same input constants,
so the parity test in ``tests/episode_detector/`` will fail loudly if
a constant in the detector code is changed without regenerating the
snapshot (which is the point -- v0 is the frozen baseline; any diff
against it is a deliberate governance event).
"""

from __future__ import annotations

import json
from pathlib import Path

from services.analysis_worker.app.episode_detector_v2 import site_keys as sk
from services.analysis_worker.app.episode_detector_v2.signals import (
    pathway_channel as pc,
)

from libs.episode_detector.rulebook import SiteRulebook

V0_VERSION = "v0-2026.04.0"
SCHEMA = "1.0.0"
DEPENDENCIES = {"detector_binary": "v2", "snomed_edition": "uk-202511"}


# Defaults from generators/_window.py
LOOKBACK = 365
LOOKAHEAD = 730


BREAST_POSITIVE = [
    "carcinoma", "dcis", "invasive", "malignant", "positive for malignancy",
]
BREAST_NEGATIVE = [
    "benign", "negative", "no abnormality", "no malignancy", "normal",
]
BREAST_INVESTIGATION = [
    "breast biopsy", "breast mri", "breast ultrasound",
    "core biopsy of breast", "fine needle aspiration of breast", "mammogra",
]
BREAST_OBS_CODES = sorted({"169068008", "722164000", "439470001"})


REASON_REGEX_PER_SITE = {
    sk.SITE_BREAST: [r"\bbreast\b"],
    sk.SITE_UPPER_GI: [r"\b(oesophagus|gastric|stomach|upper gi|dysphagia)\b"],
    sk.SITE_LOWER_GI: [r"\b(colorectal|colon|rectal|lower gi|pr bleed)\b"],
    sk.SITE_LUNG: [r"\b(lung|chest|haemoptysis)\b"],
    sk.SITE_GYNAE: [r"\b(ovarian|cervical|endometrial|gynae)\b"],
    sk.SITE_HEAD_NECK: [r"\b(head and neck|throat|laryng)\b"],
    sk.SITE_PROSTATE_UROLOGICAL: [r"\b(prostate|urology|urological|psa)\b"],
    sk.SITE_SKIN: [r"\b(melanoma|skin lesion)\b"],
    sk.SITE_HAEMATOLOGY: [r"\b(leuk|lymph|myeloma)\b"],
    sk.SITE_BRAIN_CNS: [r"\b(brain|cns|glioma)\b"],
}


def _form_types_for_site(site: str) -> list[str]:
    return sorted(
        key for key, mapped in pc._FORM_TYPE_TO_SITE.items() if mapped == site
    )


def _referral_codes(site: str) -> list[str]:
    return sorted(
        code for code, mapped in sk.REFERRAL_SNOMED_TO_SITE.items()
        if mapped == site
    )


def _clinic_seen_codes(site: str) -> list[str]:
    return sorted(
        code for code, mapped in sk.CLINIC_SEEN_SNOMED_TO_SITE.items()
        if mapped == site
    )


def _suspected_codes_for_site(site: str) -> list[str]:
    out = [
        cid for cid, (mapped, intent)
        in sk.SUSPECTED_SITE_SNOMED.items()
        if mapped == site and intent == "suspected"
    ]
    if site == sk.SITE_BREAST:
        out.extend(sk.BREAST_SNOMED_SUSPECTED)
    return sorted(set(out))


def _confirmed_codes_for_site(site: str) -> list[str]:
    out = [
        cid for cid, (mapped, intent)
        in sk.SUSPECTED_SITE_SNOMED.items()
        if mapped == site and intent == "confirmed"
    ]
    if site == sk.SITE_BREAST:
        out.extend(sk.BREAST_SNOMED_CONFIRMED)
    return sorted(set(out))


def _benign_closure_for_site(site: str) -> list[str]:
    if site == sk.SITE_BREAST:
        return sorted(sk.BREAST_SNOMED_BENIGN_CLOSURE)
    return []


def _activation_for(site: str) -> dict:
    record = sk.ACTIVATION[site]
    return {
        "auto_publish": record.auto_publish,
        "suggest": record.suggest,
        "min_precision": 0.95,
    }


def _result_channel_for_site(site: str) -> dict:
    if site == sk.SITE_BREAST:
        return {
            "observation_snomed": BREAST_OBS_CODES,
            "investigation_terms": BREAST_INVESTIGATION,
            "positive_terms": BREAST_POSITIVE,
            "negative_terms": BREAST_NEGATIVE,
        }
    return {
        "observation_snomed": [],
        "investigation_terms": [],
        "positive_terms": [],
        "negative_terms": [],
    }


def build_rulebook(site: str) -> dict:
    """Build a v0 rulebook dict for the given site from live constants."""
    suspected = _suspected_codes_for_site(site)
    confirmed = _confirmed_codes_for_site(site)
    benign = _benign_closure_for_site(site)
    return {
        "site_key": site,
        "rulebook_version": V0_VERSION,
        "schema_version": SCHEMA,
        "dependencies": DEPENDENCIES,
        "activation": _activation_for(site),
        "windows": {"lookback_days": LOOKBACK, "lookahead_days": LOOKAHEAD},
        "tier_thresholds": {
            "auto_votes": 2,
            "suggest_votes": 2,
            "diversity_required_for_auto": 2,
        },
        "scorer_weights": {
            "code": 1.0, "text": 0.4, "pathway": 0.8,
            "result": 0.9, "treatment": 0.6, "bias": -0.2,
        },
        "anchors": {
            "referral_snomed": _referral_codes(site),
            "clinic_seen_snomed": _clinic_seen_codes(site),
            "suspected_snomed": suspected,
            "confirmed_snomed": confirmed,
        },
        "signals": {
            "code_channel": {
                "suspected_snomed": suspected,
                "confirmed_snomed": confirmed,
                "benign_closure_snomed": benign,
                "suspected_confidence": 0.70 if site != sk.SITE_BREAST else 0.80,
                "confirmed_confidence": 0.85 if site != sk.SITE_BREAST else 0.95,
                "benign_closure_confidence": 0.70,
            },
            "text_channel": {"regex_catalogue": []},
            "pathway_channel": {
                "form_types": _form_types_for_site(site),
                "reason_regex": REASON_REGEX_PER_SITE.get(site, []),
            },
            "result_channel": _result_channel_for_site(site),
            "treatment_channel": {"snomed": [], "regex_catalogue": []},
        },
        "closure": {
            "benign": {"requires_any_of": [], "and_no_confirmed_within_days": None},
            "completed": {
                "requires_any_of": [],
                "and_no_confirmed_within_days": None,
            },
            "use_core_closure_set": True,
        },
        "cross_site_guard": [],
    }


def main() -> None:
    out_dir = Path("libs/episode_detector/defaults")
    out_dir.mkdir(parents=True, exist_ok=True)
    for site in sk.ALL_SITES:
        rb_dict = build_rulebook(site)
        # Exercise the round-trip so generation fails loudly if the
        # dataclass rejects a field.
        SiteRulebook.from_json(json.dumps(rb_dict))
        path = out_dir / f"{site}.v0.json"
        with path.open("w", encoding="utf-8") as fh:
            json.dump(rb_dict, fh, indent=2, sort_keys=True)
            fh.write("\n")
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
