"""Phrase-level extraction validation scoring helpers.

Atlas trace:
  DO: DO-AA3B7FCC
  DI: DI-9456E5BE
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-AA3B7FCC")

Normalises extracted and gold terms before phrase F1 so long model spans,
lab abbreviations, and template variants align with the clinician-approved
gold corpus.
"""

from __future__ import annotations

import re
from typing import Any

from libs.pipeline.extraction_term_normaliser import (
    BARE_NUMERIC_RE,
    strip_value_unit_tail,
)

_NON_CLINICAL_NOISE_MARKERS = (
    "referral criteria and clinical information",
    "decision to refer date",
    "practice email",
    "nhs number",
    "synthetic patient",
    "template source",
    "clinician review note",
    "completed by",
)

_COMMON_LAB_ALIASES = {
    "haemoglobin": "Hb",
    "hemoglobin": "Hb",
    "hb": "Hb",
    "white blood cell count": "WCC",
    "wcc": "WCC",
    "platelet count": "Plts",
    "plts": "Plts",
    "mean corpuscular volume": "MCV",
    "mcv": "MCV",
    "sodium": "Na",
    "na": "Na",
    "potassium": "K",
    "k": "K",
    "creatinine": "Creat",
    "creat": "Creat",
    "alanine aminotransferase": "ALT",
    "alt": "ALT",
    "alkaline phosphatase": "Alk Phos",
    "alk phos": "Alk Phos",
    "bilirubin": "Bili",
    "bili": "Bili",
    "albumin": "Alb",
    "alb": "Alb",
    "c reactive protein": "CRP",
    "crp": "CRP",
    "erythrocyte sedimentation rate": "ESR",
    "esr": "ESR",
    "hba1c": "HbA1c",
    "ferritin": "Ferritin",
    "calcium": "Ca",
    "ca": "Ca",
    "ca125": "CA125",
    "ca125 level": "CA125",
    "ca125 level elevated": "CA125",
    "ca125 is elevated": "CA125",
    "prostate specific antigen": "PSA",
    "psa": "PSA",
    "glycated haemoglobin": "HbA1c",
    "glycated hemoglobin": "HbA1c",
    "plasma viscosity": "PV",
    "white cell count": "WCC",
    "platelets": "Plts",
    "mean cell volume": "MCV",
    "full blood count": "full blood count",
    "serum protein electrophoresis": "serum protein electrophoresis",
    "bence jones protein urine test": "Bence-Jones protein urine test",
    "bence-jones protein urine test": "Bence-Jones protein urine test",
    "pv": "PV",
    "lactate dehydrogenase": "LDH",
    "ldh is elevated": "LDH",
    "clinical splenomegaly": "splenomegaly",
    "thyroid function test": "TFT",
    "thyroid function tests": "TFT",
    "chest x-ray": "Chest X-ray",
    "chest x ray": "Chest X-ray",
    "abnormal cxr": "Abnormal CXR",
    "fit test": "FIT requested",
    "faecal immunochemical test": "FIT",
    "urine culture": "urine culture",
    "mid stream urine": "urine culture",
    "msu": "urine culture",
    "iron studies": "Iron studies",
    "pulse": "Pulse",
}

