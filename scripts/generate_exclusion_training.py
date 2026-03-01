#!/usr/bin/env python3
"""Generate exclusion-domain NER training dataset.

Produces JSONL conforming to the cancer pathway NER annotation schema.
Each record is one GP encounter (document level) with character-level entity
spans, assertion status, normalised SNOMED codes, and inter-entity relations.

Scenario coverage:
  FAST_TRACK_REFERRAL  — 10 examples
  FIRST_SEEN           —  8 examples
  CANCER_EXCLUDED      — 16 examples
  DIAGNOSIS_CONFIRMED  — 12 examples
  FIRST_TREATMENT      —  8 examples
  STILL_INVESTIGATING  — 10 examples
  PENDING_LETTER       —  6 examples
  FDS_CLOCK_START      —  3 examples
  Negation-heavy       —  5 examples
  ----------------------------------
  Total                ~ 78 examples

Output: exports/ner/training/exclusion_domain_v1.jsonl
"""
from __future__ import annotations

import json
import re
import sys
import uuid
from datetime import date
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ANNOTATOR_ID = "synthetic-v1"
ANNOTATION_DATE = str(date.today())
GUIDELINES_VERSION = "exclusion-domain-v1"


def _eid(prefix: str, n: int) -> str:
    return f"{prefix}_e{n}"


def _rid(prefix: str, n: int) -> str:
    return f"{prefix}_r{n}"


def find_span(text: str, surface: str, after: int = 0) -> tuple[int, int]:
    """Return (start, end) of *surface* in *text* starting at *after*.

    Raises ValueError if not found (helps catch annotation mistakes).
    """
    idx = text.find(surface, after)
    if idx == -1:
        raise ValueError(
            f"Surface form not found in text after offset {after}:\n"
            f"  surface: {surface!r}\n"
            f"  text:    {text!r}"
        )
    return idx, idx + len(surface)


def entity(
    eid: str,
    text: str,
    surface: str,
    label: str,
    assertion: str,
    after: int = 0,
    *,
    milestone_type: str | None = None,
    value: Any = None,
    unit: str | None = None,
    normalised_code: dict | None = None,
    confidence: float = 0.95,
) -> dict:
    start, end = find_span(text, surface, after)
    ent: dict = {
        "entity_id": eid,
        "start": start,
        "end": end,
        "text": surface,
        "label": label,
        "assertion": assertion,
        "confidence": confidence,
    }
    if milestone_type is not None:
        ent["milestone_type"] = milestone_type
    if value is not None:
        ent["value"] = value
        ent["unit"] = unit
    if normalised_code is not None:
        ent["normalised_code"] = normalised_code
    return ent


def relation(rid: str, rel_type: str, head: str, tail: str) -> dict:
    return {"relation_id": rid, "type": rel_type, "head": head, "tail": tail}


def meta(source_type: str) -> dict:
    return {
        "source_type": source_type,
        "annotator_id": ANNOTATOR_ID,
        "annotation_date": ANNOTATION_DATE,
        "annotation_guidelines_version": GUIDELINES_VERSION,
        "de_identification_method": "synthetic",
    }


def doc(
    did: str,
    text: str,
    entities: list[dict],
    source_type: str,
    relations: list[dict] | None = None,
) -> dict:
    return {
        "document_id": did,
        "text": text,
        "entities": entities,
        "relations": relations or [],
        "metadata": meta(source_type),
    }


def snomed(code: str, display: str) -> dict:
    return {"system": "SNOMED_CT", "code": code, "display": display}


# ---------------------------------------------------------------------------
# Training examples
# ---------------------------------------------------------------------------

EXAMPLES: list[dict] = []


# ============================================================
# FAST_TRACK_REFERRAL (10)
# ============================================================

# 1 — colorectal
_t = "Fast track referral for suspected colorectal cancer. Patient presents with 6-week history of rectal bleeding and change in bowel habit. Weight loss of 4 kg over 3 months. Referred urgently under 2-week-wait pathway."
EXAMPLES.append(doc(
    "ftr_col_01", _t,
    [
        entity("e0", _t, "Fast track referral", "X_PATHWAY_MILESTONE", "present",
               milestone_type="FAST_TRACK_REFERRAL",
               normalised_code=snomed("306206005", "Referral to fast-track cancer clinic (procedure)")),
        entity("e1", _t, "suspected colorectal cancer", "disorder", "possible",
               normalised_code=snomed("363346000", "Malignant neoplastic disease (disorder)")),
        entity("e2", _t, "rectal bleeding", "finding", "present",
               normalised_code=snomed("12063002", "Rectal haemorrhage (finding)")),
        entity("e3", _t, "change in bowel habit", "finding", "present",
               normalised_code=snomed("197121002", "Change in bowel habit (finding)")),
        entity("e4", _t, "Weight loss of 4 kg", "finding", "present",
               value=4, unit="kg",
               normalised_code=snomed("89362005", "Weight loss (finding)")),
        entity("e5", _t, "6-week history", "X_TEMPORAL", "present"),
        entity("e6", _t, "2-week-wait pathway", "X_PATHWAY_MILESTONE", "present",
               milestone_type="FAST_TRACK_REFERRAL"),
    ],
    "gp_record",
    [relation("r0", "triggers", "e2", "e0"), relation("r1", "triggers", "e3", "e0")],
))

# 2 — breast
_t = "2WW referral to breast clinic for suspected breast malignancy. Found discrete 2 cm lump in upper outer quadrant right breast. Firm, non-tender, no skin tethering. No axillary lymphadenopathy. Urgent fast track referral sent today."
EXAMPLES.append(doc(
    "ftr_brs_01", _t,
    [
        entity("e0", _t, "2WW referral", "X_PATHWAY_MILESTONE", "present",
               milestone_type="FAST_TRACK_REFERRAL",
               normalised_code=snomed("306206005", "Referral to fast-track cancer clinic (procedure)")),
        entity("e1", _t, "suspected breast malignancy", "disorder", "possible",
               normalised_code=snomed("363346000", "Malignant neoplastic disease (disorder)")),
        entity("e2", _t, "2 cm lump in upper outer quadrant right breast", "finding", "present",
               normalised_code=snomed("12240221000119106", "Mass of right breast (finding)")),
        entity("e3", _t, "axillary lymphadenopathy", "finding", "absent",
               normalised_code=snomed("30746006", "Lymphadenopathy (finding)")),
        entity("e4", _t, "No", "X_NEGATION_CUE", "present", after=_t.index("No axillary")),
        entity("e5", _t, "fast track referral", "X_PATHWAY_MILESTONE", "present",
               milestone_type="FAST_TRACK_REFERRAL"),
    ],
    "gp_record",
    [relation("r0", "negates", "e4", "e3")],
))

# 3 — lung
_t = "Urgent 2WW lung cancer referral. 62-year-old ex-smoker presenting with haemoptysis x 3 episodes over past 4 weeks. CXR today shows right upper lobe opacity. Referred for urgent CT chest and respiratory 2WW clinic."
EXAMPLES.append(doc(
    "ftr_lng_01", _t,
    [
        entity("e0", _t, "2WW lung cancer referral", "X_PATHWAY_MILESTONE", "present",
               milestone_type="FAST_TRACK_REFERRAL",
               normalised_code=snomed("306206005", "Referral to fast-track cancer clinic (procedure)")),
        entity("e1", _t, "haemoptysis", "finding", "present",
               normalised_code=snomed("66857006", "Haemoptysis (finding)")),
        entity("e2", _t, "right upper lobe opacity", "finding", "present",
               normalised_code=snomed("25505002", "Opacity of lung (finding)")),
        entity("e3", _t, "4 weeks", "X_TEMPORAL", "present"),
        entity("e4", _t, "2WW clinic", "X_PATHWAY_MILESTONE", "present",
               milestone_type="FAST_TRACK_REFERRAL"),
    ],
    "gp_record",
))

# 4 — prostate
_t = "Fast track referral to urology for raised PSA. PSA 12.4 ng/mL (age-adjusted upper limit 3.0). Digital rectal examination: firm irregular right lobe. Suspected prostate malignancy. 2-week-wait referral made."
EXAMPLES.append(doc(
    "ftr_pro_01", _t,
    [
        entity("e0", _t, "Fast track referral", "X_PATHWAY_MILESTONE", "present",
               milestone_type="FAST_TRACK_REFERRAL",
               normalised_code=snomed("306206005", "Referral to fast-track cancer clinic (procedure)")),
        entity("e1", _t, "PSA 12.4 ng/mL", "observable_entity", "present",
               value=12.4, unit="ng/mL",
               normalised_code=snomed("63476009", "Prostate specific antigen measurement (observable entity)")),
        entity("e2", _t, "firm irregular right lobe", "finding", "present",
               normalised_code=snomed("89103001", "Prostate hard on rectal examination (finding)")),
        entity("e3", _t, "Suspected prostate malignancy", "disorder", "possible",
               normalised_code=snomed("126906006", "Neoplasm of prostate (disorder)")),
        entity("e4", _t, "2-week-wait referral", "X_PATHWAY_MILESTONE", "present",
               milestone_type="FAST_TRACK_REFERRAL"),
    ],
    "gp_record",
    [relation("r0", "triggers", "e1", "e0"), relation("r1", "triggers", "e2", "e0")],
))

# 5 — skin/melanoma
_t = "2WW skin cancer referral. Changing pigmented lesion right calf, ABCDE criteria met: asymmetry, irregular border, variegated colour, diameter >6mm, evolving over 3 months. Suspicious for melanoma. Urgent dermatology 2WW referral submitted."
EXAMPLES.append(doc(
    "ftr_ski_01", _t,
    [
        entity("e0", _t, "2WW skin cancer referral", "X_PATHWAY_MILESTONE", "present",
               milestone_type="FAST_TRACK_REFERRAL",
               normalised_code=snomed("306206005", "Referral to fast-track cancer clinic (procedure)")),
        entity("e1", _t, "pigmented lesion right calf", "finding", "present",
               normalised_code=snomed("89698007", "Pigmented lesion (finding)")),
        entity("e2", _t, "Suspicious for melanoma", "disorder", "possible",
               normalised_code=snomed("372244006", "Malignant melanoma (disorder)")),
        entity("e3", _t, "3 months", "X_TEMPORAL", "present"),
        entity("e4", _t, "dermatology 2WW referral", "X_PATHWAY_MILESTONE", "present",
               milestone_type="FAST_TRACK_REFERRAL"),
    ],
    "gp_record",
))

# 6 — haematological
_t = "Fast track haematology referral. Persistent cervical lymphadenopathy >4 weeks, night sweats and 5% weight loss. FBC: WBC 14.2, lymphocytes 9.8. Suspected haematological malignancy. 2WW referral to haematology."
EXAMPLES.append(doc(
    "ftr_hae_01", _t,
    [
        entity("e0", _t, "Fast track haematology referral", "X_PATHWAY_MILESTONE", "present",
               milestone_type="FAST_TRACK_REFERRAL",
               normalised_code=snomed("306206005", "Referral to fast-track cancer clinic (procedure)")),
        entity("e1", _t, "cervical lymphadenopathy", "finding", "present",
               normalised_code=snomed("30746006", "Lymphadenopathy (finding)")),
        entity("e2", _t, "night sweats", "finding", "present",
               normalised_code=snomed("42984000", "Night sweats (finding)")),
        entity("e3", _t, "Suspected haematological malignancy", "disorder", "possible",
               normalised_code=snomed("363346000", "Malignant neoplastic disease (disorder)")),
        entity("e4", _t, ">4 weeks", "X_TEMPORAL", "present"),
        entity("e5", _t, "2WW referral to haematology", "X_PATHWAY_MILESTONE", "present",
               milestone_type="FAST_TRACK_REFERRAL"),
    ],
    "gp_record",
))

