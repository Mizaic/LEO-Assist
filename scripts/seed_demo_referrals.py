#!/usr/bin/env python3
"""Seed synthetic referral documents for the demo GP practice patients.

Creates ReferralRequest, DocumentReference and Chunk nodes for all 80 demo
patients across 14 specialty pathways, modelled on real NHS referral forms.

Pathway distribution:
  Patients 001-035 (cancer cohort)   -> 2WW cancer pathways (lung, colorectal,
                                        breast, prostate, upper_gi, skin)
  Patients 036-060 (benign/open)     -> non-cancer specialties (cardiology,
                                        urology, gastroenterology, rheumatology,
                                        neurology, respiratory, endocrinology)
  Patients 061-070 (open/in-progress)-> mixed 2WW + urgent specialties
  Patients 071-080 (blood signal)    -> haematology + mixed cancer

Usage:
    python -m scripts.seed_demo_referrals                 # seed (idempotent)
    python -m scripts.seed_demo_referrals --force         # teardown + re-seed
    python -m scripts.seed_demo_referrals --teardown      # remove demo referrals
    python -m scripts.seed_demo_referrals --direct-code   # seed + write SNOMED links
    python -m scripts.seed_demo_referrals --run-pipeline  # seed + full LLM pipeline
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import random
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services" / "api"))

load_dotenv(ROOT / "secrets" / ".env")
load_dotenv(ROOT / ".env", override=False)

from libs.neo4j_client.client import PatientGraphClient  # noqa: E402

_RNG = random.Random(99)

DEMO_GP_ID = "demo-gp-001"
DEMO_SP_ID = "demo-sp-001"
DEMO_SERVICE_ID = "demo-service-001"

_N_REFERRALS = 80

_REFERRAL_PLAN_ID = "pd-referral-assessment"
_GUIDELINE_ID = "NG12"

# ---------------------------------------------------------------------------
# Demographics helpers
# ---------------------------------------------------------------------------

_DEMO_SURNAMES = [
    "Smith", "Jones", "Williams", "Brown", "Taylor", "Davies", "Evans",
    "Wilson", "Thomas", "Roberts", "Johnson", "Walker", "Wright",
    "Robinson", "Thompson", "White", "Hughes", "Edwards", "Green", "Hall",
    "Lewis", "Harris", "Clarke", "Patel", "Jackson", "Wood", "Turner",
    "Martin", "Cooper", "Hill",
]
_DEMO_FORENAMES_M = [
    "James", "Robert", "Michael", "William", "David", "Richard", "Joseph",
    "Thomas", "Charles", "Daniel", "Peter", "George", "Andrew", "Kenneth",
    "Steven",
]
_DEMO_FORENAMES_F = [
    "Mary", "Patricia", "Jennifer", "Linda", "Barbara", "Susan", "Jessica",
    "Karen", "Sarah", "Lisa", "Helen", "Christine", "Anne", "Catherine",
    "Margaret",
]


def _rand_nhs() -> str:
    return str(_RNG.randint(1_000_000_000, 9_999_999_999))


def _rand_dob(age_min: int = 40, age_max: int = 82) -> str:
    age = _RNG.randint(age_min, age_max)
    anchor = date(2024, 1, 1)
    return (anchor - timedelta(days=age * 365 + _RNG.randint(0, 364))).isoformat()


def _referral_date(idx: int) -> str:
    base = date(2023, 9, 1)
    return (base + timedelta(days=(idx * 5) % 365)).isoformat()


def _person(idx: int) -> dict[str, str]:
    gender = "male" if idx % 2 == 0 else "female"
    forenames = _DEMO_FORENAMES_M if gender == "male" else _DEMO_FORENAMES_F
    return {
        "surname": _DEMO_SURNAMES[(idx - 1) % len(_DEMO_SURNAMES)].upper(),
        "forename": forenames[(idx - 1) % len(forenames)],
        "dob": _rand_dob(),
        "nhs": _rand_nhs(),
        "gender": gender,
        "gp_name": "Demo Medical Centre",
        "gp_code": "DEMO01",
        "referral_date": _referral_date(idx),
    }


# ---------------------------------------------------------------------------
# Pre-coded SNOMED concepts per pathway
# Format: (snomed_concept_id, term, semantic_tag, assertion)
# assertion: "present" | "historical" | "suspected" | "negated"
# ---------------------------------------------------------------------------

_PATHWAY_CODES: dict[str, list[tuple[str, str, str, str]]] = {
    # -- Cancer 2WW --
    "lung": [
        ("66857006", "Haemoptysis", "finding", "present"),
        ("49727002", "Cough", "finding", "present"),
        ("267111009", "Mass of lung", "disorder", "suspected"),
        ("13645005", "COPD", "disorder", "historical"),
        ("77176002", "Smoker", "finding", "historical"),
    ],
    "colorectal": [
        ("267060002", "Rectal bleeding", "finding", "present"),
        ("197127009", "Change in bowel habit", "finding", "present"),
        ("271737000", "Anaemia", "disorder", "present"),
        ("413822004", "FIT positive", "finding", "present"),
        ("363346000", "Malignant neoplasm of colorectum", "disorder", "suspected"),
    ],
    "breast": [
        ("309568002", "Breast lump", "finding", "present"),
        ("416940007", "Skin puckering of breast", "finding", "present"),
        ("254837009", "Carcinoma of breast", "disorder", "suspected"),
    ],
    "prostate": [
        ("7522000", "Urinary hesitancy", "finding", "present"),
        ("49650001", "Dysuria", "finding", "present"),
        ("77880009", "Elevated PSA", "finding", "present"),
        ("399068003", "Carcinoma of prostate", "disorder", "suspected"),
    ],
    "upper_gi": [
        ("40739000", "Dysphagia", "finding", "present"),
        ("162076009", "Weight loss", "finding", "present"),
        ("30473006", "Epigastric pain", "finding", "present"),
        ("413448000", "Carcinoma of oesophagus", "disorder", "suspected"),
    ],
    "skin": [
        ("21390004", "Pigmented lesion of skin", "finding", "present"),
        ("371155009", "Asymmetrical melanocytic lesion", "finding", "present"),
        ("372244006", "Malignant melanoma of skin", "disorder", "suspected"),
    ],
    # -- Non-cancer specialties --
    "cardiology": [
        ("29857009", "Chest pain", "finding", "present"),
        ("267036007", "Breathlessness", "finding", "present"),
        ("44077006", "Numbness", "finding", "present"),
        ("38341003", "Hypertension", "disorder", "historical"),
        ("53741008", "Coronary arteriosclerosis", "disorder", "suspected"),
    ],
    "urology": [
        ("83128009", "Haematuria", "finding", "present"),
        ("224960004", "Frequency of micturition", "finding", "present"),
        ("57773001", "Loin pain", "finding", "present"),
        ("197834003", "Urinary tract infection", "disorder", "historical"),
    ],
    "gastroenterology": [
        ("21522001", "Abdominal pain", "finding", "present"),
        ("62315008", "Diarrhoea", "finding", "present"),
        ("16932000", "Nausea and vomiting", "finding", "present"),
        ("271737000", "Anaemia", "disorder", "present"),
        ("24526004", "Inflammatory bowel disease", "disorder", "suspected"),
    ],
    "rheumatology": [
        ("57676002", "Joint pain", "finding", "present"),
        ("57178007", "Morning stiffness", "finding", "present"),
        ("9826008", "Conjunctivitis", "finding", "present"),
        ("69896004", "Rheumatoid arthritis", "disorder", "suspected"),
        ("38341003", "Hypertension", "disorder", "historical"),
    ],
    "neurology": [
        ("25064002", "Headache", "finding", "present"),
        ("44695005", "Paralysis", "finding", "present"),
        ("271807003", "Skin eruption", "finding", "present"),
        ("230690007", "Stroke", "disorder", "suspected"),
        ("386661006", "Fever", "finding", "historical"),
    ],
    "respiratory": [
        ("267036007", "Breathlessness", "finding", "present"),
        ("49727002", "Cough", "finding", "present"),
        ("57335002", "Coughing up blood", "finding", "present"),
        ("195967001", "Asthma", "disorder", "historical"),
        ("13645005", "COPD", "disorder", "suspected"),
    ],
    "endocrinology": [
        ("162076009", "Weight loss", "finding", "present"),
        ("80394007", "Hyperglycaemia", "finding", "present"),
        ("84229001", "Fatigue", "finding", "present"),
        ("73211009", "Diabetes mellitus", "disorder", "historical"),
        ("34093004", "Thyroid disorder", "disorder", "suspected"),
    ],
    "haematology": [
        ("271737000", "Anaemia", "disorder", "present"),
        ("302215000", "Thrombocytopenia", "disorder", "present"),
        ("55821 00", "Lymphadenopathy", "finding", "present"),
        ("84229001", "Fatigue", "finding", "present"),
        ("118600007", "Malignant lymphoma", "disorder", "suspected"),
    ],
}


# ---------------------------------------------------------------------------
# Chunk text factories
# ---------------------------------------------------------------------------

def _chunks_lung(p: dict) -> list[str]:
    return [
        (
            f"--- Document: DEMO Lung 2WW Referral {p['surname']}.docx ---\n\n"
            "LUNG CANCER 2 WEEK WAIT REFERRAL\n\n"
            "Referral under the suspected lung cancer 2WW pathway (NICE NG12)."
        ),
        (
            "| Referral criteria: |  |\n| --- | --- |\n"
            "| Unexplained haemoptysis aged 40 or over | [X] |\n"
            "| Chest X-ray suggestive of lung cancer | [X] |\n"
            "| Signs consistent with metastatic lung cancer | [ ] |\n"
        ),
        (
            f"| Patient: {p['surname']}, {p['forename']} | NHS No: {p['nhs']} |\n"
            f"| --- | --- |\n| DOB: {p['dob']} | GP: {p['gp_name']} |\n"
            f"| Referral date: {p['referral_date']} | Referring GP: Dr Demo |\n"
        ),
        (
            "| Reason for referral: |\n| --- |\n"
            "| [DEMO] Patient presents with a 6-week history of haemoptysis. "
            "Current smoker with 30 pack-year history. Recent CXR shows right "
            "hilar opacity. Concerned about suspected lung cancer. |\n"
        ),
        (
            "| Blood results: |\n| --- |\n"
            "| FBC: Hb 118 g/L, WCC 9.1, Plts 380, MCV 82 |\n"
            "| CRP: 22 mg/L | LFTs normal | Ca 2.4 |\n"
        ),
        (
            "| Medical history: |\n| --- |\n"
            "| Hypertension, COPD, Ex-smoker 30 pack-years |\n"
            "| Medications: Salbutamol, Tiotropium, Amlodipine 5mg |\n"
        ),
    ]


def _chunks_colorectal(p: dict) -> list[str]:
    return [
        (
            f"--- Document: DEMO Lower GI 2WW Referral {p['surname']}.docx ---\n\n"
            "LOWER GI / COLORECTAL CANCER 2 WEEK WAIT REFERRAL (NG12)"
        ),
        (
            "| Referral criteria: |  |\n| --- | --- |\n"
            "| Rectal bleeding with change in bowel habit aged 40+ | [X] |\n"
            "| FIT positive (>10 mcg Hb/g) | [X] |\n"
            "| Iron deficiency anaemia | [ ] |\n"
        ),
        (
            f"| Patient: {p['surname']}, {p['forename']} | NHS No: {p['nhs']} |\n"
            f"| --- | --- |\n| DOB: {p['dob']} | Referral date: {p['referral_date']} |\n"
        ),
        (
            "| Reason for referral: |\n| --- |\n"
            "| [DEMO] 10-week history of fresh rectal bleeding with looser stools "
            "and increased frequency. FIT result 45 mcg Hb/g. "
            "Concerned about possible colorectal cancer. |\n"
        ),
        (
            "| Blood results: |\n| --- |\n"
            "| FBC: Hb 108 g/L (low), MCV 74, Plts 445 |\n"
            "| Iron: Ferritin 8 ng/ml (low), Iron saturation 12% |\n"
            "| CEA: 4.2 ng/ml | CRP: 8 mg/L |\n"
        ),
        (
            "| Medical history: |\n| --- |\n"
            "| Type 2 diabetes, Essential hypertension |\n"
            "| Family history: Father - colorectal cancer age 62 |\n"
        ),
    ]


def _chunks_breast(p: dict) -> list[str]:
    return [
        (
            f"--- Document: DEMO Breast 2WW Referral {p['surname']}.docx ---\n\n"
            "BREAST CANCER 2 WEEK WAIT REFERRAL"
        ),
        (
            "| Referral criteria: |  |\n| --- | --- |\n"
            "| Unexplained breast lump aged 30 or over | [X] |\n"
            "| Skin changes suggestive of breast cancer | [X] |\n"
            "| Unilateral nipple discharge aged 50+ | [ ] |\n"
        ),
        (
            f"| Patient: {p['surname']}, {p['forename']} | NHS No: {p['nhs']} |\n"
            f"| --- | --- |\n| DOB: {p['dob']} | Referral date: {p['referral_date']} |\n"
        ),
        (
            "| Reason for referral: |\n| --- |\n"
            "| [DEMO] 2 cm firm, irregular, non-tender lump in upper outer quadrant "
            "of right breast, present 4 weeks. Skin puckering noted. "
            "Concerned about possible breast malignancy. |\n"
        ),
        (
            "| Investigations: |\n| --- |\n"
            "| FBC: Hb 132 g/L, WCC 7.4, Plts 290, MCV 88 |\n"
            "| No prior mammogram in last 12 months. |\n"
        ),
    ]


def _chunks_prostate(p: dict) -> list[str]:
    return [
        (
            f"--- Document: DEMO Prostate 2WW Referral {p['surname']}.docx ---\n\n"
            "PROSTATE / UROLOGICAL CANCER 2 WEEK WAIT REFERRAL"
        ),
        (
            "| Referral criteria: |  |\n| --- | --- |\n"
            "| PSA above age-specific threshold | [X] |\n"
            "| Hard irregular prostate on DRE | [X] |\n"
            "| Unexplained haematuria aged 45+ | [ ] |\n"
        ),
        (
            f"| Patient: {p['surname']}, {p['forename']} | NHS No: {p['nhs']} |\n"
            f"| --- | --- |\n| DOB: {p['dob']} | Referral date: {p['referral_date']} |\n"
        ),
        (
            "| Reason for referral: |\n| --- |\n"
            "| [DEMO] 3-month history of urinary hesitancy, poor stream, nocturia x3. "
            "PSA 18 ng/ml (threshold 4 for age). DRE - hard irregular prostate. "
            "Concerned about suspected prostate cancer. |\n"
        ),
        (
            "| Investigations: |\n| --- |\n"
            "| PSA: 18.2 ng/ml | eGFR: 72 | Urine MCS: no infection |\n"
            "| FBC: Hb 138, WCC 7.1, Plts 230 |\n"
        ),
    ]


def _chunks_upper_gi(p: dict) -> list[str]:
    return [
        (
            f"--- Document: DEMO Upper GI 2WW Referral {p['surname']}.docx ---\n\n"
            "UPPER GI CANCER 2 WEEK WAIT REFERRAL"
        ),
        (
            "| Referral criteria: |  |\n| --- | --- |\n"
            "| Dysphagia - any age | [X] |\n"
            "| Progressive weight loss with upper abdominal pain | [X] |\n"
            "| Upper abdominal mass | [ ] |\n"
        ),
        (
            f"| Patient: {p['surname']}, {p['forename']} | NHS No: {p['nhs']} |\n"
            f"| --- | --- |\n| DOB: {p['dob']} | Referral date: {p['referral_date']} |\n"
        ),
        (
            "| Reason for referral: |\n| --- |\n"
            "| [DEMO] 6-week history of progressive dysphagia to solids, 8 kg "
            "weight loss in 2 months, epigastric pain. "
            "Concerned about oesophageal or gastric malignancy. |\n"
        ),
        (
            "| Blood results: |\n| --- |\n"
            "| FBC: Hb 102 g/L, MCV 78, WCC 9.8, Plts 510 |\n"
            "| LFT: ALP 122 (raised), Alb 30 | CRP: 64 mg/L | H. pylori: positive |\n"
        ),
    ]


def _chunks_skin(p: dict) -> list[str]:
    return [
        (
            f"--- Document: DEMO Skin Cancer 2WW Referral {p['surname']}.docx ---\n\n"
            "SKIN CANCER 2 WEEK WAIT REFERRAL (SUSPECTED MELANOMA)"
        ),
        (
            "| Referral criteria: |  |\n| --- | --- |\n"
            "| Weighted 7-point checklist score >= 3 | [X] |\n"
            "| Change in size, shape or colour of existing lesion | [X] |\n"
        ),
        (
            f"| Patient: {p['surname']}, {p['forename']} | NHS No: {p['nhs']} |\n"
            f"| --- | --- |\n| DOB: {p['dob']} | Referral date: {p['referral_date']} |\n"
        ),
        (
            "| Reason for referral: |\n| --- |\n"
            "| [DEMO] Pigmented lesion left shoulder, asymmetric with irregular "
            "border, multiple shades of brown and black, diameter 12 mm, "
            "change in size over 8 weeks. 7-point score: 4. "
            "Concerned about suspected melanoma. |\n"
        ),
    ]


def _chunks_cardiology(p: dict) -> list[str]:
    return [
        (
            f"--- Document: DEMO Cardiology Referral {p['surname']}.docx ---\n\n"
            "URGENT CARDIOLOGY OUTPATIENT REFERRAL\n\n"
            "Referral for suspected acute coronary syndrome / angina assessment."
        ),
        (
            "| Presenting complaint: |\n| --- |\n"
            "| [DEMO] Patient presents with a 3-month history of exertional chest "
            "pain radiating to the left arm, associated with breathlessness. "
            "Pain resolves with rest. ECG: ST depression during episode. "
            "Troponin negative. Risk: hypertension, type 2 diabetes, ex-smoker. |\n"
        ),
        (
            f"| Patient: {p['surname']}, {p['forename']} | NHS No: {p['nhs']} |\n"
            f"| --- | --- |\n| DOB: {p['dob']} | Referral date: {p['referral_date']} |\n"
        ),
        (
            "| Investigations: |\n| --- |\n"
            "| ECG: ST depression V4-V6 during chest pain episode |\n"
            "| Troponin I: <14 ng/L (negative) |\n"
            "| Echo: LV function mildly impaired, EF 45% |\n"
            "| Bloods: Chol 6.2, LDL 3.8, HbA1c 58 mmol/mol |\n"
        ),
        (
            "| Medical history: |\n| --- |\n"
            "| Essential hypertension (10 years), Type 2 diabetes (5 years) |\n"
            "| Ex-smoker 20 pack-years. No prior cardiac events. |\n"
            "| Medications: Ramipril 10mg, Metformin 1g bd, Aspirin 75mg |\n"
        ),
    ]


def _chunks_urology(p: dict) -> list[str]:
    return [
        (
            f"--- Document: DEMO Urology Referral {p['surname']}.docx ---\n\n"
            "URGENT UROLOGY OUTPATIENT REFERRAL\n\n"
            "Referral for visible haematuria / renal tract assessment."
        ),
        (
            "| Presenting complaint: |\n| --- |\n"
            "| [DEMO] Patient presents with a 6-week history of painless visible "
            "haematuria. Two episodes of macroscopic haematuria confirmed. "
            "No urinary tract infection on MSU. No anticoagulant use. "
            "CT KUB requested - awaiting result. |\n"
        ),
        (
            f"| Patient: {p['surname']}, {p['forename']} | NHS No: {p['nhs']} |\n"
            f"| --- | --- |\n| DOB: {p['dob']} | Referral date: {p['referral_date']} |\n"
        ),
        (
            "| Investigations: |\n| --- |\n"
            "| MSU: No infection | Urine cytology: atypical cells seen |\n"
            "| FBC: Hb 129 g/L, WCC 7.2, Plts 265 |\n"
            "| eGFR: 68 mL/min | PSA: 2.1 ng/ml |\n"
        ),
        (
            "| Medical history: |\n| --- |\n"
            "| Recurrent UTIs (3 in past year), Hypertension |\n"
            "| Medications: Amlodipine 5mg, Trimethoprim 200mg PRN |\n"
            "| Allergies: None known |\n"
        ),
    ]


def _chunks_gastroenterology(p: dict) -> list[str]:
    return [
        (
            f"--- Document: DEMO Gastroenterology Referral {p['surname']}.docx ---\n\n"
            "URGENT GASTROENTEROLOGY OUTPATIENT REFERRAL\n\n"
            "Referral for investigation of suspected inflammatory bowel disease."
        ),
        (
            "| Presenting complaint: |\n| --- |\n"
            "| [DEMO] Patient has a 4-month history of crampy abdominal pain, "
            "intermittent diarrhoea (5-6 times/day), rectal urgency, and "
            "unintentional weight loss of 5 kg. Two episodes of passing blood "
            "mixed with stool. Calprotectin markedly elevated. |\n"
        ),
        (
            f"| Patient: {p['surname']}, {p['forename']} | NHS No: {p['nhs']} |\n"
            f"| --- | --- |\n| DOB: {p['dob']} | Referral date: {p['referral_date']} |\n"
        ),
        (
            "| Investigations: |\n| --- |\n"
            "| Faecal calprotectin: 820 mcg/g (markedly elevated) |\n"
            "| CRP: 42 mg/L | ESR: 55 mm/hr |\n"
            "| FBC: Hb 104 g/L, WCC 12.1, Plts 520 | MCV 78 |\n"
            "| Albumin: 28 g/L | FIT: 35 mcg Hb/g |\n"
        ),
        (
            "| Medical history: |\n| --- |\n"
            "| Anxiety (2 years), No prior GI diagnosis |\n"
            "| Family history: Mother - Crohn's disease |\n"
            "| Medications: Sertraline 50mg od |\n"
        ),
    ]


def _chunks_rheumatology(p: dict) -> list[str]:
    return [
        (
            f"--- Document: DEMO Rheumatology Referral {p['surname']}.docx ---\n\n"
            "URGENT RHEUMATOLOGY OUTPATIENT REFERRAL\n\n"
            "Referral for suspected early inflammatory arthritis."
        ),
        (
            "| Presenting complaint: |\n| --- |\n"
            "| [DEMO] 3-month history of symmetrical small joint swelling and "
            "pain in hands and wrists, with morning stiffness lasting over 1 hour. "
            "Grip strength reduced bilaterally. Positive anti-CCP antibody. "
            "Rheumatoid factor positive. |\n"
        ),
        (
            f"| Patient: {p['surname']}, {p['forename']} | NHS No: {p['nhs']} |\n"
            f"| --- | --- |\n| DOB: {p['dob']} | Referral date: {p['referral_date']} |\n"
        ),
        (
            "| Investigations: |\n| --- |\n"
            "| Anti-CCP: 140 U/ml (strongly positive) |\n"
            "| Rheumatoid factor: 64 IU/ml (positive) |\n"
            "| CRP: 38 mg/L | ESR: 62 mm/hr |\n"
            "| X-ray hands: periarticular osteopenia, no erosions yet |\n"
        ),
        (
            "| Medical history: |\n| --- |\n"
            "| No prior joint disease. Thyroid disorder (hypothyroid). |\n"
            "| Medications: Levothyroxine 100mcg, Naproxen 500mg bd PRN |\n"
            "| Family history: Sister - rheumatoid arthritis |\n"
        ),
    ]


def _chunks_neurology(p: dict) -> list[str]:
    return [
        (
            f"--- Document: DEMO Neurology Referral {p['surname']}.docx ---\n\n"
            "URGENT NEUROLOGY OUTPATIENT REFERRAL\n\n"
            "Referral for investigation of TIA / early stroke."
        ),
        (
            "| Presenting complaint: |\n| --- |\n"
            "| [DEMO] Patient experienced sudden onset of right arm weakness and "
            "slurred speech lasting 20 minutes then fully resolving. ABCD2 score 5 "
            "(high risk). CT head: no acute changes. NIHSS 0 on review. |\n"
        ),
        (
            f"| Patient: {p['surname']}, {p['forename']} | NHS No: {p['nhs']} |\n"
            f"| --- | --- |\n| DOB: {p['dob']} | Referral date: {p['referral_date']} |\n"
        ),
        (
            "| Investigations: |\n| --- |\n"
            "| CT head: no acute infarct or haemorrhage |\n"
            "| Carotid Doppler: 40% stenosis right ICA |\n"
            "| ECG: sinus rhythm | Echo: no thrombus |\n"
            "| Cholesterol: 5.8 | HbA1c: 48 mmol/mol |\n"
        ),
        (
            "| Medical history: |\n| --- |\n"
            "| Hypertension (poorly controlled), Atrial fibrillation |\n"
            "| Medications: Amlodipine 10mg, Apixaban 5mg bd, Atorvastatin 40mg |\n"
        ),
    ]


def _chunks_respiratory(p: dict) -> list[str]:
    return [
        (
            f"--- Document: DEMO Respiratory Referral {p['surname']}.docx ---\n\n"
            "URGENT RESPIRATORY OUTPATIENT REFERRAL\n\n"
            "Referral for investigation of progressive breathlessness / possible COPD."
        ),
        (
            "| Presenting complaint: |\n| --- |\n"
            "| [DEMO] Patient presents with progressive breathlessness on exertion "
            "over 6 months, persistent productive cough, and two infective "
            "exacerbations requiring antibiotics in the past year. "
            "Spirometry: FEV1/FVC 0.64, FEV1 58% predicted. |\n"
        ),
        (
            f"| Patient: {p['surname']}, {p['forename']} | NHS No: {p['nhs']} |\n"
            f"| --- | --- |\n| DOB: {p['dob']} | Referral date: {p['referral_date']} |\n"
        ),
        (
            "| Investigations: |\n| --- |\n"
            "| Spirometry: FEV1 1.4L (58%), FVC 2.2L, FEV1/FVC 0.64 |\n"
            "| CXR: hyperinflation, no consolidation |\n"
            "| Sats: 94% on air at rest |\n"
            "| FBC: Hb 162 g/L (polycythaemia), Plts 188 |\n"
        ),
        (
            "| Medical history: |\n| --- |\n"
            "| Ex-smoker 40 pack-years. Alpha-1 antitrypsin deficiency known. |\n"
            "| Medications: Salbutamol, Tiotropium, Prednisolone 5mg |\n"
        ),
    ]


def _chunks_endocrinology(p: dict) -> list[str]:
    return [
        (
            f"--- Document: DEMO Endocrinology Referral {p['surname']}.docx ---\n\n"
            "URGENT ENDOCRINOLOGY OUTPATIENT REFERRAL\n\n"
            "Referral for newly diagnosed type 2 diabetes with poor control."
        ),
        (
            "| Presenting complaint: |\n| --- |\n"
            "| [DEMO] Patient presents with polyuria, polydipsia, and 8 kg weight "
            "loss over 3 months. HbA1c 96 mmol/mol on two occasions. "
            "Random glucose 18.4 mmol/L. Urine dipstick: glycosuria 3+, "
            "no ketones. |\n"
        ),
        (
            f"| Patient: {p['surname']}, {p['forename']} | NHS No: {p['nhs']} |\n"
            f"| --- | --- |\n| DOB: {p['dob']} | Referral date: {p['referral_date']} |\n"
        ),
        (
            "| Investigations: |\n| --- |\n"
            "| HbA1c: 96 mmol/mol (x2 confirmed) |\n"
            "| Random glucose: 18.4 mmol/L |\n"
            "| Urine ACR: 42 mg/mmol (raised) |\n"
            "| eGFR: 62 mL/min | Chol: 7.1 | TSH: 3.2 |\n"
        ),
        (
            "| Medical history: |\n| --- |\n"
            "| Thyroid disorder (hypothyroid), Hypertension |\n"
            "| Medications: Levothyroxine 75mcg, Lisinopril 10mg |\n"
            "| Family history: Mother - type 2 diabetes |\n"
        ),
    ]


def _chunks_haematology(p: dict) -> list[str]:
    return [
        (
            f"--- Document: DEMO Haematology Referral {p['surname']}.docx ---\n\n"
            "URGENT HAEMATOLOGY OUTPATIENT REFERRAL\n\n"
            "Referral for investigation of unexplained lymphadenopathy and anaemia."
        ),
        (
            "| Presenting complaint: |\n| --- |\n"
            "| [DEMO] Patient presents with progressive fatigue, night sweats, "
            "and 6 kg unintentional weight loss over 2 months. "
            "Multiple enlarged cervical lymph nodes palpable (largest 3 cm). "
            "FBC shows pancytopenia. |\n"
        ),
        (
            f"| Patient: {p['surname']}, {p['forename']} | NHS No: {p['nhs']} |\n"
            f"| --- | --- |\n| DOB: {p['dob']} | Referral date: {p['referral_date']} |\n"
        ),
        (
            "| Investigations: |\n| --- |\n"
            "| FBC: Hb 92 g/L, WCC 2.8 (low), Plts 88 (low), Lymphocytes 1.1 |\n"
            "| LDH: 480 IU/L (raised) | Beta-2 microglobulin: 4.2 mg/L |\n"
            "| CT neck/chest/abdomen: mediastinal and inguinal LAD |\n"
            "| Blood film: atypical lymphocytes, no blast cells |\n"
        ),
        (
            "| Medical history: |\n| --- |\n"
            "| No prior haematological diagnosis. |\n"
            "| Medications: None regular. |\n"
            "| Allergies: Penicillin (rash) |\n"
        ),
    ]


# ---------------------------------------------------------------------------
# Pathway assignment by patient index
# ---------------------------------------------------------------------------

# Cancer 2WW pathways cycle for patients 001-035
_CANCER_PATHWAYS = ["lung", "colorectal", "breast", "prostate", "upper_gi", "skin"]

# Non-cancer specialties for patients 036-060
_SPECIALIST_PATHWAYS = [
    "cardiology", "urology", "gastroenterology", "rheumatology",
    "neurology", "respiratory", "endocrinology",
]

# Open/in-progress (061-070): mix of urgent 2WW + specialist
_MIXED_PATHWAYS = [
    "lung", "cardiology", "colorectal", "urology",
    "gastroenterology", "breast", "rheumatology", "neurology",
    "respiratory", "endocrinology",
]

# Blood signal cohort (071-080): haematology + cancer
_BLOOD_PATHWAYS = [
    "haematology", "lung", "haematology", "colorectal",
    "haematology", "breast", "haematology", "upper_gi",
    "haematology", "haematology",
]

_CHUNK_FACTORIES: dict[str, Any] = {
    "lung": _chunks_lung,
    "colorectal": _chunks_colorectal,
    "breast": _chunks_breast,
    "prostate": _chunks_prostate,
    "upper_gi": _chunks_upper_gi,
    "skin": _chunks_skin,
    "cardiology": _chunks_cardiology,
    "urology": _chunks_urology,
    "gastroenterology": _chunks_gastroenterology,
    "rheumatology": _chunks_rheumatology,
    "neurology": _chunks_neurology,
    "respiratory": _chunks_respiratory,
    "endocrinology": _chunks_endocrinology,
    "haematology": _chunks_haematology,
}

_SPECIALTY_LABELS: dict[str, tuple[str, str]] = {
    "lung": ("2WW", "TWO_WEEK_WAIT"),
    "colorectal": ("2WW", "TWO_WEEK_WAIT"),
    "breast": ("2WW", "TWO_WEEK_WAIT"),
    "prostate": ("2WW", "TWO_WEEK_WAIT"),
    "upper_gi": ("2WW", "TWO_WEEK_WAIT"),
    "skin": ("2WW", "TWO_WEEK_WAIT"),
    "cardiology": ("Cardiology", "URGENT"),
    "urology": ("Urology", "URGENT"),
    "gastroenterology": ("Gastroenterology", "URGENT"),
    "rheumatology": ("Rheumatology", "ROUTINE"),
    "neurology": ("Neurology", "URGENT"),
    "respiratory": ("Respiratory", "ROUTINE"),
    "endocrinology": ("Endocrinology", "ROUTINE"),
    "haematology": ("Haematology", "URGENT"),
}


def _pathway_for(idx: int) -> str:
    if idx <= 35:
        return _CANCER_PATHWAYS[(idx - 1) % len(_CANCER_PATHWAYS)]
    if idx <= 60:
        return _SPECIALIST_PATHWAYS[(idx - 36) % len(_SPECIALIST_PATHWAYS)]
    if idx <= 70:
        return _MIXED_PATHWAYS[(idx - 61) % len(_MIXED_PATHWAYS)]
    return _BLOOD_PATHWAYS[(idx - 71) % len(_BLOOD_PATHWAYS)]


# ---------------------------------------------------------------------------
# ID helpers
# ---------------------------------------------------------------------------

def _rr_id(idx: int) -> str:
    return f"demo-rr-{idx:03d}"


def _dr_id(idx: int) -> str:
    return f"demo-rr-{idx:03d}:leo-referral-bundle"


def _make_chunk_id(dr: str, ordinal: int, sha: str) -> str:
    raw = f"{dr}:{ordinal}:{sha}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def _chunk_sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Neo4j write helpers
# ---------------------------------------------------------------------------

def _seed_referral_request(
    client: PatientGraphClient,
    idx: int,
    specialty: str,
    priority: str,
    ref_date: str,
) -> None:
    rr_id = _rr_id(idx)
    client.run(
        "MERGE (rr:ReferralRequest {id: $id}) "
        "ON CREATE SET rr.specialty = $specialty, "
        "  rr.priority = $priority, "
        "  rr.status = 'active', "
        "  rr.source = 'demo', "
        "  rr.created_at = datetime($ref_date)",
        id=rr_id, specialty=specialty, priority=priority, ref_date=ref_date,
    )
    client.run(
        "MATCH (rr:ReferralRequest {id: $rr_id}), (p:Patient {id: $pid}) "
        "MERGE (rr)-[:FOR_PATIENT]->(p)",
        rr_id=rr_id, pid=f"demo-patient-{idx:03d}",
    )
    client.run(
        "MATCH (rr:ReferralRequest {id: $rr_id}), (s:Service {id: $sid}) "
        "MERGE (w:Workflow {id: $wf_id}) "
        "ON CREATE SET w.source = 'demo', w.created_at = datetime() "
        "MERGE (rr)-[:IN_WORKFLOW]->(w)-[:FOR_SERVICE]->(s)",
        rr_id=rr_id, sid=DEMO_SERVICE_ID, wf_id=f"demo-wf-{idx:03d}",
    )


def _seed_document_reference(
    client: PatientGraphClient,
    idx: int,
    pathway: str,
    ref_date: str,
) -> str:
    dr = _dr_id(idx)
    specialty_label, _ = _SPECIALTY_LABELS[pathway]
    title = f"DEMO {pathway.replace('_', ' ').title()} Referral"
    client.run(
        "MERGE (dr:DocumentReference {id: $id}) "
        "ON CREATE SET dr.title = $title, "
        "  dr.type = $rtype, "
        "  dr.category = 'referral_letter', "
        "  dr.date = $ref_date, "
        "  dr.source = 'demo', "
        "  dr.created_at = datetime()",
        id=dr, title=title,
        rtype="2WW-referral" if specialty_label == "2WW" else "outpatient-referral",
        ref_date=ref_date,
    )
    client.run(
        "MATCH (rr:ReferralRequest {id: $rr_id}), (dr:DocumentReference {id: $dr_id}) "
        "MERGE (rr)-[:HAS_DOCUMENT]->(dr) "
        "MERGE (dr)-[:DERIVED_FROM]->(rr)",
        rr_id=_rr_id(idx), dr_id=dr,
    )
    client.run(
        "MATCH (p:Patient {id: $pid}), (dr:DocumentReference {id: $dr_id}) "
        "MERGE (p)-[:HAS_DOCUMENT_REFERENCE]->(dr)",
        pid=f"demo-patient-{idx:03d}", dr_id=dr,
    )
    return dr


def _seed_chunks(
    client: PatientGraphClient,
    dr: str,
    chunk_texts: list[str],
) -> list[str]:
    chunk_ids: list[str] = []
    char_cursor = 0
    for ordinal, text in enumerate(chunk_texts, start=1):
        sha = _chunk_sha(text)
        cid = _make_chunk_id(dr, ordinal, sha)
        char_end = char_cursor + len(text)
        client.run(
            "MATCH (dr:DocumentReference {id: $dr_id}) "
            "MERGE (c:Chunk {id: $cid}) "
            "SET c.document_reference_id = $dr_id, "
            "    c.text = $text, c.sha256 = $sha, "
            "    c.char_start = $cs, c.char_end = $ce, "
            "    c.ordinal = $ordinal, c.source = 'demo', "
            "    c.updated_at = datetime(), "
            "    c.created_at = coalesce(c.created_at, datetime()) "
            "MERGE (dr)-[r:HAS_CHUNK]->(c) "
            "SET r.ordinal = $ordinal, r.char_start = $cs, r.char_end = $ce",
            dr_id=dr, cid=cid, text=text, sha=sha,
            cs=char_cursor, ce=char_end, ordinal=ordinal,
        )
        chunk_ids.append(cid)
        char_cursor = char_end + 1
    return chunk_ids


# ---------------------------------------------------------------------------
# Guard / teardown
# ---------------------------------------------------------------------------

def _already_seeded(client: PatientGraphClient) -> bool:
    rows = client.run(
        "MATCH (rr:ReferralRequest {id: $id}) RETURN count(rr) AS n",
        id=_rr_id(1),
    )
    return bool(rows and rows[0].get("n", 0) > 0)


def _teardown(client: PatientGraphClient) -> None:
    client.run(
        "MATCH (n {source: 'demo'}) "
        "WHERE n:ReferralRequest OR n:DocumentReference "
        "   OR n:Chunk OR n:Workflow "
        "DETACH DELETE n"
    )
    # Also remove demo-seeded SNOMED nodes that aren't used elsewhere
    client.run(
        "MATCH (n {source: 'demo'}) "
        "WHERE n:Clinical_finding OR n:Disorder OR n:Observable_entity "
        "DETACH DELETE n"
    )
    print("  [OK] Demo referral data removed")


# ---------------------------------------------------------------------------
# Main seed loop
# ---------------------------------------------------------------------------

def _seed_referrals(client: PatientGraphClient) -> list[dict[str, Any]]:
    print(f"\n{'='*60}")
    print(f"SEEDING {_N_REFERRALS} DEMO REFERRALS")
    print(f"{'='*60}")
    records: list[dict[str, Any]] = []
    for idx in range(1, _N_REFERRALS + 1):
        pathway = _pathway_for(idx)
        specialty_label, priority = _SPECIALTY_LABELS[pathway]
        p = _person(idx)
        chunks_fn = _CHUNK_FACTORIES[pathway]
        chunks_text = chunks_fn(p)
        _seed_referral_request(client, idx, specialty_label, priority, p["referral_date"])
        dr = _seed_document_reference(client, idx, pathway, p["referral_date"])
        chunk_ids = _seed_chunks(client, dr, chunks_text)
        records.append(
            {
                "patient_id": f"demo-patient-{idx:03d}",
                "rr_id": _rr_id(idx),
                "dr_id": dr,
                "pathway": pathway,
                "chunk_ids": chunk_ids,
            }
        )
        print(
            f"  [OK] demo-patient-{idx:03d} -> {pathway:<20} "
            f"({len(chunks_text)} chunks)"
        )
    print(f"\n  Seeded {len(records)} referral bundles across "
          f"{len(set(r['pathway'] for r in records))} pathways")
    return records


# ---------------------------------------------------------------------------
# Direct coding (bypasses the LLM - for local dev without AWS Bedrock)
# ---------------------------------------------------------------------------

def _semantic_tag_to_label(tag: str) -> str:
    return {
        "finding": "Clinical_finding",
        "disorder": "Disorder",
        "observable_entity": "Observable_entity",
        "procedure": "Procedure",
    }.get(tag, "Clinical_finding")


def _seed_documents_links(
    client: PatientGraphClient,
    rec: dict,
) -> None:
    """Write pre-coded DOCUMENTS links from the referral chunk to SNOMED concepts."""
    codes = _PATHWAY_CODES.get(rec["pathway"], [])
    if not codes:
        return

    chunk_ids = rec["chunk_ids"]
    evidence_chunk_id = chunk_ids[3] if len(chunk_ids) > 3 else chunk_ids[0]
    run_id = f"demo-direct-code-{rec['rr_id']}"

    for concept_id, term, semantic_tag, assertion in codes:
        node_label = _semantic_tag_to_label(semantic_tag)
        node_id = f"demo-snomed-{concept_id}"
        client.run(
            f"MERGE (s:{node_label} {{id: $nid}}) "
            "ON CREATE SET s.conceptId = $cid, s.name = $term, "
            "  s.semanticTag = $tag, s.source = 'demo', "
            "  s.created_at = datetime()",
            nid=node_id, cid=concept_id, term=term, tag=semantic_tag,
        )
        client.run(
            "MATCH (c:Chunk {id: $chunk_id}), (s {id: $nid}) "
            "MERGE (c)-[d:DOCUMENTS {conceptId: $cid}]->(s) "
            "ON CREATE SET d.evidence = $term, "
            "  d.confidence = 0.9, d.context = $assertion, "
            "  d.domain = 'referral', d.source = 'demo', "
            "  d.run_id = $run_id, d.model_name = 'demo-seed', "
            "  d.coded_at = datetime()",
            chunk_id=evidence_chunk_id, nid=node_id, cid=concept_id,
            term=term, assertion=assertion, run_id=run_id,
        )
        if assertion in ("present", "suspected"):
            client.run(
                "MATCH (p:Patient {id: $pid}), (s {id: $nid}) "
                "MERGE (p)-[:HAS_FINDING {domain: 'referral', "
                "  source: 'demo', conceptId: $cid}]->(s)",
                pid=rec["patient_id"], nid=node_id, cid=concept_id,
            )


def _run_direct_code(
    client: PatientGraphClient,
    records: list[dict],
) -> None:
    print(f"\n{'='*60}")
    print("DIRECT-CODING DEMO REFERRALS (no LLM)")
    print(f"{'='*60}")
    for rec in records:
        _seed_documents_links(client, rec)
        codes = _PATHWAY_CODES.get(rec["pathway"], [])
        print(
            f"  [CODE] {rec['patient_id']} ({rec['pathway']:<20}) "
            f"-> {len(codes)} SNOMED codes"
        )


# ---------------------------------------------------------------------------
# Full LLM pipeline trigger (requires AWS Bedrock + Redis)
# ---------------------------------------------------------------------------

async def _run_pipeline(records: list[dict[str, Any]]) -> None:
    from libs.keyvault.loader import load_keyvault_secrets
    from services.pipeline_worker.app.services.referral_durable_steps import (
        REFERRAL_STEPS,
        handle_referral_durable_message,
    )
    load_keyvault_secrets()
    print(f"\n{'='*60}")
    print("RUNNING PIPELINE FOR DEMO REFERRALS")
    print(f"{'='*60}")
    for rec in records:
        initial: dict[str, Any] = {
            "event_type": "referral-received",
            "plan_definition_id": _REFERRAL_PLAN_ID,
            "patient_id": rec["patient_id"],
            "encounter_id": rec["rr_id"].replace("demo-rr-", "demo-enc-") + "-referral",
            "referral_id": rec["rr_id"],
            "document_reference_id": rec["dr_id"],
            "chunk_ids": rec["chunk_ids"],
            "text_segmentation_mode": "document_chunks",
            "run_id": f"demo-run-{rec['rr_id']}",
            "source_node_type": "ReferralRequest",
            "source_node_id": rec["rr_id"],
            "mode": "referral_assessment",
            "output_target": "patient_graph",
            "guideline_scope_type": "guideline",
            "guideline_scope_id": _GUIDELINE_ID,
            "guideline_id": _GUIDELINE_ID,
            "completeness_domain": "cancer_referrals",
            "completeness_subdomain": rec["pathway"],
            "context": {"referral_id": rec["rr_id"]},
            "errors": [],
        }
        passed, failed_step = 0, None
        for definition in REFERRAL_STEPS:
            body = {
                **initial,
                "event_type": definition.event_type,
                "workflow_id": _REFERRAL_PLAN_ID,
                "step_id": definition.step_id,
                "context": dict(initial),
            }
            try:
                result = await handle_referral_durable_message(
                    body, bus=None, publish_progress=None,
                )
                initial.update(result.output or {})
                if result.status != "completed":
                    failed_step = definition.step_id
                    break
                passed += 1
            except Exception as exc:  # noqa: BLE001
                failed_step = f"{definition.step_id}: {exc}"
                break
        status = "completed" if not failed_step else f"failed at {failed_step}"
        marker = "[OK]" if not failed_step else "[!!]"
        print(
            f"  {marker} {rec['patient_id']} ({rec['pathway']}) "
            f"-> {passed} steps - {status}"
        )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    force = "--force" in sys.argv
    teardown_only = "--teardown" in sys.argv
    run_pipeline = "--run-pipeline" in sys.argv
    direct_code = "--direct-code" in sys.argv

    client = PatientGraphClient()
    try:
        if teardown_only:
            print("Removing demo referral data...")
            _teardown(client)
            return

        if _already_seeded(client):
            if not force:
                print(
                    f"Demo referrals already seeded ({_rr_id(1)}). "
                    "Use --force to re-seed or --teardown to remove."
                )
                return
            print("--force: removing existing demo referral data...")
            _teardown(client)

        records = _seed_referrals(client)

        if direct_code:
            _run_direct_code(client, records)
    finally:
        client.close()

    if run_pipeline:
        asyncio.run(_run_pipeline(records))
        print(f"\n{'='*60}")
        print("DONE - pipeline run complete")
        print(f"{'='*60}\n")
    else:
        suffix = " and direct-coded" if direct_code else ""
        print(f"\n{'='*60}")
        print(f"DONE - {_N_REFERRALS} referral bundles created{suffix}")
        if not direct_code:
            print(
                "Re-run with --direct-code to write pre-coded SNOMED links "
                "(no AWS Bedrock required)."
            )
        print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