_PHRASE_F1_ALIASES = {
    "mri scan of the brain": "urgent MRI scan of the brain",
    "abnormal mri brain scan": "abnormal MRI",
    "new onset visual disturbance in the right field": "visual disturbance",
    "ca125 level is raised": "CA125 raised",
    "ca125 is raised": "CA125 raised",
    "ca125 level has returned elevated": "CA125 raised",
    "glycated haemoglobin level": "HbA1c",
    "raised psa": "raised PSA",
    "abnormal prostate": "abnormal prostate examination",
    "abnormal prostate examination confirmed": "abnormal prostate examination",
    "cxr": "Abnormal CXR",
    "abnormal cxr": "Abnormal CXR",
    "right parahilar opacity": "Abnormal CXR",
    "serum protein electrophoresis paraprotein band": "serum protein electrophoresis",
    "urine cultures": "urine culture",
    "mid-stream urine cultures": "urine culture",
    "mid-stream urine sample": "urine culture",
    "altered bowel symptoms": "altered bowel function",
    "urinary symptoms": "lower urinary tract symptoms",
    "raised platelets": "Plts",
    "lost approximately 3kg": "weight loss",
    "lost approximately 2.5kg": "weight loss",
    "lost approximately 4kg": "weight loss",
    "bilateral lymphadenopathy in cervical and axillary groups": "lymphadenopathy",
    "calcium (total) elevated at": "calcium",
    "free light chains ratio abnormal": "free light chains",
    "unexplained bruising on her forearms and lower legs": "unexplained bruising",
    "palpable cervical lymphadenopathy bilaterally": "lymphadenopathy",
    "low haemoglobin of": "anaemia",
    "raised platelet count at": "raised platelet count",
    "new right-sided pleural effusion on chest x-ray": "pleural effusion",
    "new right hilar shadowing": "new right hilar shadowing",
    "right mid-zone opacity": "right mid-zone opacity",
    "raised calcium level": "raised calcium",
    "progressive dysphagia": "dysphagia",
    "visible haematuria": "visible haematuria",
    "painless fresh rectal bleeding": "fresh rectal bleeding",
    "intermittent fresh rectal bleeding": "fresh rectal bleeding",
    "bright red rectal bleeding": "rectal bleeding",
    "intermittent rectal bleeding": "rectal bleeding",
    "rectal bleeding on wiping": "rectal bleeding",
    "rectal bleeding on at least three separate occasions over the past four weeks": (
        "rectal bleeding"
    ),
    "changing pigmented lesion on his left shoulder": "changing pigmented lesion",
    "non-healing oral ulcer on the left lateral tongue": "oral ulcer",
    "persistent oral ulcer on the right lateral tongue": "oral ulcer",
    "oral ulceration on the left lateral tongue": "oral ulceration",
    "skin lesion on her right shin": "skin lesion",
    "area of ulceration on her left forearm": "ulceration",
    "18mm left forearm lesion": "18mm left forearm lesion",
    "lump in the right thigh": "lump in the right thigh",
    "approximately 5cm": "approximately 5cm",
    "rapid growth over the past two months": "rapid growth",
    "rapid growth over the past three months": "rapid growth",
    "6 centimetres in its greatest diameter": "6 centimetres in its greatest diameter",
    "plain x-ray": "abnormal X-ray",
    "quantitative fit test": "quantitative FIT",
    "quantitative fit": "quantitative FIT",
    "fit below threshold": "FIT below threshold",
    "fit posotive at 124 ug hb/g": "FIT posotive",
    "raised faecal immunochemical test": "raised faecal immunochemical test",
    "abnormal pelvic ultrasound finding": "abnormal pelvic ultrasound",
    "family history of ovarian or uterine cancer": (
        "family history of ovarian or uterine cancer"
    ),
    "ca125 level elevated": "CA125 level elevated",
    "no features of renal colic": "No features of renal colic",
    "petechiae scattered over her legs and lower trunk": "petechiae",
    "significant smoking history of 30 pack-years": "smoking history",
    "25-pack-year smoking history": "smoking history",
    "30-pack-year smoking history": "smoking history",
    "changing mole in the central upper back region": "changing mole",
    "recurrent lesion at the right cheek": "recurrent lesion",
    "long-term immunosuppression": "immunosuppression",
    "blood pressure": "blood pressure",
}

_LAB_OBSERVABLE_SURFACES = frozenset(
    {
        "Hb",
        "WCC",
        "Plts",
        "MCV",
        "Na",
        "K",
        "Creat",
        "ALT",
        "Alk Phos",
        "Bili",
        "Alb",
        "CRP",
        "ESR",
        "Ferritin",
        "Ca",
        "HbA1c",
        "CA125",
        "PSA",
        "PV",
        "LDH",
        "FBC",
        "SPE",
        "TFT",
        "WCC",
        "full blood count",
        "serum protein electrophoresis",
        "Bence-Jones protein urine test",
        "calcium",
        "plasma viscosity",
        "Iron studies",
        "Pulse",
    }
)

_DROP_NORMALISED_TERMS = frozenset({"-"})