# 7 — upper GI
_t = "Upper GI 2WW referral. Dysphagia to solids progressive over 8 weeks, weight loss 6 kg. Upper endoscopy by GP cannot be done urgently - referred under 2-week-wait for suspected oesophageal cancer."
EXAMPLES.append(doc(
    "ftr_ugi_01", _t,
    [
        entity("e0", _t, "Upper GI 2WW referral", "X_PATHWAY_MILESTONE", "present",
               milestone_type="FAST_TRACK_REFERRAL",
               normalised_code=snomed("306206005", "Referral to fast-track cancer clinic (procedure)")),
        entity("e1", _t, "Dysphagia to solids", "finding", "present",
               normalised_code=snomed("40739000", "Dysphagia (finding)")),
        entity("e2", _t, "weight loss 6 kg", "finding", "present",
               value=6, unit="kg",
               normalised_code=snomed("89362005", "Weight loss (finding)")),
        entity("e3", _t, "suspected oesophageal cancer", "disorder", "possible",
               normalised_code=snomed("363349007", "Malignant tumour of oesophagus (disorder)")),
        entity("e4", _t, "8 weeks", "X_TEMPORAL", "present"),
        entity("e5", _t, "2-week-wait", "X_PATHWAY_MILESTONE", "present",
               milestone_type="FAST_TRACK_REFERRAL"),
    ],
    "gp_record",
))

# 8 — bladder
_t = "2WW urology referral for visible haematuria. Two episodes of frank haematuria without UTI over past month. MSU negative. Suspected bladder malignancy. Referred for urgent cystoscopy via 2-week-wait."
EXAMPLES.append(doc(
    "ftr_bla_01", _t,
    [
        entity("e0", _t, "2WW urology referral", "X_PATHWAY_MILESTONE", "present",
               milestone_type="FAST_TRACK_REFERRAL",
               normalised_code=snomed("306206005", "Referral to fast-track cancer clinic (procedure)")),
        entity("e1", _t, "frank haematuria", "finding", "present",
               normalised_code=snomed("34436003", "Blood in urine (finding)")),
        entity("e2", _t, "Suspected bladder malignancy", "disorder", "possible",
               normalised_code=snomed("363477002", "Malignant neoplasm of urinary bladder (disorder)")),
        entity("e3", _t, "cystoscopy", "procedure", "present",
               normalised_code=snomed("44491007", "Cystoscopy (procedure)")),
        entity("e4", _t, "2-week-wait", "X_PATHWAY_MILESTONE", "present",
               milestone_type="FAST_TRACK_REFERRAL"),
    ],
    "gp_record",
))

# 9 — gynaecological
_t = "Fast track gynaecology referral. Post-menopausal bleeding x 2 episodes. LMP 8 years ago. No HRT. Transvaginal ultrasound: endometrial thickness 12 mm. Suspected endometrial cancer. 2WW referral submitted."
EXAMPLES.append(doc(
    "ftr_gyn_01", _t,
    [
        entity("e0", _t, "Fast track gynaecology referral", "X_PATHWAY_MILESTONE", "present",
               milestone_type="FAST_TRACK_REFERRAL",
               normalised_code=snomed("306206005", "Referral to fast-track cancer clinic (procedure)")),
        entity("e1", _t, "Post-menopausal bleeding", "finding", "present",
               normalised_code=snomed("54968007", "Postmenopausal bleeding (finding)")),
        entity("e2", _t, "endometrial thickness 12 mm", "observable_entity", "present",
               value=12, unit="mm",
               normalised_code=snomed("102590004", "Endometrial thickness by ultrasound (observable entity)")),
        entity("e3", _t, "Suspected endometrial cancer", "disorder", "possible",
               normalised_code=snomed("371973000", "Malignant neoplasm of uterus (disorder)")),
        entity("e4", _t, "2WW referral", "X_PATHWAY_MILESTONE", "present",
               milestone_type="FAST_TRACK_REFERRAL"),
    ],
    "gp_record",
))

# 10 — head and neck
_t = "Urgent 2WW head and neck referral. Unexplained neck lump present 6 weeks, non-tender, firm, 3 cm. No upper respiratory tract infection. Possible squamous cell carcinoma of head and neck. Fast track referral to ENT."
EXAMPLES.append(doc(
    "ftr_ent_01", _t,
    [
        entity("e0", _t, "2WW head and neck referral", "X_PATHWAY_MILESTONE", "present",
               milestone_type="FAST_TRACK_REFERRAL",
               normalised_code=snomed("306206005", "Referral to fast-track cancer clinic (procedure)")),
        entity("e1", _t, "neck lump", "finding", "present",
               normalised_code=snomed("300852004", "Neck lump (finding)")),
        entity("e2", _t, "No", "X_NEGATION_CUE", "present",
               after=_t.index("No upper")),
        entity("e3", _t, "upper respiratory tract infection", "disorder", "absent",
               normalised_code=snomed("54150009", "Upper respiratory infection (disorder)")),
        entity("e4", _t, "Possible squamous cell carcinoma of head and neck", "disorder", "possible",
               normalised_code=snomed("254422003", "Squamous cell carcinoma of head and neck (disorder)")),
        entity("e5", _t, "Fast track referral to ENT", "X_PATHWAY_MILESTONE", "present",
               milestone_type="FAST_TRACK_REFERRAL"),
        entity("e6", _t, "6 weeks", "X_TEMPORAL", "present"),
    ],
    "gp_record",
    [relation("r0", "negates", "e2", "e3")],
))


# ============================================================
# FIRST_SEEN (8)
# ============================================================

# 11
_t = "Seen in fast track suspected colorectal cancer clinic. Colonoscopy performed today under sedation. Multiple biopsies taken from sigmoid lesion. Awaiting histology. Follow-up appointment booked in 2 weeks."
EXAMPLES.append(doc(
    "fsn_col_01", _t,
    [
        entity("e0", _t, "Seen in fast track suspected colorectal cancer clinic", "X_PATHWAY_MILESTONE", "present",
               milestone_type="FIRST_SEEN",
               normalised_code=snomed("185387006", "Self-referral to hospital (procedure)")),
        entity("e1", _t, "Colonoscopy", "procedure", "present",
               normalised_code=snomed("73761001", "Colonoscopy (procedure)")),
        entity("e2", _t, "biopsies taken from sigmoid lesion", "procedure", "present",
               normalised_code=snomed("86273004", "Biopsy (procedure)")),
        entity("e3", _t, "Awaiting histology", "finding", "present"),
        entity("e4", _t, "2 weeks", "X_TEMPORAL", "present"),
    ],
    "gp_record",
))

# 12
_t = "Attended 2WW breast clinic. Triple assessment performed: clinical examination, mammogram and ultrasound. Core biopsy taken from right breast lump. Results pending. Specialist nurse input given."
EXAMPLES.append(doc(
    "fsn_brs_01", _t,
    [
        entity("e0", _t, "Attended 2WW breast clinic", "X_PATHWAY_MILESTONE", "present",
               milestone_type="FIRST_SEEN",
               normalised_code=snomed("185387006", "Self-referral to hospital (procedure)")),
        entity("e1", _t, "Triple assessment", "procedure", "present",
               normalised_code=snomed("169069000", "Breast assessment (procedure)")),
        entity("e2", _t, "mammogram", "procedure", "present",
               normalised_code=snomed("71651007", "Mammography (procedure)")),
        entity("e3", _t, "Core biopsy taken from right breast lump", "procedure", "present",
               normalised_code=snomed("86273004", "Biopsy (procedure)")),
        entity("e4", _t, "Results pending", "finding", "present"),
    ],
    "gp_record",
))

# 13
_t = "Patient seen in urgent lung cancer clinic. CT chest performed — right upper lobe mass 3.2 cm with mediastinal lymphadenopathy. PET-CT arranged. Bronchoscopy with biopsy planned. MDT referral made."
EXAMPLES.append(doc(
    "fsn_lng_01", _t,
    [
        entity("e0", _t, "seen in urgent lung cancer clinic", "X_PATHWAY_MILESTONE", "present",
               milestone_type="FIRST_SEEN"),
        entity("e1", _t, "CT chest", "procedure", "present",
               normalised_code=snomed("77477000", "Computerized axial tomography of chest (procedure)")),
        entity("e2", _t, "right upper lobe mass 3.2 cm", "finding", "present",
               normalised_code=snomed("52731009", "Mass of lung (finding)")),
        entity("e3", _t, "mediastinal lymphadenopathy", "finding", "present",
               normalised_code=snomed("30746006", "Lymphadenopathy (finding)")),
        entity("e4", _t, "PET-CT", "procedure", "present",
               normalised_code=snomed("703430008", "Positron emission tomography (procedure)")),
        entity("e5", _t, "Bronchoscopy with biopsy", "procedure", "present",
               normalised_code=snomed("10847001", "Bronchoscopy (procedure)")),
    ],
    "gp_record",
))

# 14
_t = "Seen in haematology 2WW clinic. Lymph node biopsy arranged. CT neck, chest, abdomen and pelvis performed. Provisional diagnosis query lymphoma pending histology confirmation."
EXAMPLES.append(doc(
    "fsn_hae_01", _t,
    [
        entity("e0", _t, "Seen in haematology 2WW clinic", "X_PATHWAY_MILESTONE", "present",
               milestone_type="FIRST_SEEN"),
        entity("e1", _t, "Lymph node biopsy", "procedure", "present",
               normalised_code=snomed("274330002", "Lymph node biopsy (procedure)")),
        entity("e2", _t, "CT neck, chest, abdomen and pelvis", "procedure", "present",
               normalised_code=snomed("77477000", "Computerized axial tomography (procedure)")),
        entity("e3", _t, "query lymphoma", "disorder", "possible",
               normalised_code=snomed("118613001", "Lymphoma (disorder)")),
    ],
    "gp_record",
))

# 15
_t = "Patient attended fast track dermatology clinic. Dermoscopy of right calf pigmented lesion performed. Clinical opinion: suggestive of melanoma. Excision biopsy arranged for next week. Sentinel node biopsy to be discussed at MDT."
EXAMPLES.append(doc(
    "fsn_ski_01", _t,
    [
        entity("e0", _t, "fast track dermatology clinic", "X_PATHWAY_MILESTONE", "present",
               milestone_type="FIRST_SEEN"),
        entity("e1", _t, "Dermoscopy", "procedure", "present",
               normalised_code=snomed("400916002", "Dermoscopy (procedure)")),
        entity("e2", _t, "pigmented lesion", "finding", "present",
               normalised_code=snomed("89698007", "Pigmented lesion (finding)")),
        entity("e3", _t, "suggestive of melanoma", "disorder", "possible",
               normalised_code=snomed("372244006", "Malignant melanoma (disorder)")),
        entity("e4", _t, "Excision biopsy", "procedure", "present",
               normalised_code=snomed("65801008", "Excision (procedure)")),
        entity("e5", _t, "next week", "X_TEMPORAL", "present"),
    ],
    "gp_record",
))

# 16
_t = "Seen in urology 2WW clinic for haematuria. Flexible cystoscopy performed today. Small papillary lesion posterior wall bladder identified. Resection (TURBT) booked. CT urogram performed."
EXAMPLES.append(doc(
    "fsn_bla_01", _t,
    [
        entity("e0", _t, "Seen in urology 2WW clinic", "X_PATHWAY_MILESTONE", "present",
               milestone_type="FIRST_SEEN"),
        entity("e1", _t, "Flexible cystoscopy", "procedure", "present",
               normalised_code=snomed("44491007", "Cystoscopy (procedure)")),
        entity("e2", _t, "papillary lesion posterior wall bladder", "finding", "present",
               normalised_code=snomed("302837000", "Bladder lesion (finding)")),
        entity("e3", _t, "TURBT", "procedure", "present",
               normalised_code=snomed("14426007", "Transurethral resection of bladder tumor (procedure)")),
        entity("e4", _t, "CT urogram", "procedure", "present",
               normalised_code=snomed("713830008", "CT urogram (procedure)")),
    ],
    "gp_record",
))

# 17
_t = "Attended prostate rapid access clinic. Multiparametric MRI prostate performed: PIRADS 4 lesion in left peripheral zone. Transperineal biopsy under GA arranged in 3 weeks. PSA 14.7 ng/mL today."
EXAMPLES.append(doc(
    "fsn_pro_01", _t,
    [
        entity("e0", _t, "prostate rapid access clinic", "X_PATHWAY_MILESTONE", "present",
               milestone_type="FIRST_SEEN"),
        entity("e1", _t, "Multiparametric MRI prostate", "procedure", "present",
               normalised_code=snomed("726070007", "Multiparametric magnetic resonance imaging of prostate (procedure)")),
        entity("e2", _t, "PIRADS 4 lesion in left peripheral zone", "finding", "present",
               normalised_code=snomed("25510009", "Prostate lesion (finding)")),
        entity("e3", _t, "Transperineal biopsy", "procedure", "present",
               normalised_code=snomed("86273004", "Biopsy (procedure)")),
        entity("e4", _t, "PSA 14.7 ng/mL", "observable_entity", "present",
               value=14.7, unit="ng/mL",
               normalised_code=snomed("63476009", "Prostate specific antigen measurement (observable entity)")),
        entity("e5", _t, "3 weeks", "X_TEMPORAL", "present"),
    ],
    "gp_record",
))

# 18
_t = "Patient seen in gynaecology rapid access clinic. Hysteroscopy and endometrial biopsy performed. Uterus bulky on examination. CA-125 taken. Pelvic MRI arranged. Results awaited."
EXAMPLES.append(doc(
    "fsn_gyn_01", _t,
    [
        entity("e0", _t, "gynaecology rapid access clinic", "X_PATHWAY_MILESTONE", "present",
               milestone_type="FIRST_SEEN"),
        entity("e1", _t, "Hysteroscopy", "procedure", "present",
               normalised_code=snomed("423827005", "Hysteroscopy (procedure)")),
        entity("e2", _t, "endometrial biopsy", "procedure", "present",
               normalised_code=snomed("86273004", "Biopsy (procedure)")),
        entity("e3", _t, "CA-125", "observable_entity", "present",
               value=None, unit=None,
               normalised_code=snomed("60123008", "Cancer antigen 125 measurement (observable entity)")),
        entity("e4", _t, "Pelvic MRI", "procedure", "present",
               normalised_code=snomed("726252009", "MRI of pelvis (procedure)")),
    ],
    "gp_record",
))


# ============================================================
# CANCER_EXCLUDED (16)
# ============================================================

# 19
_t = "Letter from Colorectal Surgery. Colonoscopy findings: no evidence of malignancy. Diverticular disease noted. No polyps. Patient reassured and discharged from 2WW pathway. No further action required."
EXAMPLES.append(doc(
    "exc_col_01", _t,
    [
        entity("e0", _t, "no evidence of malignancy", "X_PATHWAY_MILESTONE", "absent",
               milestone_type="CANCER_EXCLUDED",
               normalised_code=snomed("395100000", "No evidence of cancer found (situation)")),
        entity("e1", _t, "no evidence of", "X_NEGATION_CUE", "present"),
        entity("e2", _t, "malignancy", "disorder", "absent",
               normalised_code=snomed("363346000", "Malignant neoplastic disease (disorder)")),
        entity("e3", _t, "Diverticular disease", "disorder", "present",
               normalised_code=snomed("419202007", "Diverticular disease (disorder)")),
        entity("e4", _t, "discharged from 2WW pathway", "X_PATHWAY_MILESTONE", "present",
               milestone_type="CANCER_EXCLUDED",
               normalised_code=snomed("395100000", "No evidence of cancer found (situation)")),
        entity("e5", _t, "No further action", "X_NEGATION_CUE", "present"),
    ],
    "clinic_letter",
    [relation("r0", "negates", "e1", "e2")],
))

# 20
_t = "Histology result: right breast core biopsy — benign fibroadenoma. No malignancy identified. Discharged from breast clinic. Reassured. No further follow-up required. Routine mammogram in 3 years as per screening programme."
EXAMPLES.append(doc(
    "exc_brs_01", _t,
    [
        entity("e0", _t, "benign fibroadenoma", "disorder", "present",
               normalised_code=snomed("79438006", "Fibroadenoma of breast (disorder)")),
        entity("e1", _t, "No", "X_NEGATION_CUE", "present", after=_t.index("No malignancy")),
        entity("e2", _t, "malignancy", "disorder", "absent",
               normalised_code=snomed("363346000", "Malignant neoplastic disease (disorder)")),
        entity("e3", _t, "No malignancy identified", "X_PATHWAY_MILESTONE", "absent",
               milestone_type="CANCER_EXCLUDED",
               normalised_code=snomed("395100000", "No evidence of cancer found (situation)")),
        entity("e4", _t, "Discharged from breast clinic", "X_PATHWAY_MILESTONE", "present",
               milestone_type="CANCER_EXCLUDED"),
        entity("e5", _t, "3 years", "X_TEMPORAL", "present"),
    ],
    "pathology_report",
    [relation("r0", "negates", "e1", "e2")],
))

# 21
_t = "Dermatology clinic letter. Excision biopsy of right calf lesion. Histology: intradermal naevus, completely excised. No evidence of melanoma. Margins clear. Cancer excluded. Discharged."
EXAMPLES.append(doc(
    "exc_ski_01", _t,
    [
        entity("e0", _t, "intradermal naevus", "disorder", "present",
               normalised_code=snomed("400016003", "Intradermal naevus (disorder)")),
        entity("e1", _t, "No evidence of melanoma", "X_PATHWAY_MILESTONE", "absent",
               milestone_type="CANCER_EXCLUDED",
               normalised_code=snomed("395100000", "No evidence of cancer found (situation)")),
        entity("e2", _t, "No evidence of", "X_NEGATION_CUE", "present",
               after=_t.index("No evidence of melanoma")),
        entity("e3", _t, "melanoma", "disorder", "absent",
               normalised_code=snomed("372244006", "Malignant melanoma (disorder)")),
        entity("e4", _t, "Cancer excluded", "X_PATHWAY_MILESTONE", "present",
               milestone_type="CANCER_EXCLUDED",
               normalised_code=snomed("395100000", "No evidence of cancer found (situation)")),
    ],
    "pathology_report",
    [relation("r0", "negates", "e2", "e3")],
))

# 22
_t = "Urology discharge summary. Flexible cystoscopy: no lesions identified. Haematuria attributed to urinary tract infection. No malignancy found. PSA 2.1 ng/mL normal range. Discharged from urology. Recurrent UTI management in primary care."
EXAMPLES.append(doc(
    "exc_uro_01", _t,
    [
        entity("e0", _t, "no lesions identified", "finding", "absent",
               normalised_code=snomed("260413007", "None (qualifier value)")),
        entity("e1", _t, "Haematuria attributed to urinary tract infection", "situation", "present",
               normalised_code=snomed("34436003", "Blood in urine (finding)")),
        entity("e2", _t, "No malignancy found", "X_PATHWAY_MILESTONE", "absent",
               milestone_type="CANCER_EXCLUDED",
               normalised_code=snomed("395100000", "No evidence of cancer found (situation)")),
        entity("e3", _t, "PSA 2.1 ng/mL", "observable_entity", "present",
               value=2.1, unit="ng/mL",
               normalised_code=snomed("63476009", "Prostate specific antigen measurement (observable entity)")),
        entity("e4", _t, "Discharged from urology", "X_PATHWAY_MILESTONE", "present",
               milestone_type="CANCER_EXCLUDED"),
    ],
    "discharge_summary",
))

# 23
_t = "Radiology report. CT chest abdomen pelvis. Requested: 2WW lung, right upper lobe mass. Findings: right upper lobe consolidation consistent with resolving pneumonia. No mass lesion identified. No lymphadenopathy. No evidence of malignancy on CT."
EXAMPLES.append(doc(
    "exc_lng_ct_01", _t,
    [
        entity("e0", _t, "consolidation consistent with resolving pneumonia", "disorder", "present",
               normalised_code=snomed("233604007", "Pneumonia (disorder)")),
        entity("e1", _t, "No mass lesion identified", "finding", "absent"),
        entity("e2", _t, "No", "X_NEGATION_CUE", "present", after=_t.index("No mass")),
        entity("e3", _t, "No lymphadenopathy", "finding", "absent",
               normalised_code=snomed("30746006", "Lymphadenopathy (finding)")),
        entity("e4", _t, "No evidence of malignancy on CT", "X_PATHWAY_MILESTONE", "absent",
               milestone_type="CANCER_EXCLUDED",
               normalised_code=snomed("395100000", "No evidence of cancer found (situation)")),
    ],
    "radiology_report",
))

# 24
_t = "Haematology outpatient letter. Lymph node biopsy histology: reactive lymphadenopathy. No evidence of lymphoma or other haematological malignancy. Epstein-Barr virus serology positive — consistent with infectious mononucleosis. Cancer excluded. Discharged from haematology."
EXAMPLES.append(doc(
    "exc_hae_01", _t,
    [
        entity("e0", _t, "reactive lymphadenopathy", "disorder", "present",
               normalised_code=snomed("19824006", "Reactive lymphadenopathy (disorder)")),
        entity("e1", _t, "No evidence of lymphoma", "X_PATHWAY_MILESTONE", "absent",
               milestone_type="CANCER_EXCLUDED",
               normalised_code=snomed("395100000", "No evidence of cancer found (situation)")),
        entity("e2", _t, "No evidence of", "X_NEGATION_CUE", "present"),
        entity("e3", _t, "lymphoma", "disorder", "absent",
               normalised_code=snomed("118613001", "Lymphoma (disorder)")),
        entity("e4", _t, "haematological malignancy", "disorder", "absent",
               normalised_code=snomed("363346000", "Malignant neoplastic disease (disorder)")),
        entity("e5", _t, "infectious mononucleosis", "disorder", "present",
               normalised_code=snomed("271558008", "Infectious mononucleosis (disorder)")),
        entity("e6", _t, "Cancer excluded", "X_PATHWAY_MILESTONE", "present",
               milestone_type="CANCER_EXCLUDED",
               normalised_code=snomed("395100000", "No evidence of cancer found (situation)")),
    ],
    "clinic_letter",
    [relation("r0", "negates", "e2", "e3"), relation("r1", "negates", "e2", "e4")],
))

# 25
_t = "Upper GI endoscopy report. Indication: dysphagia, 2WW upper GI. Findings: oesophagitis grade B. No mass lesion. No Barrett's oesophagus. Biopsies: moderate chronic gastritis, H. pylori positive. No dysplasia. No malignancy."
EXAMPLES.append(doc(
    "exc_ugi_01", _t,
    [
        entity("e0", _t, "oesophagitis grade B", "disorder", "present",
               normalised_code=snomed("235592006", "Oesophagitis (disorder)")),
        entity("e1", _t, "No mass lesion", "finding", "absent"),
        entity("e2", _t, "chronic gastritis", "disorder", "present",
               normalised_code=snomed("40845000", "Gastritis (disorder)")),
        entity("e3", _t, "H. pylori positive", "finding", "present",
               normalised_code=snomed("714476002", "Helicobacter pylori infection (disorder)")),
        entity("e4", _t, "No dysplasia", "finding", "absent",
               normalised_code=snomed("25723000", "Dysplasia (finding)")),
        entity("e5", _t, "No malignancy", "X_PATHWAY_MILESTONE", "absent",
               milestone_type="CANCER_EXCLUDED",
               normalised_code=snomed("395100000", "No evidence of cancer found (situation)")),
        entity("e6", _t, "No", "X_NEGATION_CUE", "present", after=_t.index("No malignancy")),
    ],
    "pathology_report",
))