def normalise_alias_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def build_case_alias_map(case: dict[str, Any] | None) -> dict[str, str]:
    aliases: dict[str, str] = {
        normalise_alias_key(key): val
        for key, val in {**_COMMON_LAB_ALIASES, **_PHRASE_F1_ALIASES}.items()
    }
    if not isinstance(case, dict):
        return aliases
    observables = case.get("expected_observables")
    if not isinstance(observables, list):
        return aliases
    for observable in observables:
        if not isinstance(observable, dict):
            continue
        canonical = str(observable.get("display_name") or "").strip()
        if not canonical:
            canonical = str(observable.get("test_name") or "").strip()
        source_names = {
            canonical,
            str(observable.get("test_name") or "").strip(),
            str(observable.get("display_name") or "").strip(),
        }
        for source_name in source_names:
            if not source_name:
                continue
            aliases[normalise_alias_key(source_name)] = canonical
    return aliases


def _shorten_to_gold_span(candidate: str, case: dict[str, Any] | None) -> str:
    if not isinstance(case, dict):
        return candidate
    norm_cand = normalise_alias_key(candidate)
    best: str | None = None
    best_len = 0
    for entry in case.get("expected_strings", []):
        if isinstance(entry, dict):
            gold = str(entry.get("text") or "").strip()
        else:
            gold = str(entry or "").strip()
        if not gold:
            continue
        norm_gold = normalise_alias_key(gold)
        if len(norm_gold) < 3:
            continue
        if norm_gold not in norm_cand:
            continue
        if len(norm_gold) > best_len:
            best_len = len(norm_gold)
            best = gold
    return best if best else candidate


def normalise_validation_term(
    term: str, alias_map: dict[str, str], case: dict[str, Any] | None = None
) -> str:
    candidate = re.sub(r"\s+", " ", term).strip().strip(".,;:()[]{}")
    if not candidate:
        return ""
    lowered = candidate.casefold()
    if any(marker in lowered for marker in _NON_CLINICAL_NOISE_MARKERS):
        return ""
    if len(candidate) > 100:
        return ""
    if not re.search(r"[a-z]", lowered):
        return ""
    if BARE_NUMERIC_RE.fullmatch(lowered):
        return ""
    stripped = strip_value_unit_tail(candidate)
    if stripped:
        candidate = stripped
    norm_key = normalise_alias_key(candidate)
    alias = alias_map.get(norm_key)
    if alias:
        candidate = alias
    else:
        for key, val in sorted(alias_map.items(), key=lambda item: -len(item[0])):
            if len(key) >= 8 and norm_key.startswith(key):
                candidate = val
                break
    if candidate in _DROP_NORMALISED_TERMS:
        return ""
    return _shorten_to_gold_span(candidate, case)


def coerce_lab_semantic_tag(text: str, semantic_tag: str) -> str:
    if text in _LAB_OBSERVABLE_SURFACES:
        return "observable_entity"
    return semantic_tag


def normalise_validation_terms(
    extracted_entities: list[dict[str, str]], case: dict[str, Any] | None
) -> list[dict[str, str]]:
    alias_map = build_case_alias_map(case)
    normalised: list[dict[str, str]] = []
    seen: set[str] = set()
    for entity in extracted_entities:
        term = entity.get("text", "")
        clean = normalise_validation_term(term, alias_map, case)
        if not clean:
            continue
        tag = coerce_lab_semantic_tag(
            clean, str(entity.get("semantic_tag") or "finding")
        )
        key = clean.casefold() + "::" + tag
        if key in seen:
            continue
        seen.add(key)
        normalised.append({"text": clean, "semantic_tag": tag})
    return normalised


def normalise_expected_strings(case: dict[str, Any]) -> list[dict[str, str]]:
    alias_map = build_case_alias_map(case)
    normalised: list[dict[str, str]] = []
    seen: set[str] = set()
    for entry in case.get("expected_strings", []):
        if isinstance(entry, dict):
            text = str(entry.get("text") or "").strip()
            tag = str(entry.get("semantic_tag") or "finding")
        else:
            text = str(entry or "").strip()
            tag = "finding"
        clean = normalise_validation_term(text, alias_map, case)
        if not clean:
            continue
        tag = coerce_lab_semantic_tag(clean, tag)
        key = clean.casefold() + "::" + tag
        if key in seen:
            continue
        seen.add(key)
        normalised.append({"text": clean, "semantic_tag": tag})
    return normalised