# 26
_t = "Oncology clinic letter. Following 2WW referral for suspected ovarian cancer. CA-125 26 U/mL normal. Pelvic ultrasound: simple left ovarian cyst 3 cm, no complex features. ROCA score low risk. No evidence of cancer. Discharged to GP. Repeat ultrasound in 12 months."
EXAMPLES.append(doc(
    "exc_gyn_02", _t,
    [
        entity("e0", _t, "simple left ovarian cyst 3 cm", "disorder", "present",
               normalised_code=snomed("79883001", "Ovarian cyst (disorder)")),
        entity("e1", _t, "CA-125 26 U/mL", "observable_entity", "present",
               value=26, unit="U/mL",
               normalised_code=snomed("60123008", "Cancer antigen 125 measurement (observable entity)")),
        entity("e2", _t, "ROCA score low risk", "finding", "present"),
        entity("e3", _t, "No evidence of cancer", "X_PATHWAY_MILESTONE", "absent",
               milestone_type="CANCER_EXCLUDED",
               normalised_code=snomed("395100000", "No evidence of cancer found (situation)")),
        entity("e4", _t, "No evidence of", "X_NEGATION_CUE", "present",
               after=_t.index("No evidence of cancer")),
        entity("e5", _t, "Discharged to GP", "X_PATHWAY_MILESTONE", "present",
               milestone_type="CANCER_EXCLUDED"),
        entity("e6", _t, "12 months", "X_TEMPORAL", "present"),
    ],
    "clinic_letter",
    [relation("r0", "negates", "e4", "e3")],
))

# 27 — soft exclusion: "all clear"
_t = "Telephone call from colorectal team. Patient rang for results. Nurse specialist confirmed: colonoscopy showed diverticular disease only. All clear from colorectal team. No further action needed. Reassured."
EXAMPLES.append(doc(
    "exc_col_02", _t,
    [
        entity("e0", _t, "diverticular disease", "disorder", "present",
               normalised_code=snomed("419202007", "Diverticular disease (disorder)")),
        entity("e1", _t, "All clear from colorectal team", "X_PATHWAY_MILESTONE", "present",
               milestone_type="CANCER_EXCLUDED",
               normalised_code=snomed("395100000", "No evidence of cancer found (situation)")),
        entity("e2", _t, "No further action", "X_NEGATION_CUE", "present"),
    ],
    "gp_record",
))

# 28
_t = "ENT discharge letter. Excision of left tonsil performed. Histology: chronic tonsillitis, no dysplasia, no malignancy. Neck lump resolved post-tonsillectomy. Cancer excluded. Patient discharged."
EXAMPLES.append(doc(
    "exc_ent_01", _t,
    [
        entity("e0", _t, "chronic tonsillitis", "disorder", "present",
               normalised_code=snomed("40283007", "Chronic tonsillitis (disorder)")),
        entity("e1", _t, "no dysplasia", "finding", "absent",
               normalised_code=snomed("25723000", "Dysplasia (finding)")),
        entity("e2", _t, "no malignancy", "disorder", "absent",
               normalised_code=snomed("363346000", "Malignant neoplastic disease (disorder)")),
        entity("e3", _t, "Cancer excluded", "X_PATHWAY_MILESTONE", "present",
               milestone_type="CANCER_EXCLUDED",
               normalised_code=snomed("395100000", "No evidence of cancer found (situation)")),
    ],
    "clinic_letter",
))

# 29 — radiology report normal
_t = "CT colonography report. Clinical indication: 2WW colorectal. No colonic mass identified. Sigmoid diverticulosis. No lymphadenopathy. No distant metastases. Conclusion: no evidence of colorectal malignancy. Recommend dietary advice for diverticular disease."
EXAMPLES.append(doc(
    "exc_col_ct_01", _t,
    [
        entity("e0", _t, "No colonic mass identified", "finding", "absent"),
        entity("e1", _t, "Sigmoid diverticulosis", "disorder", "present",
               normalised_code=snomed("419202007", "Diverticular disease (disorder)")),
        entity("e2", _t, "No lymphadenopathy", "finding", "absent",
               normalised_code=snomed("30746006", "Lymphadenopathy (finding)")),
        entity("e3", _t, "No distant metastases", "finding", "absent",
               normalised_code=snomed("128462008", "Metastatic disease (finding)")),
        entity("e4", _t, "no evidence of colorectal malignancy", "X_PATHWAY_MILESTONE", "absent",
               milestone_type="CANCER_EXCLUDED",
               normalised_code=snomed("395100000", "No evidence of cancer found (situation)")),
    ],
    "radiology_report",
))

# 30 — PSA normalised, discharged
_t = "Urology letter. Prostate biopsy histology: benign prostatic hyperplasia, no evidence of malignancy. Gleason score not applicable — benign tissue only. PSA repeat 3.1 ng/mL — within normal range. No evidence of cancer found. Discharged from fast track pathway."
EXAMPLES.append(doc(
    "exc_pro_01", _t,
    [
        entity("e0", _t, "benign prostatic hyperplasia", "disorder", "present",
               normalised_code=snomed("266569009", "Benign prostatic hyperplasia (disorder)")),
        entity("e1", _t, "no evidence of malignancy", "X_PATHWAY_MILESTONE", "absent",
               milestone_type="CANCER_EXCLUDED",
               normalised_code=snomed("395100000", "No evidence of cancer found (situation)")),
        entity("e2", _t, "PSA repeat 3.1 ng/mL", "observable_entity", "present",
               value=3.1, unit="ng/mL",
               normalised_code=snomed("63476009", "Prostate specific antigen measurement (observable entity)")),
        entity("e3", _t, "No evidence of cancer found", "X_PATHWAY_MILESTONE", "absent",
               milestone_type="CANCER_EXCLUDED",
               normalised_code=snomed("395100000", "No evidence of cancer found (situation)")),
        entity("e4", _t, "Discharged from fast track pathway", "X_PATHWAY_MILESTONE", "present",
               milestone_type="CANCER_EXCLUDED"),
    ],
    "clinic_letter",
))

# 31
_t = "Gynaecology clinic letter re: postmenopausal bleeding. Hysteroscopy: normal endometrial cavity. Endometrial biopsy: inactive endometrium, no atypia, no malignancy. Reassured — cancer excluded. No action required."
EXAMPLES.append(doc(
    "exc_gyn_03", _t,
    [
        entity("e0", _t, "normal endometrial cavity", "finding", "present"),
        entity("e1", _t, "inactive endometrium", "finding", "present"),
        entity("e2", _t, "no atypia", "finding", "absent"),
        entity("e3", _t, "no malignancy", "disorder", "absent",
               normalised_code=snomed("363346000", "Malignant neoplastic disease (disorder)")),
        entity("e4", _t, "cancer excluded", "X_PATHWAY_MILESTONE", "present",
               milestone_type="CANCER_EXCLUDED",
               normalised_code=snomed("395100000", "No evidence of cancer found (situation)")),
    ],
    "pathology_report",
))

# 32 — recurrence excluded
_t = "Oncology follow-up. Surveillance CT chest abdomen pelvis: no evidence of recurrence of colon cancer. CEA 2.3 ug/L — normal. No new lesions. Next surveillance CT in 12 months. Patient reviewed at MDT — no evidence of recurrence."
EXAMPLES.append(doc(
    "exc_rec_01", _t,
    [
        entity("e0", _t, "no evidence of recurrence of colon cancer", "X_PATHWAY_MILESTONE", "absent",
               milestone_type="CANCER_EXCLUDED",
               normalised_code=snomed("405611007", "No evidence of recurrence of cancer (situation)")),
        entity("e1", _t, "no evidence of recurrence", "X_NEGATION_CUE", "present"),
        entity("e2", _t, "CEA 2.3 ug/L", "observable_entity", "present",
               value=2.3, unit="ug/L",
               normalised_code=snomed("250530007", "Carcinoembryonic antigen measurement (observable entity)")),
        entity("e3", _t, "no evidence of recurrence", "X_PATHWAY_MILESTONE", "absent",
               milestone_type="CANCER_EXCLUDED",
               normalised_code=snomed("405611007", "No evidence of recurrence of cancer (situation)"),
               after=_t.rfind("no evidence of recurrence")),
        entity("e4", _t, "12 months", "X_TEMPORAL", "present"),
    ],
    "clinic_letter",
))

# 33 — non-melanoma skin
_t = "Dermatology letter. Shave biopsy right forearm. Histology: seborrhoeic keratosis. No evidence of basal cell carcinoma or squamous cell carcinoma. Benign lesion fully excised. Cancer not found. Discharged."
EXAMPLES.append(doc(
    "exc_ski_02", _t,
    [
        entity("e0", _t, "seborrhoeic keratosis", "disorder", "present",
               normalised_code=snomed("83595000", "Seborrhoeic keratosis (disorder)")),
        entity("e1", _t, "No evidence of basal cell carcinoma", "finding", "absent",
               normalised_code=snomed("275032003", "Basal cell carcinoma (disorder)")),
        entity("e2", _t, "squamous cell carcinoma", "disorder", "absent",
               normalised_code=snomed("402447006", "Squamous cell carcinoma of skin (disorder)")),
        entity("e3", _t, "Cancer not found", "X_PATHWAY_MILESTONE", "absent",
               milestone_type="CANCER_EXCLUDED",
               normalised_code=snomed("395100000", "No evidence of cancer found (situation)")),
    ],
    "pathology_report",
))

# 34 — chest X-ray normal
_t = "CXR result. Indication: haemoptysis, 2WW lung pathway. Report: Heart size normal. No mass lesion in lung fields. No consolidation. No pleural effusion. No hilar enlargement. Normal chest radiograph — no malignancy."
EXAMPLES.append(doc(
    "exc_cxr_01", _t,
    [
        entity("e0", _t, "No mass lesion in lung fields", "finding", "absent"),
        entity("e1", _t, "No consolidation", "finding", "absent",
               normalised_code=snomed("233604007", "Pneumonia (disorder)")),
        entity("e2", _t, "No pleural effusion", "finding", "absent",
               normalised_code=snomed("52612000", "Pleural effusion (finding)")),
        entity("e3", _t, "Normal chest radiograph", "finding", "present",
               normalised_code=snomed("1290959000", "Plain X-ray of chest normal (finding)")),
        entity("e4", _t, "no malignancy", "X_PATHWAY_MILESTONE", "absent",
               milestone_type="CANCER_EXCLUDED",
               normalised_code=snomed("395100000", "No evidence of cancer found (situation)")),
    ],
    "radiology_report",
))


# ============================================================
# DIAGNOSIS_CONFIRMED (12)
# ============================================================

# 35
_t = "Colorectal MDT outcome letter. Histology: moderately differentiated adenocarcinoma of sigmoid colon. Staging CT: T3 N1 M0. Case discussed at MDT 14/09/2023. Plan: laparoscopic anterior resection with defunctioning ileostomy. Oncology referral made. Cancer diagnosis confirmed."
EXAMPLES.append(doc(
    "dia_col_01", _t,
    [
        entity("e0", _t, "adenocarcinoma of sigmoid colon", "disorder", "present",
               normalised_code=snomed("363349007", "Malignant tumour of sigmoid colon (disorder)")),
        entity("e1", _t, "Cancer diagnosis confirmed", "X_PATHWAY_MILESTONE", "present",
               milestone_type="DIAGNOSIS_CONFIRMED",
               normalised_code=snomed("363346000", "Malignant neoplastic disease (disorder)")),
        entity("e2", _t, "T3 N1 M0", "qualifier_value", "present"),
        entity("e3", _t, "laparoscopic anterior resection", "procedure", "present",
               normalised_code=snomed("235230009", "Anterior resection of rectum (procedure)")),
        entity("e4", _t, "14/09/2023", "X_TEMPORAL", "present"),
    ],
    "mdt_outcome",
    [relation("r0", "diagnoses", "e0", "e1")],
))

# 36
_t = "Breast clinic letter. Core biopsy histology: Grade 2 invasive ductal carcinoma, ER positive PR positive HER2 negative. Tumour 22 mm right breast. Axillary node sampling arranged. MDT recommendation: wide local excision and axillary node clearance, followed by adjuvant chemotherapy and radiotherapy."
EXAMPLES.append(doc(
    "dia_brs_01", _t,
    [
        entity("e0", _t, "invasive ductal carcinoma", "disorder", "present",
               normalised_code=snomed("408643008", "Infiltrating duct carcinoma of breast (disorder)")),
        entity("e1", _t, "Tumour 22 mm right breast", "finding", "present",
               value=22, unit="mm"),
        entity("e2", _t, "Grade 2", "qualifier_value", "present"),
        entity("e3", _t, "wide local excision", "procedure", "present",
               normalised_code=snomed("392021009", "Lumpectomy of breast (procedure)")),
        entity("e4", _t, "adjuvant chemotherapy", "procedure", "present",
               normalised_code=snomed("367336001", "Chemotherapy (procedure)")),
        entity("e5", _t, "radiotherapy", "procedure", "present",
               normalised_code=snomed("1287742003", "Radiotherapy (procedure)")),
    ],
    "mdt_outcome",
))

# 37
_t = "Respiratory clinic letter. Bronchoscopy biopsy histology: non-small cell lung cancer, adenocarcinoma subtype. PD-L1 expression 60%. EGFR and ALK negative. Stage IIIA (T3N2M0). Referred to oncology for radical chemoradiotherapy."
EXAMPLES.append(doc(
    "dia_lng_01", _t,
    [
        entity("e0", _t, "non-small cell lung cancer", "disorder", "present",
               normalised_code=snomed("254637007", "Non-small cell carcinoma of lung (disorder)")),
        entity("e1", _t, "adenocarcinoma subtype", "disorder", "present",
               normalised_code=snomed("413448000", "Adenocarcinoma of lung (disorder)")),
        entity("e2", _t, "Stage IIIA", "qualifier_value", "present"),
        entity("e3", _t, "T3N2M0", "qualifier_value", "present"),
        entity("e4", _t, "radical chemoradiotherapy", "procedure", "present",
               normalised_code=snomed("703423002", "Radical chemoradiotherapy (procedure)")),
    ],
    "clinic_letter",
))

# 38
_t = "Haematology letter. Excision lymph node biopsy confirmed: diffuse large B-cell lymphoma (DLBCL), germinal centre B-cell subtype. Ann Arbor stage III. PET-CT confirms extensive disease. Starting R-CHOP chemotherapy next week."
EXAMPLES.append(doc(
    "dia_hae_01", _t,
    [
        entity("e0", _t, "diffuse large B-cell lymphoma", "disorder", "present",
               normalised_code=snomed("413448000", "Diffuse large B-cell lymphoma (disorder)")),
        entity("e1", _t, "Ann Arbor stage III", "qualifier_value", "present"),
        entity("e2", _t, "PET-CT", "procedure", "present",
               normalised_code=snomed("703430008", "Positron emission tomography (procedure)")),
        entity("e3", _t, "R-CHOP chemotherapy", "procedure", "present",
               normalised_code=snomed("367336001", "Chemotherapy (procedure)")),
        entity("e4", _t, "next week", "X_TEMPORAL", "present"),
    ],
    "clinic_letter",
))

# 39
_t = "Urology letter. Prostate biopsy result: Gleason 4+3=7, Grade Group 3. Adenocarcinoma of prostate, maximum core involvement 80%. Clinical stage T2c. Prostate cancer diagnosis confirmed. MDT recommendation: radical prostatectomy or radiotherapy."
EXAMPLES.append(doc(
    "dia_pro_01", _t,
    [
        entity("e0", _t, "Adenocarcinoma of prostate", "disorder", "present",
               normalised_code=snomed("399068003", "Malignant tumour of prostate (disorder)")),
        entity("e1", _t, "Gleason 4+3=7", "qualifier_value", "present"),
        entity("e2", _t, "Grade Group 3", "qualifier_value", "present"),
        entity("e3", _t, "T2c", "qualifier_value", "present"),
        entity("e4", _t, "Prostate cancer diagnosis confirmed", "X_PATHWAY_MILESTONE", "present",
               milestone_type="DIAGNOSIS_CONFIRMED",
               normalised_code=snomed("399068003", "Malignant tumour of prostate (disorder)")),
        entity("e5", _t, "radical prostatectomy", "procedure", "present",
               normalised_code=snomed("265481001", "Radical prostatectomy (procedure)")),
    ],
    "clinic_letter",
))

# 40
_t = "Dermatology letter. Excision biopsy right calf. Histology: malignant melanoma, Breslow thickness 2.1 mm, Clark level IV, ulceration present. Diagnosed with melanoma. Wide local excision and sentinel lymph node biopsy arranged. Referred to skin MDT."
EXAMPLES.append(doc(
    "dia_ski_01", _t,
    [
        entity("e0", _t, "malignant melanoma", "disorder", "present",
               normalised_code=snomed("372244006", "Malignant melanoma (disorder)")),
        entity("e1", _t, "Breslow thickness 2.1 mm", "observable_entity", "present",
               value=2.1, unit="mm"),
        entity("e2", _t, "Clark level IV", "qualifier_value", "present"),
        entity("e3", _t, "Diagnosed with melanoma", "X_PATHWAY_MILESTONE", "present",
               milestone_type="DIAGNOSIS_CONFIRMED",
               normalised_code=snomed("372244006", "Malignant melanoma (disorder)")),
        entity("e4", _t, "Wide local excision", "procedure", "present",
               normalised_code=snomed("65801008", "Excision (procedure)")),
        entity("e5", _t, "sentinel lymph node biopsy", "procedure", "present",
               normalised_code=snomed("396487001", "Sentinel node biopsy (procedure)")),
    ],
    "pathology_report",
))

# 41 — bladder TCC
_t = "Urology MDT outcome. TURBT pathology: transitional cell carcinoma grade 3 (high grade urothelial carcinoma), T1, lamina propria invasion. Muscle invasive disease excluded on restaging TURBT. Intravesical BCG immunotherapy commenced. Cystectomy deferred."
EXAMPLES.append(doc(
    "dia_bla_01", _t,
    [
        entity("e0", _t, "transitional cell carcinoma grade 3", "disorder", "present",
               normalised_code=snomed("363477002", "Malignant neoplasm of urinary bladder (disorder)")),
        entity("e1", _t, "T1", "qualifier_value", "present"),
        entity("e2", _t, "Intravesical BCG immunotherapy", "procedure", "present",
               normalised_code=snomed("394888000", "BCG immunotherapy (procedure)")),
    ],
    "mdt_outcome",
))

# 42 — oesophageal
_t = "Upper GI clinic letter. OGD and biopsy: oesophageal adenocarcinoma at gastro-oesophageal junction, 3 cm lesion. CT staging: T3N2M0. Referred to specialist upper GI oncology centre for consideration of neoadjuvant chemotherapy and oesophagectomy."
EXAMPLES.append(doc(
    "dia_ugi_01", _t,
    [
        entity("e0", _t, "oesophageal adenocarcinoma", "disorder", "present",
               normalised_code=snomed("363349007", "Malignant tumour of oesophagus (disorder)")),
        entity("e1", _t, "T3N2M0", "qualifier_value", "present"),
        entity("e2", _t, "neoadjuvant chemotherapy", "procedure", "present",
               normalised_code=snomed("367336001", "Chemotherapy (procedure)")),
        entity("e3", _t, "oesophagectomy", "procedure", "present",
               normalised_code=snomed("31511000", "Oesophagectomy (procedure)")),
    ],
    "clinic_letter",
))

# 43 — endometrial
_t = "Gynaecology MDT. Hysteroscopy biopsy: grade 1 endometrioid adenocarcinoma. MRI pelvis: disease confined to uterine corpus, stage 1A. Total abdominal hysterectomy and bilateral salpingo-oophorectomy performed. Final pathology: pT1a N0 M0 — cancer confirmed."
EXAMPLES.append(doc(
    "dia_gyn_01", _t,
    [
        entity("e0", _t, "endometrioid adenocarcinoma", "disorder", "present",
               normalised_code=snomed("371973000", "Malignant neoplasm of uterus (disorder)")),
        entity("e1", _t, "stage 1A", "qualifier_value", "present"),
        entity("e2", _t, "Total abdominal hysterectomy", "procedure", "present",
               normalised_code=snomed("287922008", "Hysterectomy (procedure)")),
        entity("e3", _t, "bilateral salpingo-oophorectomy", "procedure", "present",
               normalised_code=snomed("83152002", "Oophorectomy (procedure)")),
        entity("e4", _t, "cancer confirmed", "X_PATHWAY_MILESTONE", "present",
               milestone_type="DIAGNOSIS_CONFIRMED",
               normalised_code=snomed("363346000", "Malignant neoplastic disease (disorder)")),
    ],
    "mdt_outcome",
))

# 44 — GP read-back from specialist
_t = "Read from oncology clinic letter. Patient diagnosed with non-Hodgkin's lymphoma — diffuse large B-cell type. Starting R-CHOP x 6 cycles. Macmillan nurse support arranged. Benefits advice given. Sicknote issued for 6 months."
EXAMPLES.append(doc(
    "dia_hae_02", _t,
    [
        entity("e0", _t, "non-Hodgkin's lymphoma", "disorder", "present",
               normalised_code=snomed("118600007", "Non-Hodgkin lymphoma (disorder)")),
        entity("e1", _t, "diagnosed with non-Hodgkin's lymphoma", "X_PATHWAY_MILESTONE", "present",
               milestone_type="DIAGNOSIS_CONFIRMED",
               normalised_code=snomed("118600007", "Non-Hodgkin lymphoma (disorder)")),
        entity("e2", _t, "R-CHOP", "substance", "present",
               normalised_code=snomed("703421000", "R-CHOP regimen (regime/therapy)")),
        entity("e3", _t, "6 cycles", "X_DOSAGE", "present"),
        entity("e4", _t, "6 months", "X_TEMPORAL", "present"),
    ],
    "gp_record",
))

# 45 — renal cell carcinoma
_t = "Urology letter. Incidental renal mass found on USS abdomen. CT renal protocol: 4.5 cm right renal mass, enhancement on contrast consistent with clear cell renal cell carcinoma. Stage T2aN0M0. Referred to specialist renal cancer MDT. Partial nephrectomy planned."
EXAMPLES.append(doc(
    "dia_ren_01", _t,
    [
        entity("e0", _t, "clear cell renal cell carcinoma", "disorder", "present",
               normalised_code=snomed("41607009", "Renal cell carcinoma (disorder)")),
        entity("e1", _t, "4.5 cm right renal mass", "finding", "present",
               value=4.5, unit="cm"),
        entity("e2", _t, "T2aN0M0", "qualifier_value", "present"),
        entity("e3", _t, "Partial nephrectomy", "procedure", "present",
               normalised_code=snomed("116028008", "Partial nephrectomy (procedure)")),
    ],
    "clinic_letter",
))

# 46 — cervical cancer
_t = "Gynaecology letter. Colposcopy biopsy: squamous cell carcinoma of cervix stage IB1. MRI pelvis confirming disease confined to cervix. MDT recommendation: radical hysterectomy with pelvic lymph node dissection. Discussed with patient. Consent obtained."
EXAMPLES.append(doc(
    "dia_cer_01", _t,
    [
        entity("e0", _t, "squamous cell carcinoma of cervix", "disorder", "present",
               normalised_code=snomed("254890008", "Squamous cell carcinoma of cervix (disorder)")),
        entity("e1", _t, "stage IB1", "qualifier_value", "present"),
        entity("e2", _t, "radical hysterectomy", "procedure", "present",
               normalised_code=snomed("287924007", "Radical hysterectomy (procedure)")),
        entity("e3", _t, "pelvic lymph node dissection", "procedure", "present",
               normalised_code=snomed("234262008", "Pelvic lymph node dissection (procedure)")),
    ],
    "mdt_outcome",
))


# ============================================================
# FIRST_TREATMENT (8)
# ============================================================

# 47
_t = "Started first cycle of capecitabine for colorectal cancer today. Dose 1250 mg/m2 BD. Reviewed by oncology nurse. Discussed side effects: hand-foot syndrome, diarrhoea, fatigue. SACT commenced."
EXAMPLES.append(doc(
    "trt_col_01", _t,
    [
        entity("e0", _t, "capecitabine", "substance", "present",
               normalised_code=snomed("372502001", "Capecitabine (substance)")),
        entity("e1", _t, "first cycle of capecitabine", "X_PATHWAY_MILESTONE", "present",
               milestone_type="FIRST_TREATMENT"),
        entity("e2", _t, "1250 mg/m2", "X_DOSAGE", "present"),
        entity("e3", _t, "colorectal cancer", "disorder", "present",
               normalised_code=snomed("363346000", "Malignant neoplastic disease (disorder)")),
        entity("e4", _t, "hand-foot syndrome", "finding", "present",
               normalised_code=snomed("403849000", "Hand-foot syndrome (finding)")),
        entity("e5", _t, "SACT commenced", "X_PATHWAY_MILESTONE", "present",
               milestone_type="FIRST_TREATMENT"),
    ],
    "clinic_letter",
    [relation("r0", "treats", "e0", "e3"), relation("r1", "dosage_of", "e2", "e0")],
))

# 48
_t = "Patient commenced tamoxifen 20 mg daily for hormone receptor positive breast cancer. Counselled regarding side effects including hot flushes, mood changes, DVT risk. Annual mammogram arranged. Oncology follow-up in 6 months."
EXAMPLES.append(doc(
    "trt_brs_01", _t,
    [
        entity("e0", _t, "tamoxifen", "substance", "present",
               normalised_code=snomed("372494005", "Tamoxifen (substance)")),
        entity("e1", _t, "tamoxifen 20 mg daily", "X_PATHWAY_MILESTONE", "present",
               milestone_type="FIRST_TREATMENT"),
        entity("e2", _t, "20 mg", "X_DOSAGE", "present"),
        entity("e3", _t, "daily", "X_FREQUENCY", "present"),
        entity("e4", _t, "hormone receptor positive breast cancer", "disorder", "present",
               normalised_code=snomed("408643008", "Infiltrating duct carcinoma of breast (disorder)")),
        entity("e5", _t, "hot flushes", "finding", "present",
               normalised_code=snomed("198436008", "Hot flushes (finding)")),
        entity("e6", _t, "DVT risk", "finding", "present",
               normalised_code=snomed("128053003", "Deep vein thrombosis (disorder)")),
        entity("e7", _t, "6 months", "X_TEMPORAL", "present"),
    ],
    "clinic_letter",
    [relation("r0", "treats", "e0", "e4"), relation("r1", "dosage_of", "e2", "e0"),
     relation("r2", "frequency_of", "e3", "e0")],
))

# 49
_t = "First cycle CHOP chemotherapy administered today for DLBCL. Rituximab 375 mg/m2 IV, cyclophosphamide, doxorubicin, vincristine, prednisolone. Tolerated well. GCSF prophylaxis prescribed. Next cycle in 21 days."
EXAMPLES.append(doc(
    "trt_hae_01", _t,
    [
        entity("e0", _t, "First cycle CHOP chemotherapy", "X_PATHWAY_MILESTONE", "present",
               milestone_type="FIRST_TREATMENT"),
        entity("e1", _t, "Rituximab", "substance", "present",
               normalised_code=snomed("387003001", "Rituximab (substance)")),
        entity("e2", _t, "375 mg/m2", "X_DOSAGE", "present"),
        entity("e3", _t, "cyclophosphamide", "substance", "present",
               normalised_code=snomed("372747003", "Cyclophosphamide (substance)")),
        entity("e4", _t, "DLBCL", "disorder", "present",
               normalised_code=snomed("413448000", "Diffuse large B-cell lymphoma (disorder)")),
        entity("e5", _t, "GCSF prophylaxis", "substance", "present",
               normalised_code=snomed("386947003", "Filgrastim (substance)")),
        entity("e6", _t, "21 days", "X_TEMPORAL", "present"),
    ],
    "clinic_letter",
))

# 50
_t = "Degarelix 240 mg SC injection administered today. Starting androgen deprivation therapy for prostate cancer prior to radiotherapy. PSA to be monitored monthly. Next dose in 28 days. Patient counselled on ADT side effects."
EXAMPLES.append(doc(
    "trt_pro_01", _t,
    [
        entity("e0", _t, "Degarelix 240 mg SC injection", "X_PATHWAY_MILESTONE", "present",
               milestone_type="FIRST_TREATMENT"),
        entity("e1", _t, "Degarelix", "substance", "present",
               normalised_code=snomed("416940008", "Degarelix (substance)")),
        entity("e2", _t, "240 mg", "X_DOSAGE", "present"),
        entity("e3", _t, "SC", "X_ROUTE", "present"),
        entity("e4", _t, "androgen deprivation therapy", "procedure", "present",
               normalised_code=snomed("169413002", "Hormone therapy (procedure)")),
        entity("e5", _t, "prostate cancer", "disorder", "present",
               normalised_code=snomed("399068003", "Malignant tumour of prostate (disorder)")),
        entity("e6", _t, "28 days", "X_TEMPORAL", "present"),
    ],
    "clinic_letter",
    [relation("r0", "treats", "e1", "e5"), relation("r1", "dosage_of", "e2", "e1")],
))

# 51
_t = "Laparoscopic anterior resection performed at City Hospital. Consultant surgeon: Mr [SURNAME]. Anastomosis formed. No intraoperative complications. Histology pending. Discharged day 4. District nursing arranged for stoma care."
EXAMPLES.append(doc(
    "trt_col_02", _t,
    [
        entity("e0", _t, "Laparoscopic anterior resection", "X_PATHWAY_MILESTONE", "present",
               milestone_type="FIRST_TREATMENT",
               normalised_code=snomed("235230009", "Anterior resection of rectum (procedure)")),
        entity("e1", _t, "Laparoscopic anterior resection", "procedure", "present",
               normalised_code=snomed("235230009", "Anterior resection of rectum (procedure)")),
        entity("e2", _t, "Histology pending", "finding", "present"),
        entity("e3", _t, "day 4", "X_TEMPORAL", "present"),
        entity("e4", _t, "stoma care", "procedure", "present"),
    ],
    "discharge_summary",
))

# 52
_t = "Commenced letrozole 2.5 mg daily for postmenopausal ER-positive breast cancer. Bone density scan arranged — baseline DEXA before starting aromatase inhibitor. Calcium and vitamin D supplementation prescribed."
EXAMPLES.append(doc(
    "trt_brs_02", _t,
    [
        entity("e0", _t, "letrozole", "substance", "present",
               normalised_code=snomed("386442008", "Letrozole (substance)")),
        entity("e1", _t, "letrozole 2.5 mg daily", "X_PATHWAY_MILESTONE", "present",
               milestone_type="FIRST_TREATMENT"),
        entity("e2", _t, "2.5 mg", "X_DOSAGE", "present"),
        entity("e3", _t, "daily", "X_FREQUENCY", "present"),
        entity("e4", _t, "ER-positive breast cancer", "disorder", "present",
               normalised_code=snomed("408643008", "Infiltrating duct carcinoma of breast (disorder)")),
        entity("e5", _t, "DEXA", "procedure", "present",
               normalised_code=snomed("312681000", "Dual energy X-ray absorptiometry (procedure)")),
    ],
    "clinic_letter",
    [relation("r0", "treats", "e0", "e4")],
))

# 53
_t = "Radiotherapy commenced for non-small cell lung cancer. 60 Gy in 30 fractions. Concurrent cisplatin 50 mg/m2 day 1 and day 8. Radical intent. Radiation oncologist: Dr [SURNAME]. Fatigue and oesophagitis anticipated."
EXAMPLES.append(doc(
    "trt_lng_01", _t,
    [
        entity("e0", _t, "Radiotherapy commenced", "X_PATHWAY_MILESTONE", "present",
               milestone_type="FIRST_TREATMENT"),
        entity("e1", _t, "Radiotherapy", "procedure", "present",
               normalised_code=snomed("1287742003", "Radiotherapy (procedure)")),
        entity("e2", _t, "60 Gy in 30 fractions", "X_DOSAGE", "present"),
        entity("e3", _t, "cisplatin", "substance", "present",
               normalised_code=snomed("387318005", "Cisplatin (substance)")),
        entity("e4", _t, "50 mg/m2", "X_DOSAGE", "present",
               after=_t.index("cisplatin")),
        entity("e5", _t, "non-small cell lung cancer", "disorder", "present",
               normalised_code=snomed("254637007", "Non-small cell carcinoma of lung (disorder)")),
        entity("e6", _t, "oesophagitis", "finding", "present",
               normalised_code=snomed("235592006", "Oesophagitis (disorder)")),
    ],
    "clinic_letter",
    [relation("r0", "treats", "e1", "e5"), relation("r1", "treats", "e3", "e5")],
))

# 54
_t = "Mastectomy of right breast performed today under GA. Sentinel lymph node biopsy performed — 2 nodes removed. Procedure uncomplicated. Specimen sent for histology. Drain in situ. Expected discharge tomorrow."
EXAMPLES.append(doc(
    "trt_brs_03", _t,
    [
        entity("e0", _t, "Mastectomy of right breast", "X_PATHWAY_MILESTONE", "present",
               milestone_type="FIRST_TREATMENT",
               normalised_code=snomed("172043006", "Mastectomy (procedure)")),
        entity("e1", _t, "Mastectomy", "procedure", "present",
               normalised_code=snomed("172043006", "Mastectomy (procedure)")),
        entity("e2", _t, "Sentinel lymph node biopsy", "procedure", "present",
               normalised_code=snomed("396487001", "Sentinel node biopsy (procedure)")),
    ],
    "discharge_summary",
))


# ============================================================
# STILL_INVESTIGATING (10)
# ============================================================

# 55
_t = "Awaiting colonoscopy results for 2WW colorectal referral. Biopsies taken at procedure on 03/11/2023. Histology typically 2 weeks. Patient to be contacted with results. Follow-up appointment booked."
EXAMPLES.append(doc(
    "inv_col_01", _t,
    [
        entity("e0", _t, "Awaiting colonoscopy results", "finding", "present"),
        entity("e1", _t, "Biopsies taken", "procedure", "present",
               normalised_code=snomed("86273004", "Biopsy (procedure)")),
        entity("e2", _t, "03/11/2023", "X_TEMPORAL", "present"),
        entity("e3", _t, "2 weeks", "X_TEMPORAL", "present"),
    ],
    "gp_record",
))

# 56
_t = "Core biopsy right breast performed at breast clinic. Awaiting histology result. Patient very anxious. Provided written information and Macmillan helpline number. Results appointment in 7 days."
EXAMPLES.append(doc(
    "inv_brs_01", _t,
    [
        entity("e0", _t, "Core biopsy right breast", "procedure", "present",
               normalised_code=snomed("86273004", "Biopsy (procedure)")),
        entity("e1", _t, "Awaiting histology result", "finding", "present"),
        entity("e2", _t, "7 days", "X_TEMPORAL", "present"),
    ],
    "gp_record",
))

# 57
_t = "CT chest abdomen pelvis requested for 2WW lung pathway — right upper lobe opacity on CXR. Radiology appointment: 2 weeks. Patient advised to return if symptoms worsen. Haemoptysis ongoing."
EXAMPLES.append(doc(
    "inv_lng_01", _t,
    [
        entity("e0", _t, "CT chest abdomen pelvis requested", "procedure", "present",
               normalised_code=snomed("77477000", "Computerized axial tomography (procedure)")),
        entity("e1", _t, "right upper lobe opacity", "finding", "present",
               normalised_code=snomed("25505002", "Opacity of lung (finding)")),
        entity("e2", _t, "Haemoptysis ongoing", "finding", "present",
               normalised_code=snomed("66857006", "Haemoptysis (finding)")),
        entity("e3", _t, "2 weeks", "X_TEMPORAL", "present"),
    ],
    "gp_record",
))

# 58
_t = "MRI liver arranged to characterise indeterminate liver lesion seen on CT abdomen. Lesion 2.3 cm segment 6 — enhancement pattern suspicious for HCC in context of known cirrhosis. Liver MDT referral made. AFP 650 IU/mL elevated."
EXAMPLES.append(doc(
    "inv_hcc_01", _t,
    [
        entity("e0", _t, "MRI liver", "procedure", "present",
               normalised_code=snomed("726252009", "MRI of liver (procedure)")),
        entity("e1", _t, "indeterminate liver lesion", "finding", "present",
               normalised_code=snomed("6157006", "Liver mass (finding)")),
        entity("e2", _t, "suspicious for HCC", "disorder", "possible",
               normalised_code=snomed("109841003", "Hepatocellular carcinoma (disorder)")),
        entity("e3", _t, "AFP 650 IU/mL", "observable_entity", "present",
               value=650, unit="IU/mL",
               normalised_code=snomed("51176003", "Alpha-fetoprotein measurement (observable entity)")),
        entity("e4", _t, "2.3 cm", "X_TEMPORAL", "present"),
    ],
    "gp_record",
))

# 59
_t = "PSA 9.8 ng/mL — elevated. Repeat in 6 weeks as per protocol. If remains elevated, referral to urology 2WW to be made. Digital rectal examination benign. Under investigation."
EXAMPLES.append(doc(
    "inv_pro_01", _t,
    [
        entity("e0", _t, "PSA 9.8 ng/mL", "observable_entity", "present",
               value=9.8, unit="ng/mL",
               normalised_code=snomed("63476009", "Prostate specific antigen measurement (observable entity)")),
        entity("e1", _t, "6 weeks", "X_TEMPORAL", "present"),
        entity("e2", _t, "Under investigation", "finding", "present"),
    ],
    "gp_record",
))

# 60
_t = "Haematology clinic. Bone marrow biopsy performed today for suspected multiple myeloma. Serum protein electrophoresis shows IgG paraprotein 32 g/L. Awaiting trephine and cytogenetics results. FISH panel sent. Results expected in 10 days."
EXAMPLES.append(doc(
    "inv_mye_01", _t,
    [
        entity("e0", _t, "Bone marrow biopsy", "procedure", "present",
               normalised_code=snomed("274339000", "Bone marrow biopsy (procedure)")),
        entity("e1", _t, "suspected multiple myeloma", "disorder", "possible",
               normalised_code=snomed("109989006", "Multiple myeloma (disorder)")),
        entity("e2", _t, "IgG paraprotein 32 g/L", "observable_entity", "present",
               value=32, unit="g/L"),
        entity("e3", _t, "Awaiting trephine and cytogenetics results", "finding", "present"),
        entity("e4", _t, "10 days", "X_TEMPORAL", "present"),
    ],
    "clinic_letter",
))

# 61
_t = "Follow-up appointment to discuss colonoscopy and biopsy results in 2 weeks. Results not yet available. Patient contacted — appointment confirmed for 17/11/2023. 2WW clock ongoing."
EXAMPLES.append(doc(
    "inv_col_02", _t,
    [
        entity("e0", _t, "colonoscopy and biopsy results", "procedure", "present",
               normalised_code=snomed("86273004", "Biopsy (procedure)")),
        entity("e1", _t, "Results not yet available", "finding", "present"),
        entity("e2", _t, "2 weeks", "X_TEMPORAL", "present"),
        entity("e3", _t, "17/11/2023", "X_TEMPORAL", "present"),
        entity("e4", _t, "2WW clock ongoing", "X_PATHWAY_MILESTONE", "present",
               milestone_type="FAST_TRACK_REFERRAL"),
    ],
    "gp_record",
))

# 62
_t = "CT urogram completed. No obvious renal mass. Incidental finding: right proximal ureteric filling defect — suspicious, may represent urothelial tumour. Urology urgent outpatient referral made. Ureteroscopy planned. Under investigation."
EXAMPLES.append(doc(
    "inv_uro_02", _t,
    [
        entity("e0", _t, "CT urogram", "procedure", "present",
               normalised_code=snomed("713830008", "CT urogram (procedure)")),
        entity("e1", _t, "ureteric filling defect", "finding", "present"),
        entity("e2", _t, "suspicious, may represent urothelial tumour", "disorder", "possible",
               normalised_code=snomed("363477002", "Malignant neoplasm of urinary bladder (disorder)")),
        entity("e3", _t, "Ureteroscopy", "procedure", "present",
               normalised_code=snomed("713834004", "Ureteroscopy (procedure)")),
        entity("e4", _t, "Under investigation", "finding", "present"),
    ],
    "radiology_report",
))

# 63 — PET-CT awaited
_t = "PET-CT requested following suspicious 18F-FDG activity on staging CT in mediastinum. Clinically: suspected lung cancer versus lymphoma. Bronchoscopy with BAL and biopsy arranged. Results pending. MDT to review once histology available."
EXAMPLES.append(doc(
    "inv_med_01", _t,
    [
        entity("e0", _t, "PET-CT", "procedure", "present",
               normalised_code=snomed("703430008", "Positron emission tomography (procedure)")),
        entity("e1", _t, "suspected lung cancer", "disorder", "possible",
               normalised_code=snomed("254637007", "Non-small cell carcinoma of lung (disorder)")),
        entity("e2", _t, "lymphoma", "disorder", "possible",
               normalised_code=snomed("118613001", "Lymphoma (disorder)")),
        entity("e3", _t, "Bronchoscopy", "procedure", "present",
               normalised_code=snomed("10847001", "Bronchoscopy (procedure)")),
        entity("e4", _t, "Results pending", "finding", "present"),
    ],
    "gp_record",
))

# 64 — suspicious USS
_t = "USS abdomen: right upper quadrant mass 4 cm suspicious for malignancy — heterogeneous, poorly defined margin. Alpha fetoprotein 210 IU/mL elevated. Hepatitis B sAg positive. Urgent liver clinic referral made. CT liver protocol requested."
EXAMPLES.append(doc(
    "inv_hcc_02", _t,
    [
        entity("e0", _t, "right upper quadrant mass 4 cm", "finding", "present",
               value=4, unit="cm"),
        entity("e1", _t, "suspicious for malignancy", "disorder", "possible",
               normalised_code=snomed("363346000", "Malignant neoplastic disease (disorder)")),
        entity("e2", _t, "Alpha fetoprotein 210 IU/mL", "observable_entity", "present",
               value=210, unit="IU/mL",
               normalised_code=snomed("51176003", "Alpha-fetoprotein measurement (observable entity)")),
        entity("e3", _t, "CT liver protocol", "procedure", "present",
               normalised_code=snomed("77477000", "Computerized axial tomography (procedure)")),
    ],
    "radiology_report",
))


# ============================================================
# PENDING_LETTER (6)
# ============================================================

# 65
_t = "Clinic letter from Oncology received and filed. Document transfer from City Hospital Oncology Department. See letter for details of consultation and management plan."
EXAMPLES.append(doc(
    "plt_onc_01", _t,
    [
        entity("e0", _t, "Clinic letter from Oncology", "X_PATHWAY_MILESTONE", "present",
               milestone_type="CANCER_EXCLUDED",
               confidence=0.6),
        entity("e1", _t, "Document transfer", "event", "present"),
    ],
    "gp_record",
))

# 66
_t = "Outpatient letter from Breast Clinic to GP. Filed in patient record. Refer to attached correspondence for triple assessment results and management plan."
EXAMPLES.append(doc(
    "plt_brs_01", _t,
    [
        entity("e0", _t, "Outpatient letter from Breast Clinic", "X_PATHWAY_MILESTONE", "present",
               milestone_type="CANCER_EXCLUDED",
               confidence=0.6),
    ],
    "gp_record",
))

# 67
_t = "Hospital discharge letter from Urology. Filed. Patient discharged following cystoscopy. Letter to be reviewed by GP. No further details available in this entry."
EXAMPLES.append(doc(
    "plt_uro_01", _t,
    [
        entity("e0", _t, "Hospital discharge letter from Urology", "X_PATHWAY_MILESTONE", "present",
               milestone_type="CANCER_EXCLUDED",
               confidence=0.6),
        entity("e1", _t, "cystoscopy", "procedure", "present",
               normalised_code=snomed("44491007", "Cystoscopy (procedure)")),
    ],
    "gp_record",
))

# 68
_t = "Colorectal surgery to GP. 26/10/2023. Filed. As per attached letter from Mr [SURGEON], Consultant Colorectal Surgeon."
EXAMPLES.append(doc(
    "plt_col_01", _t,
    [
        entity("e0", _t, "Colorectal surgery to GP", "X_PATHWAY_MILESTONE", "present",
               milestone_type="CANCER_EXCLUDED",
               confidence=0.6),
        entity("e1", _t, "26/10/2023", "X_TEMPORAL", "present"),
    ],
    "gp_record",
))

# 69
_t = "Haematology to GP clinic letter. Date: 12/09/2023. Summary: see attached letter for results of lymph node biopsy and management plan. Auto-filed."
EXAMPLES.append(doc(
    "plt_hae_01", _t,
    [
        entity("e0", _t, "Haematology to GP clinic letter", "X_PATHWAY_MILESTONE", "present",
               milestone_type="CANCER_EXCLUDED",
               confidence=0.6),
        entity("e1", _t, "lymph node biopsy", "procedure", "present",
               normalised_code=snomed("274330002", "Lymph node biopsy (procedure)")),
        entity("e2", _t, "12/09/2023", "X_TEMPORAL", "present"),
    ],
    "gp_record",
))

# 70
_t = "Results letter from Dermatology. Filed 08/11/2023. Relates to recent 2WW referral for pigmented lesion. Content available in attached correspondence."
EXAMPLES.append(doc(
    "plt_ski_01", _t,
    [
        entity("e0", _t, "Results letter from Dermatology", "X_PATHWAY_MILESTONE", "present",
               milestone_type="CANCER_EXCLUDED",
               confidence=0.6),
        entity("e1", _t, "pigmented lesion", "finding", "present",
               normalised_code=snomed("89698007", "Pigmented lesion (finding)")),
        entity("e2", _t, "08/11/2023", "X_TEMPORAL", "present"),
    ],
    "gp_record",
))


# ============================================================
# FDS_CLOCK_START (3)
# ============================================================

# 71
_t = "FDS 28-day faster diagnosis standard clock started today. First definitive specialist assessment carried out. Date of decision to refer: 04/10/2023. Date of first appointment: 01/11/2023. Delay: 28 days."
EXAMPLES.append(doc(
    "fds_01", _t,
    [
        entity("e0", _t, "FDS 28-day faster diagnosis standard clock started", "X_PATHWAY_MILESTONE", "present",
               milestone_type="FDS_CLOCK_START"),
        entity("e1", _t, "04/10/2023", "X_TEMPORAL", "present"),
        entity("e2", _t, "01/11/2023", "X_TEMPORAL", "present"),
        entity("e3", _t, "28 days", "X_TEMPORAL", "present"),
    ],
    "gp_record",
))

# 72
_t = "Cancer pathway clock started. Referral received under 28-day faster diagnosis standard. GP referral date: 15/09/2023. Triage complete. Appointment within standard. Clock start date recorded."
EXAMPLES.append(doc(
    "fds_02", _t,
    [
        entity("e0", _t, "Cancer pathway clock started", "X_PATHWAY_MILESTONE", "present",
               milestone_type="FDS_CLOCK_START"),
        entity("e1", _t, "28-day faster diagnosis standard", "X_PATHWAY_MILESTONE", "present",
               milestone_type="FDS_CLOCK_START"),
        entity("e2", _t, "15/09/2023", "X_TEMPORAL", "present"),
    ],
    "gp_record",
))

# 73
_t = "28-day FDS target: met. Referral to diagnosis within 27 days. Clock start: 05/10/2023. Date of diagnosis: 01/11/2023. Performance within standard. Case closed."
EXAMPLES.append(doc(
    "fds_03", _t,
    [
        entity("e0", _t, "28-day FDS", "X_PATHWAY_MILESTONE", "present",
               milestone_type="FDS_CLOCK_START"),
        entity("e1", _t, "05/10/2023", "X_TEMPORAL", "present"),
        entity("e2", _t, "01/11/2023", "X_TEMPORAL", "present"),
        entity("e3", _t, "27 days", "X_TEMPORAL", "present"),
    ],
    "gp_record",
))


# ============================================================
# NEGATION-HEAVY examples (5)
# ============================================================

# 74
_t = "History: No change in bowel habit. No rectal bleeding. No weight loss. No night sweats. No haematuria. No haemoptysis. No palpable mass. No lymphadenopathy. No dysphagia. Reassured."
EXAMPLES.append(doc(
    "neg_01", _t,
    [
        entity("e0", _t, "No", "X_NEGATION_CUE", "present", after=_t.index("No change")),
        entity("e1", _t, "change in bowel habit", "finding", "absent",
               normalised_code=snomed("197121002", "Change in bowel habit (finding)")),
        entity("e2", _t, "No", "X_NEGATION_CUE", "present", after=_t.index("No rectal")),
        entity("e3", _t, "rectal bleeding", "finding", "absent",
               normalised_code=snomed("12063002", "Rectal haemorrhage (finding)")),
        entity("e4", _t, "No", "X_NEGATION_CUE", "present", after=_t.index("No weight")),
        entity("e5", _t, "weight loss", "finding", "absent",
               normalised_code=snomed("89362005", "Weight loss (finding)")),
        entity("e6", _t, "No", "X_NEGATION_CUE", "present", after=_t.index("No night")),
        entity("e7", _t, "night sweats", "finding", "absent",
               normalised_code=snomed("42984000", "Night sweats (finding)")),
        entity("e8", _t, "No", "X_NEGATION_CUE", "present", after=_t.index("No lymph")),
        entity("e9", _t, "lymphadenopathy", "finding", "absent",
               normalised_code=snomed("30746006", "Lymphadenopathy (finding)")),
        entity("e10", _t, "No", "X_NEGATION_CUE", "present", after=_t.index("No dysphagia")),
        entity("e11", _t, "dysphagia", "finding", "absent",
               normalised_code=snomed("40739000", "Dysphagia (finding)")),
    ],
    "gp_record",
    [
        relation("r0", "negates", "e0", "e1"),
        relation("r1", "negates", "e2", "e3"),
        relation("r2", "negates", "e4", "e5"),
        relation("r3", "negates", "e6", "e7"),
        relation("r4", "negates", "e8", "e9"),
        relation("r5", "negates", "e10", "e11"),
    ],
))

# 75
_t = "Biopsy results reviewed. No evidence of malignancy. No lymphovascular invasion. No perineural invasion. Margins clear. Not cancer. Diagnosis: reactive changes only."
EXAMPLES.append(doc(
    "neg_02", _t,
    [
        entity("e0", _t, "No evidence of malignancy", "X_PATHWAY_MILESTONE", "absent",
               milestone_type="CANCER_EXCLUDED",
               normalised_code=snomed("395100000", "No evidence of cancer found (situation)")),
        entity("e1", _t, "No evidence of", "X_NEGATION_CUE", "present"),
        entity("e2", _t, "malignancy", "disorder", "absent",
               normalised_code=snomed("363346000", "Malignant neoplastic disease (disorder)")),
        entity("e3", _t, "No", "X_NEGATION_CUE", "present",
               after=_t.index("No lymphovascular")),
        entity("e4", _t, "lymphovascular invasion", "finding", "absent"),
        entity("e5", _t, "Not cancer", "X_PATHWAY_MILESTONE", "absent",
               milestone_type="CANCER_EXCLUDED",
               normalised_code=snomed("395100000", "No evidence of cancer found (situation)")),
    ],
    "pathology_report",
    [relation("r0", "negates", "e1", "e2"), relation("r1", "negates", "e3", "e4")],
))

# 76
_t = "CT chest: No primary lung mass identified. No mediastinal lymphadenopathy. No pleural effusion. No bone metastases visible. Normal chest CT. No evidence of malignancy."
EXAMPLES.append(doc(
    "neg_ct_01", _t,
    [
        entity("e0", _t, "No primary lung mass identified", "finding", "absent"),
        entity("e1", _t, "No", "X_NEGATION_CUE", "present", after=_t.index("No primary")),
        entity("e2", _t, "No mediastinal lymphadenopathy", "finding", "absent",
               normalised_code=snomed("30746006", "Lymphadenopathy (finding)")),
        entity("e3", _t, "No pleural effusion", "finding", "absent",
               normalised_code=snomed("52612000", "Pleural effusion (finding)")),
        entity("e4", _t, "No bone metastases", "finding", "absent",
               normalised_code=snomed("128462008", "Metastatic disease (finding)")),
        entity("e5", _t, "No evidence of malignancy", "X_PATHWAY_MILESTONE", "absent",
               milestone_type="CANCER_EXCLUDED",
               normalised_code=snomed("395100000", "No evidence of cancer found (situation)")),
    ],
    "radiology_report",
))

# 77
_t = "Seen post-referral. Reports: no further haematuria, no flank pain. Urine dipstick: no blood, no protein. Reassured — infection likely cause of haematuria. Discharged from 2WW pathway. Cancer ruled out."
EXAMPLES.append(doc(
    "neg_uro_01", _t,
    [
        entity("e0", _t, "no further haematuria", "finding", "absent",
               normalised_code=snomed("34436003", "Blood in urine (finding)")),
        entity("e1", _t, "no", "X_NEGATION_CUE", "present",
               after=_t.index("no further")),
        entity("e2", _t, "no flank pain", "finding", "absent",
               normalised_code=snomed("57676002", "Joint pain (finding)")),
        entity("e3", _t, "Discharged from 2WW pathway", "X_PATHWAY_MILESTONE", "present",
               milestone_type="CANCER_EXCLUDED"),
        entity("e4", _t, "Cancer ruled out", "X_PATHWAY_MILESTONE", "present",
               milestone_type="CANCER_EXCLUDED",
               normalised_code=snomed("395100000", "No evidence of cancer found (situation)")),
    ],
    "gp_record",
))

# 78
_t = "Oncology letter. This patient was referred under 2WW for suspected colorectal cancer. Following full assessment including colonoscopy and CT, we are pleased to confirm that there is no evidence of colorectal cancer. Colonoscopy showed only diverticular disease. Cancer has been excluded. We have discharged this patient from our service."
EXAMPLES.append(doc(
    "neg_col_let_01", _t,
    [
        entity("e0", _t, "2WW for suspected colorectal cancer", "X_PATHWAY_MILESTONE", "present",
               milestone_type="FAST_TRACK_REFERRAL"),
        entity("e1", _t, "suspected colorectal cancer", "disorder", "possible",
               normalised_code=snomed("363346000", "Malignant neoplastic disease (disorder)")),
        entity("e2", _t, "colonoscopy", "procedure", "present",
               normalised_code=snomed("73761001", "Colonoscopy (procedure)")),
        entity("e3", _t, "no evidence of colorectal cancer", "X_PATHWAY_MILESTONE", "absent",
               milestone_type="CANCER_EXCLUDED",
               normalised_code=snomed("395100000", "No evidence of cancer found (situation)")),
        entity("e4", _t, "no evidence of", "X_NEGATION_CUE", "present",
               after=_t.index("no evidence of colorectal")),
        entity("e5", _t, "diverticular disease", "disorder", "present",
               normalised_code=snomed("419202007", "Diverticular disease (disorder)")),
        entity("e6", _t, "Cancer has been excluded", "X_PATHWAY_MILESTONE", "present",
               milestone_type="CANCER_EXCLUDED",
               normalised_code=snomed("395100000", "No evidence of cancer found (situation)")),
        entity("e7", _t, "discharged this patient from our service", "X_PATHWAY_MILESTONE", "present",
               milestone_type="CANCER_EXCLUDED"),
    ],
    "clinic_letter",
    [relation("r0", "negates", "e4", "e3")],
))


# ---------------------------------------------------------------------------
# Write output
# ---------------------------------------------------------------------------

def main() -> None:
    out_dir = Path(__file__).parent.parent / "exports" / "ner" / "training"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "exclusion_domain_v1.jsonl"

    errors: list[str] = []
    written = 0

    with out_path.open("w", encoding="utf-8") as fh:
        for example in EXAMPLES:
            # Basic integrity checks
            text = example["text"]
            for ent in example["entities"]:
                actual = text[ent["start"]: ent["end"]]
                if actual != ent["text"]:
                    errors.append(
                        f"[{example['document_id']}] entity {ent['entity_id']}: "
                        f"offset mismatch — expected {ent['text']!r}, got {actual!r}"
                    )
            fh.write(json.dumps(example, ensure_ascii=False) + "\n")
            written += 1

    if errors:
        print(f"\n{'='*60}", file=sys.stderr)
        print(f"OFFSET ERRORS ({len(errors)}):", file=sys.stderr)
        for e in errors:
            print(f"  {e}", file=sys.stderr)
        print(f"{'='*60}\n", file=sys.stderr)
        sys.exit(1)

    # Summary
    from collections import Counter
    milestone_counts: Counter = Counter()
    label_counts: Counter = Counter()
    for ex in EXAMPLES:
        for ent in ex["entities"]:
            label_counts[ent["label"]] += 1
            if mt := ent.get("milestone_type"):
                milestone_counts[mt] += 1

    print(f"Written {written} examples -> {out_path}")
    print("\nEntity label distribution:")
    for label, count in sorted(label_counts.items()):
        print(f"  {label:<30} {count:>4}")
    print("\nMilestone type distribution:")
    for mt, count in sorted(milestone_counts.items()):
        print(f"  {mt:<30} {count:>4}")


if __name__ == "__main__":
    main()
