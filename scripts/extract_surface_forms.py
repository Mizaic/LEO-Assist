"""Build normalized, de-identified clinical coding spans from GP encounters.

Output format is strict JSONL:
{
  "date": "YYYY-MM",
  "sentence": "...",
  "entities": [
    {
      "text": "...",
      "type": "...",
      "snomed_semantic_tag": "...",
      "clinical_status": "current|historic|planned",
      "attributes": {},
      "temporal": {
        "onset": null,
        "duration": null,
        "offset": null,
        "pattern": null,
        "recurrence": null,
        "context": "encounter|past episode|care plan"
      },
      "negation": false,
      "uncertainty": false
    }
  ]
}
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from statistics import mean
from typing import Any

from jsonschema import Draft7Validator

ROOT = Path(__file__).resolve().parents[1]
DATA_TRAINING_DIR = ROOT / "services" / "terminology" / "data" / "training"


def resolve_paths(patient_id: str) -> tuple[Path, Path, Path, Path]:
    raw_path = DATA_TRAINING_DIR / f"raw_encounters_{patient_id}.json"
    out_path = DATA_TRAINING_DIR / f"surface_forms_{patient_id}.jsonl"
    qa_path = DATA_TRAINING_DIR / f"surface_forms_{patient_id}.qa.json"
    validation_path = (
        DATA_TRAINING_DIR / f"surface_forms_{patient_id}.validation_report.json"
    )
    return raw_path, out_path, qa_path, validation_path


NAME_PATTERN = re.compile(
    r"\b[A-Z][A-Z\-']+,\s*[A-Z][a-zA-Z\-']+\s*\((Mr|Mrs|Ms|Miss|Dr|Prof)\)"
)
HONORIFIC_NAME_PATTERN = re.compile(
    r"\b(?:Mr|Mrs|Ms|Miss|Dr|Prof)\s+[A-Z][a-zA-Z\-']+\b"
)
CONSULTANT_PATTERN = re.compile(r"\bConsultant:\s*[A-Z][a-zA-Z\-']+\s+[A-Z]\b")
EMAIL_PATTERN = re.compile(r"\b[\w.\-+]+@[\w.\-]+\.\w+\b", re.IGNORECASE)
PHONE_PATTERN = re.compile(r"\b(?:\+44|0)\d[\d\s\-]{8,}\d\b")
NHS_PATTERN = re.compile(r"\b\d{3}\s?\d{3}\s?\d{4}\b")
INLINE_DATE_PATTERN = re.compile(
    r"\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b|\b\d{1,2}\s+[A-Za-z]{3,9}\s+\d{2,4}\b"
)
DOTTED_DATE_PATTERN = re.compile(r"\b\d{1,2}\.\d{1,2}\.\d{2,4}\b")
UUID_PATTERN = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB]"
    r"[0-9a-fA-F]{3}-[0-9a-fA-F]{12}\b"
)
YM_PATTERN = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
READ_CODE_PATTERN = re.compile(r"(.{3,120}?)\s*\(([A-Za-z0-9.]{3,8})\)")

SECTION_PREFIXES = (
    "Problem:",
    "History:",
    "Examination:",
    "Comment:",
    "Medication:",
    "Additional:",
    "Social:",
)

TYPE_TO_TAG = {
    "symptom": "finding",
    "diagnosis": "disorder",
    "vital_sign": "observable entity",
    "lab_result": "observable entity",
    "exposure": "situation",
    "social_history": "situation",
    "medication": "substance",
    "intervention": "procedure",
    "advice_event": "situation",
    "referral": "procedure",
    "administrative_event": "record artifact",
    "document_event": "record artifact",
}

ALLOWED_STATUS = {"current", "historic", "planned"}
SEMANTIC_ALLOWED = {
    "symptom": {"finding"},
    "diagnosis": {"disorder"},
    "vital_sign": {"observable entity"},
    "lab_result": {"observable entity"},
    "exposure": {"situation"},
    "social_history": {"situation"},
    "medication": {"substance"},
    "intervention": {"procedure"},
    "advice_event": {"situation"},
    "referral": {"procedure"},
    "administrative_event": {"record artifact"},
    "document_event": {"record artifact"},
}

ALLOWED_ATTRIBUTES = {
    "diagnosis": {"laterality", "severity", "episode_type"},
    "symptom": {"severity", "duration"},
    "intervention": {"dose_number", "laterality", "route"},
    "advice_event": set(),
    "medication": {"dose", "frequency", "route"},
    "vital_sign": {"systolic", "diastolic", "unit", "value"},
    "lab_result": {"value", "unit"},
    "referral": {"specialty", "urgency"},
    "exposure": {"location", "timing"},
    "social_history": {"quantity", "duration"},
    "administrative_event": set(),
    "document_event": set(),
}

READ_CODE_STOPWORDS = {
    "first",
    "new",
    "episode",
    "new episode",
    "mrs",
    "mr",
    "dr",
    "prof",
    "miss",
    "ms",
    "triple",
    "gms",
}

ADMIN_NOISE_CUES = (
    "authorised by",
    "attachment reference",
    "records at",
    "unknown staff member",
    "care started at",
    "duration:",
    "report summary",
    "clinical history",
    "test name",
    "tried to call you",
    "could not get through",
    "no response",
    "failed encounter",
    "claim abandoned",
    "protocol red flags",
    "c/indications",
    "additional scr dataset",
    "copi regulations",
    "visit the gov.uk",
    "nhs websites for information",
    "nhs website",
    "gov.uk",
    "caution -",
    "check patient",
    "same name",
    "contact patient",
    "prescription issue",
    "notifiable disease notification",
    "registration fee paid",
    "new registration check",
    "health promotion clinic",
    "type of request",
    "gppaq",
    "health check programme",
    "patient telephone number",
    "telephone encounter",
    "patient file attachment",
    "resolution stop smoking service",
    "med3 issued",
    "doctor's statement",
    "informed consent for procedure",
    "main spoken language english",
    "past medical history",
)

NORMALIZATION_MAP = {
    "sob": "shortness of breath",
    "epistaxis": "epistaxis",
    "nose bleeds": "epistaxis",
    "nosebleeds": "epistaxis",
}

UNCERTAINTY_TOKENS = ("?", "likely", "possible", "probable")
ADMIN_PHRASE_TRIGGERS = (
    "letter",
    "notes summary",
    "administration",
    "informing patient",
    "attachment",
    "imported notes",
    "accountable general practitioner",
    "claim abandoned",
    "protocol red flags",
    "c/indications",
    "main spoken language",
    "contact preference",
    "preference",
    "additional scr dataset",
    "copi regulations",
    "contact patient",
    "notifiable disease notification",
    "registration fee paid",
    "new registration check",
    "health promotion clinic",
    "type of request",
    "gppaq",
    "health check programme",
    "patient telephone number",
    "telephone encounter",
    "patient file attachment",
    "resolution stop smoking service",
    "med3 issued",
    "doctor's statement",
    "informed consent for procedure",
    "main spoken language english",
)

SAFETY_NET_SENTENCES = re.compile(
    r"^(?:if\s+(?:no\s+(?:better|improvement|change|response)|symptoms?\s+(?:worsen|persist|return))"
    r"|(?:symptoms?\s+worsen|to\s+return\s+if|return\s+if)"
    r"|when\s+to\s+seek\s+(?:medical|further)\s+(?:help|advice|attention)"
    r"|(?:safety\s+net(?:ting)?|worsening\s+advice)"
    r"|seek\s+(?:medical\s+)?(?:help|advice|attention)\s+if"
    r"|(?:to\s+)?return\s+(?:to\s+(?:surgery|gp)|if\s+(?:not|no)\s+(?:better|improving))"
    r"|(?:further\s+)?review\s+if\s+(?:no\s+(?:better|improvement)|symptoms?\s+(?:worsen|persist)))"
    r"(?:\s|[.,])*$",
    re.IGNORECASE,
)

DERIVED_SPAN_ALLOWLIST = {
    "blood pressure",
    "pulse rate",
    "oxygen saturation",
    "sars-cov-2 test result",
    "sars-cov-2 test result negative",
    "hernia repair",
    "travel advice",
    "rabies vaccination",
    "smoking cessation advice",
}

ROW_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["date", "sentence", "entities"],
    "properties": {
        "date": {"type": "string", "pattern": r"^\d{4}-(0[1-9]|1[0-2])$"},
        "sentence": {"type": "string", "minLength": 1},
        "entities": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "text",
                    "type",
                    "snomed_semantic_tag",
                    "clinical_status",
                    "attributes",
                    "temporal",
                    "negation",
                    "uncertainty",
                ],
                "properties": {
                    "text": {"type": "string", "minLength": 1},
                    "type": {"type": "string"},
                    "snomed_semantic_tag": {"type": "string"},
                    "clinical_status": {"type": "string"},
                    "attributes": {"type": "object"},
                    "temporal": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": [
                            "onset",
                            "duration",
                            "offset",
                            "pattern",
                            "recurrence",
                            "context",
                        ],
                        "properties": {
                            "onset": {"type": ["string", "null"]},
                            "duration": {"type": ["string", "null"]},
                            "offset": {"type": ["string", "null"]},
                            "pattern": {"type": ["string", "null"]},
                            "recurrence": {"type": ["string", "null"]},
                            "context": {"type": "string"},
                        },
                    },
                    "negation": {"type": "boolean"},
                    "uncertainty": {"type": "boolean"},
                },
            },
        },
    },
}


def deid_month(date_text: str | None, encounter_id: str) -> str:
    """Deterministically map source dates into 2024-2025 month range."""
    month = 1
    if date_text:
        try:
            dt = datetime.strptime(date_text, "%Y-%m-%d")
            month = dt.month
        except ValueError:
            month = 1
    year = 2024 + (int(hashlib.sha256(encounter_id.encode()).hexdigest()[:2], 16) % 2)
    return f"{year}-{month:02d}"


def deidentify_text(text: str) -> str:
    out = text
    out = NAME_PATTERN.sub("[PERSON]", out)
    out = HONORIFIC_NAME_PATTERN.sub("[PERSON]", out)
    out = CONSULTANT_PATTERN.sub("Consultant: [PERSON]", out)
    out = EMAIL_PATTERN.sub("[EMAIL]", out)
    out = PHONE_PATTERN.sub("[PHONE]", out)
    out = NHS_PATTERN.sub("[NHS_NUMBER]", out)
    out = INLINE_DATE_PATTERN.sub("[DATE]", out)
    out = DOTTED_DATE_PATTERN.sub("[DATE]", out)
    out = re.sub(
        r"\bWoodbrook Medical Centre\b", "[PRACTICE]", out, flags=re.IGNORECASE
    )
    out = re.sub(r"\bHospital Outpatient\b", "[CARE_SITE]", out, flags=re.IGNORECASE)
    return out


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip(" -,\t")


def _iter_sentences(text: str) -> list[str]:
    lines = [_clean(ln) for ln in text.splitlines() if _clean(ln)]
    out: list[str] = []
    for line in lines:
        if line == "[PERSON]" or any(cue in line.lower() for cue in ADMIN_NOISE_CUES):
            continue
        payload = (
            line.split(":", 1)[1].strip()
            if any(line.startswith(prefix) for prefix in SECTION_PREFIXES)
            else line
        )
        for part in re.split(r"[.;]\s+|\s-\s", payload):
            sent = _clean(part)
            if sent and "[PRACTICE]" not in sent and "[PERSON]" not in sent:
                out.append(sent)
    return out


ACRONYM_PRESERVE = {
    "bcg",
    "sars",
    "ecg",
    "bmi",
    "hba1c",
    "inr",
    "fbc",
    "crp",
    "esr",
    "tft",
    "lft",
    "u&e",
    "gfr",
    "egfr",
    "hiv",
    "mmr",
    "dtap",
    "ipv",
    "hpv",
    "pcr",
    "ct",
    "mri",
}


def _normalize_text(text: str) -> str:
    low = text.lower()
    for k, v in NORMALIZATION_MAP.items():
        if k in low:
            return v
    tokens = text.split()
    out_tokens = []
    for tok in tokens:
        if tok.lower().rstrip(".,;:") in ACRONYM_PRESERVE:
            out_tokens.append(tok.upper().rstrip(".,;:"))
        else:
            out_tokens.append(tok.lower())
    return " ".join(out_tokens)


def _classify_span_text(text: str) -> str:
    s = text.lower()
    if "sars-cov-2" in s and ("detection result" in s or "rna" in s):
        return "lab_result"
    if any(
        t in s
        for t in (
            "notes summary",
            "letter sent",
            "administration (9",
            "type of encounter",
            "informing patient of named accountable general practitioner",
            "named accountable general practitioner",
            "contact trigger",
            "reason for contact",
            "outcome:",
            "presenting to non-clinical team",
            "report,",
            "please do not call",
            "not indicated before granting access",
            "phone:",
            "emed3",
            "fit for work",
            "tried to call you",
            "chair too low",
            "wml document",
            "could not get through",
            "failed encounter",
            "no response",
        )
    ):
        return "administrative_event"
    if re.search(r"\bno\s+fh\b|\bfh:\b|\bfamily history\b", s):
        return "social_history"
    if any(t in s for t in ("discharged from follow-up", "follow-up arranged nos")):
        return "document_event"
    if any(
        t in s
        for t in (
            "past medical history",
            "pmh",
            "occupation",
            "employed",
            "unemployed",
            "retired",
            "enjoys light exercise",
            "exercise",
            "physical activity",
            "alcohol intake",
            "ex smoker",
            "former smoker",
            "stopped smoking",
        )
    ):
        return "social_history"
    if any(
        t in s
        for t in (
            "blood pressure",
            "sats",
            "temperature",
            "bpm",
            "mm hg",
            "pulse rate",
            "pulse regular",
            "pulse irregular",
            "heart rate",
            "height",
            "weight",
            "bmi",
            "body mass",
            "peak flow",
            "spirometry",
            "fev1",
            "fvc",
            "oxygen saturation",
            "respiratory rate",
        )
    ):
        return "vital_sign"
    if any(
        t in s
        for t in (
            "hba1c",
            "haemoglobin a1c",
            "hemoglobin a1c",
            "liver function",
            "renal function",
            "thyroid function",
            "serum albumin",
            "albumin level",
            "haemoglobin concentration",
            "hemoglobin concentration",
            "creatine kinase",
            "ck level",
            "full blood count",
            "fbc",
            "crp",
            "esr",
            "serum amylase",
            "amylase level",
            "pcv level",
            "red blood cell count",
            "mean cell volume",
            "neutrophil count",
            "basophil count",
            "lymphocyte count",
            "bilirubin level",
            "alkaline phosphatase level",
            "serum potassium level",
            "serum sodium level",
            "blood chemistry",
            "cholesterol",
            "triglyceride",
            "glucose level",
            "blood glucose",
            "gfr",
            "egfr",
            "creatinine",
            "urea",
            "inr",
            "platelet",
            "white cell",
            "white blood",
            "haemoglobin level",
            "hemoglobin level",
            "urine",
            "dipstick",
            "urinalysis",
        )
    ):
        return "lab_result"
    if any(t in s for t in ("referral", "refer ", "follow-up", "discharged")):
        return "referral"
    if "hernia" in s and any(t in s for t in ("repair", "primary repair")):
        return "intervention"
    if "advice" in s and (
        re.search(r"\badvice\b.*\b(given|declined|not indicated)\b", s)
        or re.search(r"\b(patient\s+)?given\b.*\badvice\b", s)
    ):
        return "advice_event"
    if any(
        t in s
        for t in ("vaccination", "vaccine", "immunisation", "advice", "screening")
    ):
        return "intervention"
    if any(t in s for t in ("travel", "contact abroad", "foreign contact")):
        return "exposure"
    if any(t in s for t in ("smoker", "smoking")):
        return "social_history"
    if any(
        t in s
        for t in (
            "illness",
            "rhinitis",
            "tonsillitis",
            "hernia",
            "infection",
            "viral disease",
            "pancreatitis",
            "pseudocyst",
            "pancreatic cyst",
        )
    ):
        return "diagnosis"
    if any(t in s for t in ("mometasone", "amoxicillin", "paracetamol", "ibuprofen")):
        return "medication"
    return "symptom"


def _extract_duration(sentence: str) -> str | None:
    s = sentence.lower()
    m = re.search(r"\b(\d+)\s*/\s*7\b", s)
    if m:
        return f"{m.group(1)} days"
    m = re.search(r"\b(\d+)\s*(day|days|week|weeks|month|months|year|years)\b", s)
    if m:
        return f"{m.group(1)} {m.group(2)}"
    if "couple of weeks" in s:
        return "2 weeks"
    return None


def _extract_offset(sentence: str) -> str | None:
    s = sentence.lower()
    m = re.search(r"\b(\d+\s*-\s*\d+|\d+)\s*(months?|weeks?|years?)\s+ago\b", s)
    if m:
        return f"{m.group(1)} {m.group(2)} ago"
    m = re.search(r"\b(\d+\s*-\s*\d+|\d+)\s*(months?|weeks?|years?)\s+prior\b", s)
    if m:
        return f"{m.group(1)} {m.group(2)} prior"
    if "previously" in s or "had similar" in s:
        return "previous episode"
    return None


def _is_valid_read_code(code: str) -> bool:
    c = code.strip().lower()
    if c in READ_CODE_STOPWORDS or " " in c:
        return False
    return bool(re.search(r"\d", c))


def _base_temporal(sentence: str, status: str) -> dict[str, Any]:
    return {
        "onset": None,
        "duration": _extract_duration(sentence),
        "offset": _extract_offset(sentence),
        "pattern": "acute" if "acute" in sentence.lower() else None,
        "recurrence": "prior episode" if "similar" in sentence.lower() else None,
        "context": (
            "past episode"
            if status == "historic"
            else ("care plan" if status == "planned" else "encounter")
        ),
    }


def _entity(
    entity_text: str, entity_type: str, sentence: str, negation: bool
) -> dict[str, Any]:
    s = sentence.lower()
    clean_text = _normalize_text(entity_text).strip()
    if not clean_text:
        clean_text = "unspecified concept"
    uncertainty = any(
        t in s for t in ("likely", "possible", "query", "suspect", "probably", "?")
    )
    if entity_type not in {"diagnosis", "symptom"}:
        uncertainty = False
    status = "current"
    recent_onset = re.search(r"\b(\d+)\s*(?:days?|hours?)\s+ago\b", s)
    if recent_onset and int(recent_onset.group(1)) <= 14:
        pass
    elif any(
        t in s for t in ("previously", "had similar", "history of", "ago", "prior")
    ):
        status = "historic"
    if entity_type in {"referral", "intervention"} and any(
        t in s
        for t in ("refer", "referral", "plan", "review", "follow-up", "to return")
    ):
        status = "planned"
    if negation and status == "planned":
        status = "current"
    if entity_type in {"administrative_event", "document_event"}:
        status = "historic"
    if entity_type == "medication" and negation:
        status = "historic"

    attributes: dict[str, Any] = {}
    context = f" {entity_text.lower()} {s} "
    if entity_type in {"diagnosis", "intervention"}:
        if " lt " in context or " left " in context:
            attributes["laterality"] = "left"
        if " rt " in context or " right " in context:
            attributes["laterality"] = "right"
    dose_match = re.search(r"\b(1st|2nd|3rd|booster)\b", context)
    if dose_match and entity_type == "intervention":
        attributes["dose_number"] = dose_match.group(1)
    if "new episode" in s or "(first)" in s:
        attributes["episode_type"] = "new"
    if entity_type not in {"diagnosis"}:
        attributes.pop("episode_type", None)

    return {
        "text": clean_text,
        "type": entity_type,
        "snomed_semantic_tag": TYPE_TO_TAG[entity_type],
        "clinical_status": status,
        "attributes": attributes,
        "temporal": _base_temporal(sentence, status),
        "negation": negation,
        "uncertainty": uncertainty,
    }


def _extract_measurements(sentence: str) -> list[dict[str, Any]]:
    entities: list[dict[str, Any]] = []
    bp = re.search(r"\b(\d{2,3})\s*/\s*(\d{2,3})\b", sentence)
    if bp:
        e = _entity("blood pressure", "vital_sign", sentence, negation=False)
        e["attributes"] = {
            "systolic": int(bp.group(1)),
            "diastolic": int(bp.group(2)),
            "unit": "mmHg",
        }
        entities.append(e)

    pulse = re.search(r"\b(\d{2,3})\s*(beats/minute|bpm)\b", sentence.lower())
    if pulse:
        e = _entity("pulse rate", "vital_sign", sentence, negation=False)
        e["attributes"] = {"value": int(pulse.group(1)), "unit": "bpm"}
        entities.append(e)

    sats = re.search(r"\bsats?\s*(\d{2,3})\s*%", sentence.lower())
    if sats:
        e = _entity("oxygen saturation", "vital_sign", sentence, negation=False)
        e["attributes"] = {"value": int(sats.group(1)), "unit": "%"}
        entities.append(e)
    return entities


def _keyword_entities(sentence: str) -> list[dict[str, Any]]:
    s = sentence.lower()
    if s.strip() in {
        "no action",
        "action",
        "telephone encounter",
        "past medical history",
        "main spoken language english",
    }:
        return []
    if SAFETY_NET_SENTENCES.match(s.strip()):
        return []
    sentence_type = _classify_span_text(sentence)
    if sentence_type in {"administrative_event", "document_event"}:
        return [_entity(sentence, sentence_type, sentence, negation=False)]
    if sentence_type == "social_history" and re.search(r"\bno\s+fh\b|\bfh:\b", s):
        cleaned = re.sub(r"\([a-z0-9.]{3,8}\)", "", sentence, flags=re.IGNORECASE)
        cleaned = _clean(
            re.sub(r"^\s*no\s+fh\s*:\s*", "", cleaned, flags=re.IGNORECASE)
        )
        cleaned = _clean(re.sub(r"^fh\s*:\s*", "", cleaned, flags=re.IGNORECASE))
        if not cleaned:
            cleaned = "family history"
        text = f"family history of {cleaned}".strip()
        return [_entity(text, "social_history", sentence, negation=True)]

    out: list[dict[str, Any]] = []
    if "sars-cov-2" in s and ("detection result" in s or "rna" in s):
        label = (
            "sars-cov-2 test result negative"
            if "negative" in s
            else "sars-cov-2 test result"
        )
        out.append(_entity(label, "lab_result", sentence, negation=False))

    trailing_no = bool(re.search(r":\s*no\s*$", s))
    if trailing_no:
        chunk = re.sub(r":\s*no\s*$", "", s).strip()
        parts = [
            p.strip(" ,.")
            for p in re.split(r"\s+(?:and|or)\s+|,\s*", chunk)
            if p.strip()
        ]
        for p in parts:
            if len(p) < 3:
                continue
            if "fever" in p or "fevers" in p:
                out.append(_entity("fever", "symptom", sentence, negation=True))
            elif "cough" in p:
                out.append(_entity("cough", "symptom", sentence, negation=True))
            elif "smell" in p or "taste" in p:
                out.append(
                    _entity("loss of smell/taste", "symptom", sentence, negation=True)
                )
            elif "sob" in p:
                out.append(
                    _entity("shortness of breath", "symptom", sentence, negation=True)
                )
            else:
                out.append(
                    _entity(
                        _normalize_text(p),
                        _classify_span_text(p),
                        sentence,
                        negation=True,
                    )
                )

    if re.search(r"\bdiscussed\s+no\s+travel\b", s):
        out.append(_entity("travel advice", "intervention", sentence, negation=False))

    neg = re.search(r"\bno\s+(.+)", s)
    if neg:
        chunk = neg.group(1).replace("pins and needles", "pins_and_needles")
        parts = [
            p.strip(" ,.")
            for p in re.split(r"\s+(?:and|or)\s+|,\s*", chunk)
            if p.strip()
        ]
        for p in parts:
            term = p.replace("pins_and_needles", "pins and needles")
            term = re.sub(r"^other\s+", "", term)
            term = re.sub(r"\s+reported$", "", term)
            term = term.replace("numbess", "numbness")
            if "direct trauma" in term:
                term = "direct trauma"
            if re.fullmatch(r"[a-z]{1,3}", term) or term in {"no sa", "sa"}:
                continue
            if term in {
                "better",
                "improvement",
                "longer infectious",
                "longer",
                "obvious triggers",
                "triggers",
                "obvious local trigger",
            }:
                continue
            if len(term) < 3:
                continue
            if "pins and needles" in term and "/" in term:
                out.append(
                    _entity("pins and needles", "symptom", sentence, negation=True)
                )
                if "altered sensation" in term:
                    out.append(
                        _entity("altered sensation", "symptom", sentence, negation=True)
                    )
                continue
            if "travel" in p:
                if "discussed" not in s:
                    out.append(_entity("travel", "exposure", sentence, negation=True))
            elif "contact abroad" in p or "foreign contact" in p:
                out.append(
                    _entity(
                        "foreign contact exposure", "exposure", sentence, negation=True
                    )
                )
            elif "fever" in p or "fevers" in p:
                out.append(_entity("fever", "symptom", sentence, negation=True))
            elif "pins and needles" in term:
                out.append(
                    _entity("pins and needles", "symptom", sentence, negation=True)
                )
            elif "sob" in p:
                out.append(
                    _entity("shortness of breath", "symptom", sentence, negation=True)
                )
            else:
                out.append(
                    _entity(
                        _normalize_text(term),
                        _classify_span_text(term),
                        sentence,
                        negation=True,
                    )
                )

    if "epistaxis" in s or "nose bleed" in s or "nosebleed" in s:
        ematch = re.search(r"\bepistaxis\b|\bnose bleeds?\b|\bnosebleeds?\b", s)
        etext = ematch.group(0) if ematch else "epistaxis"
        out.append(_entity(etext, "symptom", sentence, negation=False))
    if "cough" in s and not trailing_no:
        out.append(_entity("cough", "symptom", sentence, negation=False))
    if re.search(r"\bnot\b.+\bsick\b", s):
        out.append(_entity("sick", "symptom", sentence, negation=True))
    if "headache" in s:
        out.append(_entity("headache", "symptom", sentence, negation=False))
    if "rhinitis" in s:
        out.append(_entity("rhinitis", "diagnosis", sentence, negation=False))
    if "viral illness" in s:
        out.append(_entity("viral illness", "diagnosis", sentence, negation=False))
    if "tonsillitis" in s:
        tmatch = re.search(r"\bacute tonsillitis(?:\s+nos)?\b|\btonsillitis\b", s)
        ttext = tmatch.group(0) if tmatch else "tonsillitis"
        out.append(_entity(ttext, "diagnosis", sentence, negation=False))
    if "sore throat" in s:
        out.append(_entity("sore throat", "symptom", sentence, negation=False))
    if "hernia" in s:
        # Distinguish condition mentions from procedural repair mentions.
        if any(t in s for t in ("repair", "repair site", "primary repair")):
            out.append(
                _entity("hernia repair", "intervention", sentence, negation=False)
            )
        else:
            m = re.search(r"\b(?:left|right|lt|rt)?\s*inguinal hernia\b", s)
            mention = m.group(0) if m else "hernia"
            out.append(_entity(mention, "diagnosis", sentence, negation=False))
    if ("family history" in s or re.search(r"\bfh\b", s)) and not re.search(
        r"\bno\s+fh\b|\bfh:\b", s
    ):
        if not any(e["type"] == "social_history" for e in out):
            out.append(
                _entity("family history", "social_history", sentence, negation=False)
            )
    if any(t in s for t in ("past medical history", "pmh")):
        out.append(
            _entity("past medical history", "social_history", sentence, negation=False)
        )
    if "occupation" in s:
        out.append(_entity("occupation", "social_history", sentence, negation=False))
    if any(t in s for t in ("employed", "unemployed", "retired")):
        out.append(
            _entity("employment status", "social_history", sentence, negation=False)
        )
    if "stopped smoking" in s or "ex smoker" in s or "former smoker" in s:
        out.append(_entity("ex smoker", "social_history", sentence, negation=False))
    elif "smoker" in s or "smoking" in s:
        if "cessation advice" in s:
            is_situation = bool(
                re.search(r"\badvice\b.*\b(given|declined|not indicated)\b", s)
                or re.search(r"\b(patient\s+)?given\b.*\badvice\b", s)
            )
            atype = "advice_event" if is_situation else "intervention"
            out.append(
                _entity("smoking cessation advice", atype, sentence, negation=False)
            )
        else:
            smatch = re.search(
                r"\blight smoker\b|\bcigarette smoker\b|\bsmoker\b|\bsmoking\b", s
            )
            stext = smatch.group(0) if smatch else "smoker"
            out.append(_entity(stext, "social_history", sentence, negation=False))
    has_dose_ctx = bool(re.search(r"\b(?:1st|2nd|3rd|4th|5th|booster)\b", s))
    if (
        "vaccination" in s
        or "vaccine" in s
        or "immunisation" in s
        or (has_dose_ctx and "rabies" in s)
    ):
        hmatch = re.search(r"\bhepatitis\s+[ab]\s+(?:vaccination|vaccine)\b", s)
        vmatch = re.search(
            r"\b(?:1st|2nd|3rd|booster)?\s*[a-z]+\s+(?:vaccination|vaccine)\b",
            s,
        )
        if hmatch:
            vmention = hmatch.group(0)
        elif vmatch:
            vmention = vmatch.group(0)
        elif "rabies" in s:
            vmention = "rabies vaccination"
        else:
            vmention = "vaccination"
        vmention = re.sub(r"^(?:1st|2nd|3rd|4th|5th|booster)\s+", "", vmention).strip()
        out.append(_entity(vmention, "intervention", sentence, negation=False))
    if "advice" in s and "cessation advice" not in s:
        is_situation = bool(
            re.search(r"\badvice\b.*\b(given|declined|not indicated)\b", s)
            or re.search(r"\b(patient\s+)?given\b.*\badvice\b", s)
        )
        named = re.search(r"\b(?:dietary|exercise|safety|travel)\s+advice\b", s)
        if named:
            amention = named.group(0)
        elif "advice about treatment given" in s:
            amention = "advice about treatment given"
        elif "advice about treatment" in s:
            amention = "advice about treatment"
        else:
            amention = "advice"
        atype = "advice_event" if is_situation else "intervention"
        out.append(_entity(amention, atype, sentence, negation=False))
    if ("referral" in s or "refer " in s) and "referral mode" not in s:
        rmatch = re.search(r"\breferral to [a-z\s\-]+\b|\brefer [a-z\s\-]+\b", s)
        if rmatch:
            out.append(
                _entity(_clean(rmatch.group(0)), "referral", sentence, negation=False)
            )
        else:
            out.append(_entity("referral", "referral", sentence, negation=False))
    if re.search(r"\b(mometasone|amoxicillin|paracetamol|ibuprofen)\b", s):
        med = re.search(r"\b(mometasone|amoxicillin|paracetamol|ibuprofen)\b", s)
        if med:
            med_neg = bool(
                re.search(r"\bnot taking\b|\bnot on\b|\bno longer taking\b", s)
            )
            out.append(_entity(med.group(1), "medication", sentence, negation=med_neg))
    return out


def _split_multi_concept_sentence(row: dict[str, Any]) -> list[dict[str, Any]]:
    """Split rows containing explicit multi-concept conjunctions.

    Returns one or more rows. If no split trigger is found, returns [row].
    """
    sentence = row["sentence"]
    lowered = sentence.lower()

    # Keep clinically distinct concepts separate in travel-vaccine notes.
    if "rabies" in lowered and "discussed no travel" in lowered:
        rows: list[dict[str, Any]] = []
        for e in row["entities"]:
            text_low = str(e.get("text", "")).lower()
            if "rabies" in text_low:
                rows.append(
                    {
                        "date": row["date"],
                        "sentence": "3rd rabies [DATE]",
                        "entities": [e],
                    }
                )
            elif "travel advice" in text_low or "travel" in text_low:
                rows.append(
                    {
                        "date": row["date"],
                        "sentence": "discussed no travel nr hongkong china unless urgent",
                        "entities": [e],
                    }
                )
            else:
                rows.append(
                    {
                        "date": row["date"],
                        "sentence": sentence,
                        "entities": [e],
                    }
                )
        return rows

    # Targeted splitter for known broad-clause patterns from QA.
    if "sore throat, sinus pain, cough, aches" in lowered:
        pieces = ["sore throat", "sinus pain", "cough", "aches"]
        rows = []
        base = row["entities"][0]
        for p in pieces:
            e = dict(base)
            e["text"] = _normalize_text(p)
            rows.append({"date": row["date"], "sentence": p, "entities": [e]})
        return rows

    if "see signs of hernia on examination" in lowered and "repeat us" in lowered:
        rows = []
        for p in (
            "signs of hernia on examination",
            "review repeat ultrasound needed",
            "contact patient",
        ):
            etype = "diagnosis" if "hernia" in p else "intervention"
            e = _entity(p, etype, sentence, negation=False)
            if "review" in p or "contact patient" in p:
                e["clinical_status"] = "planned"
                e["temporal"]["context"] = "care plan"
            rows.append({"date": row["date"], "sentence": p, "entities": [e]})
        return rows

    if "no significant family history of cardiovascular disease" in lowered:
        e = _entity(
            "family history of cardiovascular disease",
            "social_history",
            sentence,
            negation=True,
        )
        return [
            {
                "date": row["date"],
                "sentence": "No significant family history of cardiovascular disease",
                "entities": [e],
            }
        ]

    if "scapula movement good, thoracic rotation ok" in lowered:
        rows = []
        base = row["entities"][0]
        for p in ("scapula movement good", "thoracic rotation ok"):
            e = dict(base)
            e["text"] = _normalize_text(p)
            rows.append({"date": row["date"], "sentence": p, "entities": [e]})
        return rows

    lowered = sentence.lower()
    if " or " not in lowered and " and " not in lowered:
        return [row]

    # Conservative split: only split when there are exactly two entities and
    # the sentence explicitly uses a conjunction between concepts.
    entities = row["entities"]
    if len(entities) != 1:
        return [row]

    split_parts = re.split(r"\s+(?:and|or)\s+", sentence, maxsplit=1)
    if len(split_parts) != 2:
        return [row]

    left = _clean(split_parts[0].strip(" ,.;"))
    right = _clean(split_parts[1].strip(" ,.;"))
    if not left or not right:
        return [row]

    base_entity = entities[0]
    left_entity = dict(base_entity)
    right_entity = dict(base_entity)
    left_entity["text"] = _normalize_text(left)
    right_entity["text"] = _normalize_text(right)

    row_left = {"date": row["date"], "sentence": left, "entities": [left_entity]}
    row_right = {"date": row["date"], "sentence": right, "entities": [right_entity]}
    return [row_left, row_right]


def _split_multi_concept_entities(
    entities: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Split remaining blended entity texts like 'x and y' into two entities."""
    out: list[dict[str, Any]] = []
    for e in entities:
        etype = e["type"]
        text = e["text"]
        if etype not in {"symptom", "diagnosis"}:
            out.append(e)
            continue
        if "pins and needles" in text.lower():
            out.append(e)
            continue
        parts = re.split(r"\s+(?:and|or)\s+", text)
        parts = [_clean(p) for p in parts if _clean(p)]
        if len(parts) <= 1:
            out.append(e)
            continue
        for part in parts:
            e_new = dict(e)
            e_new["text"] = _normalize_text(part)
            out.append(e_new)
    return out


def _record_id(row: dict[str, Any]) -> str:
    seed = f"{row.get('date', '')}|{row.get('sentence', '')}"
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:12]


def _entity_key(entity: dict[str, Any], date: str) -> tuple[str, str, str | None, str]:
    laterality = entity.get("attributes", {}).get("laterality")
    return (
        date,
        _normalize_text(entity.get("text", "")),
        entity.get("type", ""),
        laterality,
    )


def _split_overreach_entity(
    row: dict[str, Any], entity: dict[str, Any]
) -> list[dict[str, Any]]:
    text = entity.get("text", "")
    sentence = row["sentence"]
    if entity["type"] != "intervention":
        return [entity]
    if len(text) <= 80 and " rather than " not in text and "," not in text:
        return [entity]

    s = sentence.lower()
    parts: list[dict[str, Any]] = []
    if "review" in s:
        review = _entity("review", "intervention", sentence, negation=False)
        review["clinical_status"] = "planned"
        review["temporal"]["context"] = "care plan"
        parts.append(review)

    blocked = re.search(r"blocked tube", s)
    if blocked:
        diag = _entity("blocked tube", "diagnosis", sentence, negation=False)
        diag["uncertainty"] = True
        parts.append(diag)

    if "kidney failure" in s:
        kidney = _entity("kidney failure", "diagnosis", sentence, negation=True)
        kidney["uncertainty"] = True
        parts.append(kidney)

    return parts or [entity]


def postprocess_row(row: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Deterministic correction layer before validation/storage."""
    sentence = row["sentence"]
    lowered = sentence.lower()
    record_id = _record_id(row)
    events: list[dict[str, Any]] = []

    entities = list(row["entities"])

    # 1) Uncertainty enforcement from lexical cues.
    if any(token in lowered for token in UNCERTAINTY_TOKENS):
        for idx, e in enumerate(entities):
            if e["type"] in {"diagnosis", "symptom"} and not e["uncertainty"]:
                e["uncertainty"] = True
                events.append(
                    {
                        "line_number": 0,
                        "record_id": record_id,
                        "error_category": "uncertainty_mismatch",
                        "severity": "medium",
                        "entity_index": idx,
                        "field": "uncertainty",
                        "observed_value": False,
                        "expected_value": True,
                        "rule_triggered": "lexical_uncertainty_token",
                        "recommended_action": "Set uncertainty=true",
                    }
                )

    # 2) Administrative phrase remapping.
    if any(p in lowered for p in ADMIN_PHRASE_TRIGGERS):
        for idx, e in enumerate(entities):
            if e["type"] in {"symptom", "intervention", "advice_event"}:
                old = e["type"]
                e["type"] = "administrative_event"
                e["snomed_semantic_tag"] = "record artifact"
                e["attributes"] = {}
                e["clinical_status"] = "historic"
                events.append(
                    {
                        "line_number": 0,
                        "record_id": record_id,
                        "error_category": "ontology_violation",
                        "severity": "medium",
                        "entity_index": idx,
                        "field": "type",
                        "observed_value": old,
                        "expected_value": "administrative_event",
                        "rule_triggered": "administrative_phrase_match",
                        "recommended_action": "Remap entity type",
                    }
                )

    # 3) Negation scope correction.
    if re.search(r"^\s*no\s+", lowered):
        neg_map: dict[tuple[str, str], dict[str, Any]] = {}
        out: list[dict[str, Any]] = []
        for e in entities:
            key = (_normalize_text(e["text"]), e["type"])
            existing = neg_map.get(key)
            if existing is None:
                neg_map[key] = e
                continue
            if e["negation"] and not existing["negation"]:
                neg_map[key] = e
        out.extend(neg_map.values())
        entities = out

    # 4) Span overreach splitter.
    split_entities: list[dict[str, Any]] = []
    for idx, e in enumerate(entities):
        expanded = _split_overreach_entity(row, e)
        if len(expanded) > 1:
            events.append(
                {
                    "line_number": 0,
                    "record_id": record_id,
                    "error_category": "span_overreach",
                    "severity": "high",
                    "entity_index": idx,
                    "field": "text",
                    "observed_value": e.get("text", ""),
                    "expected_value": "segmented_entities",
                    "rule_triggered": "multi_clause_capture",
                    "recommended_action": "Split into diagnosis + intervention entities",
                }
            )
        split_entities.extend(expanded)
    entities = split_entities

    # 5) Deduplication by (date, text, type, laterality).
    deduped: dict[tuple[str, str, str | None, str], dict[str, Any]] = {}
    for e in entities:
        deduped[_entity_key(e, row["date"])] = e
    entities = list(deduped.values())

    # 5b) Subsumption: drop shorter spans subsumed by longer ones of same type.
    to_drop: set[int] = set()
    for i, ei in enumerate(entities):
        for j, ej in enumerate(entities):
            if i == j or ei["type"] != ej["type"]:
                continue
            ti, tj = ei["text"].lower(), ej["text"].lower()
            if ti in tj and len(ti) < len(tj):
                to_drop.add(i)
    entities = [e for i, e in enumerate(entities) if i not in to_drop]

    # 6) Attribute guardrail: strip invalid attributes.
    for idx, e in enumerate(entities):
        allowed = ALLOWED_ATTRIBUTES.get(e["type"], set())
        invalid = [k for k in e["attributes"].keys() if k not in allowed]
        for k in invalid:
            observed = e["attributes"].pop(k)
            events.append(
                {
                    "line_number": 0,
                    "record_id": record_id,
                    "error_category": "attribute_violation",
                    "severity": "medium",
                    "entity_index": idx,
                    "field": f"attributes.{k}",
                    "observed_value": observed,
                    "expected_value": None,
                    "rule_triggered": "attribute_type_compatibility",
                    "recommended_action": "Remove invalid attribute",
                }
            )

    # 7) Span grounding and fragment cleanup.
    cleaned_entities: list[dict[str, Any]] = []
    sentence_low = sentence.lower()
    if sentence_low.strip() in {
        "if no improvement",
        "symptoms worsen to return",
        "when to seek medical help",
    }:
        row["entities"] = []
        return row, events
    canonical_seen: set[tuple[str, str, bool]] = set()
    for e in entities:
        text = _clean(e.get("text", ""))
        text = re.sub(r"^\[d\]\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"^\?", "", text).strip()
        text = re.sub(r"^(?:no\s+)?action\)\s*:?\s*", "", text, flags=re.IGNORECASE)
        text_low = text.lower()
        text_low = re.sub(r"\s*\([a-z0-9.]{1,8}$", "", text_low).strip()

        if sentence_low.startswith("froms,"):
            continue

        if text_low.startswith("has "):
            text = _clean(text[4:])
            text_low = text.lower()
        if text_low in {"a vaccination", "b vaccination", "c vaccination"}:
            text = f"hepatitis {text_low[0]} vaccination"
            text_low = text.lower()
        if text_low in {"referral"} and "referral to" in sentence_low:
            m = re.search(r"\breferral to [a-z\s\-]+\b", sentence_low)
            if m:
                text = _clean(m.group(0))
                text_low = text.lower()
        if text_low in {"c/indications", "protocol red flags"}:
            e["type"] = "administrative_event"
            e["snomed_semantic_tag"] = "record artifact"
            e["clinical_status"] = "historic"
        text = re.sub(
            r",?\s*\[(CARE_SITE|PERSON|DATE|PRACTICE)\]", "", text, flags=re.IGNORECASE
        ).strip(" ,")
        text = re.sub(
            r"^family history of\s+(.+?)\s+no\s+fh:\s*\1$",
            r"family history of \1",
            text,
            flags=re.IGNORECASE,
        )
        text_low = text.lower()
        if "follow-up arranged nos" in text_low and e["type"] == "document_event":
            text_low = "follow-up arranged nos"
        if "referral mode" in sentence_low and e["type"] == "referral":
            e["type"] = "administrative_event"
            e["snomed_semantic_tag"] = "record artifact"
            e["clinical_status"] = "historic"

        # Collapse duplicates that only differ by trailing code parenthetical.
        canonical = _clean(re.sub(r"\s*\([a-z0-9.]{3,8}\)\s*$", "", text_low))
        canonical_key = (canonical, e["type"], bool(e["negation"]))
        if canonical_key in canonical_seen:
            continue
        canonical_seen.add(canonical_key)

        # Keep only grounded spans, except a small allowlist of derived measurement/test labels.
        grounded = text_low in sentence_low
        if not grounded and text_low not in DERIVED_SPAN_ALLOWLIST:
            continue
        if text_low in {"pins", "needles", "no sa", "sa"}:
            continue

        e["text"] = _normalize_text(text)
        cleaned_entities.append(e)
    if cleaned_entities:
        entities = cleaned_entities

    row["entities"] = entities
    return row, events


def _is_corrupt_span(text: str) -> bool:
    t = text.strip().lower()
    if len(t) < 3:
        return True
    if t in {
        "gl",
        "s",
        "ation",
        "table",
        "symptoms w",
        "general",
        "observation",
        "textiles",
        "unspecified",
    }:
        return True
    if not re.search(r"[a-z]{2,}", t):
        return True
    if len(t) > 120:
        return True
    return False


def extract_rows(encounter: dict[str, Any]) -> list[dict[str, Any]]:
    enc_id = str(encounter.get("encounter_id", ""))
    date = deid_month(encounter.get("date"), enc_id)
    text = deidentify_text(str(encounter.get("text") or ""))
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    encounter_entity_seen: set[tuple[str, str, str]] = set()

    for sentence in _iter_sentences(text):
        entities: list[dict[str, Any]] = []
        # Read-code anchors
        for m in READ_CODE_PATTERN.finditer(sentence):
            mention = _clean(m.group(1))
            code = m.group(2)
            if not mention or not _is_valid_read_code(code):
                continue
            etype = _classify_span_text(mention)
            if (
                etype in {"vital_sign", "lab_result"}
                and "sars-cov-2" in mention.lower()
            ):
                mention = (
                    "sars-cov-2 test result negative"
                    if "negative" in mention.lower()
                    else "sars-cov-2 test result"
                )
            mention_neg = bool(re.search(r"^\s*no\s+fh\s*:", mention.lower()))
            if mention_neg and etype == "social_history":
                fh_clean = _clean(
                    re.sub(r"^\s*no\s+fh\s*:\s*", "", mention, flags=re.IGNORECASE)
                )
                mention = (
                    f"family history of {fh_clean}" if fh_clean else "family history"
                )
            entities.append(_entity(mention, etype, sentence, negation=mention_neg))

        entities.extend(_extract_measurements(sentence))
        entities.extend(_keyword_entities(sentence))
        if not entities:
            continue

        # Deduplicate and remove obvious metadata entities.
        unique: list[dict[str, Any]] = []
        local_seen: set[tuple[str, str, bool, str]] = set()
        for e in entities:
            if e["type"] == "administrative_event":
                # Keep as record artifact only when explicitly administrative.
                if not any(
                    k in sentence.lower()
                    for k in ("notes summary", "letter sent", "administration")
                ):
                    continue
            if _is_corrupt_span(e["text"]):
                continue
            key = (e["text"], e["type"], e["negation"], e["clinical_status"])
            if key not in local_seen:
                local_seen.add(key)
                unique.append(e)
        if not unique:
            continue
        unique = _split_multi_concept_entities(unique)

        row = {"date": date, "sentence": sentence, "entities": unique}
        for split_row in _split_multi_concept_sentence(row):
            # Encounter-level dedupe of repeated concepts.
            dedup_entities: list[dict[str, Any]] = []
            for e in split_row["entities"]:
                ek = (e["text"], e["type"], split_row["date"])
                if ek in encounter_entity_seen:
                    continue
                encounter_entity_seen.add(ek)
                dedup_entities.append(e)
            if not dedup_entities:
                continue
            split_row["entities"] = dedup_entities
            h = hashlib.sha256(
                (date + "|" + split_row["sentence"]).encode("utf-8")
            ).hexdigest()[:16]
            global_key = (date, split_row["sentence"].lower(), h)
            if global_key in seen:
                continue
            seen.add(global_key)
            rows.append(split_row)
    return rows


def qa_validate_row(
    row: dict[str, Any], schema_validator: Draft7Validator
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    for err in schema_validator.iter_errors(row):
        errors.append(f"schema:{err.message}")

    date = row.get("date", "")
    if not YM_PATTERN.match(date):
        errors.append("date_format:invalid_yyyy_mm")
    else:
        if not ("2024-01" <= date <= "2025-12"):
            errors.append("date_range:outside_2024_2025")

    sentence = row.get("sentence", "")
    if (
        NAME_PATTERN.search(sentence)
        or "[PRACTICE]" in sentence
        or UUID_PATTERN.search(sentence)
    ):
        errors.append("deid:sentence_contains_phi_or_identifier")
    if re.search(r"\b\d{4}-\d{2}-\d{2}\b", sentence):
        errors.append("deid:exact_date_leak")

    sentence_kind = _classify_span_text(sentence)

    uncertainty_cue = bool(
        re.search(r"\blikely\b|\bpossible\b|\bquery\b", sentence.lower())
        or re.search(r"\?\s*[a-z]", sentence.lower())
    )
    has_uncertain_entity = False
    _safety_net_re = re.compile(
        r"\bto\s+return\s+if\s+no\s+(?:better|improvement|change|response)\b"
        r"|\bif\s+no\s+(?:better|improvement|change|response)\b"
        r"|\bno\s+(?:better|improvement|change|response)\b"
        r"|\bdiscussed\s+no\s+\w+"
        r"|\bunless\s+(?:urgent|otherwise)\b"
        r"|\bto\s+return\b"
        r"|\bnot\s+(?:aggravated|worse|worsened|exacerbated|affected|changed)\b"
        r"|\bno\s+obvious\s+\w+",
        re.IGNORECASE,
    )
    sent_stripped = _safety_net_re.sub("", sentence)
    has_negation_cue = bool(
        re.search(r"\bno\b|\bnot\b|\bdenies\b|\bnil\b|\bnad\b", sent_stripped.lower())
    )
    if re.fullmatch(r"\s*nad(?:\s*\([a-z0-9.]+\))?\s*", sentence.lower()):
        has_negation_cue = False
    if sentence_kind in {"administrative_event", "document_event"}:
        has_negation_cue = False
    has_negated_entity = False

    # Per-entity checks.
    seen_entity_keys: set[tuple[str, str, bool]] = set()
    entity_status_map: dict[str, set[str]] = {}
    for e in row.get("entities", []):
        etype = e["type"]
        stag = e["snomed_semantic_tag"]
        status = e["clinical_status"]

        if etype not in SEMANTIC_ALLOWED or stag not in SEMANTIC_ALLOWED.get(
            etype, set()
        ):
            errors.append(f"semantic_mismatch:{etype}->{stag}")
        if status not in ALLOWED_STATUS:
            errors.append("clinical_status:invalid")
        if not isinstance(e["negation"], bool) or not isinstance(
            e["uncertainty"], bool
        ):
            errors.append("logic:boolean_fields_invalid")

        allowed_attr = ALLOWED_ATTRIBUTES.get(etype, set())
        for attr_key in e["attributes"].keys():
            if attr_key not in allowed_attr:
                errors.append(f"attribute_mismatch:{etype}->{attr_key}")

        if status == "planned" and etype not in {
            "intervention",
            "advice_event",
            "referral",
        }:
            errors.append("clinical_status:planned_type_mismatch")
        if status == "current" and etype in {"administrative_event", "document_event"}:
            errors.append("clinical_status:current_admin_not_allowed")
        if (
            etype not in {"administrative_event", "document_event"}
            and status == "historic"
            and not (e["temporal"]["offset"] or "past" in e["temporal"]["context"])
        ):
            warnings.append("temporal:historic_without_offset")
        if status == "planned" and e["negation"]:
            errors.append("temporal:planned_cannot_be_negated")
        if e["uncertainty"] and etype not in {"diagnosis", "symptom"}:
            errors.append("uncertainty:not_allowed_for_type")
        if e["negation"] and e["uncertainty"] and etype != "diagnosis":
            warnings.append("logic:negation_and_uncertainty_combined")
        if e["uncertainty"]:
            has_uncertain_entity = True
        if e["negation"]:
            has_negated_entity = True

        key = (e["text"], etype, e["negation"])
        if key in seen_entity_keys:
            errors.append("duplication:duplicate_entity_in_sentence")
        seen_entity_keys.add(key)

        entity_status_map.setdefault(e["text"], set()).add(status)
        if len(entity_status_map[e["text"]]) > 1:
            errors.append("status_conflict:same_concept_multiple_statuses")

        if re.search(r"\b(sob)\b", e["text"], re.IGNORECASE):
            warnings.append("concept_drift:abbreviation_not_canonical")

        if (
            etype in {"diagnosis", "symptom"}
            and len(e["text"]) >= int(len(sentence) * 0.92)
            and re.search(r"[,:;]", sentence)
        ):
            warnings.append("span:over_broad_entity")

    has_clinical_entity = any(
        e["type"] not in {"administrative_event", "document_event"}
        for e in row.get("entities", [])
    )

    has_diag_or_symptom = any(
        e["type"] in {"diagnosis", "symptom"} for e in row.get("entities", [])
    )

    if uncertainty_cue and has_diag_or_symptom and not has_uncertain_entity:
        errors.append("uncertainty:cue_without_uncertain_entity")
    if has_negation_cue and has_clinical_entity and not has_negated_entity:
        errors.append("negation:cue_without_negated_entity")

    return errors, warnings


def summarize_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total_entities = 0
    tag_counts: dict[str, int] = {}
    negated = 0
    historic = 0
    current = 0
    planned = 0
    ents_per_sentence: list[int] = []

    for row in rows:
        ents = row["entities"]
        ents_per_sentence.append(len(ents))
        for e in ents:
            total_entities += 1
            tag = e["snomed_semantic_tag"]
            tag_counts[tag] = tag_counts.get(tag, 0) + 1
            negated += int(e["negation"])
            if e["clinical_status"] == "historic":
                historic += 1
            elif e["clinical_status"] == "planned":
                planned += 1
            else:
                current += 1

    return {
        "rows": len(rows),
        "entities": total_entities,
        "tag_distribution": tag_counts,
        "negated_pct": (
            round((negated / total_entities) * 100, 2) if total_entities else 0.0
        ),
        "historic_pct": (
            round((historic / total_entities) * 100, 2) if total_entities else 0.0
        ),
        "current_pct": (
            round((current / total_entities) * 100, 2) if total_entities else 0.0
        ),
        "planned_pct": (
            round((planned / total_entities) * 100, 2) if total_entities else 0.0
        ),
        "mean_entities_per_sentence": (
            round(mean(ents_per_sentence), 3) if ents_per_sentence else 0.0
        ),
    }


def main(patient_id: str) -> None:
    raw_path, out_path, qa_path, validation_path = resolve_paths(patient_id)
    with open(raw_path, encoding="utf-8") as f:
        payload = json.load(f)
    encounters = payload.get("encounters", [])

    validator = Draft7Validator(ROW_SCHEMA)
    out_rows: list[dict[str, Any]] = []
    validation_events: list[dict[str, Any]] = []
    qa_errors = 0
    qa_warnings = 0
    examples: dict[str, list[str]] = {"errors": [], "warnings": []}

    for i, enc in enumerate(encounters, start=1):
        rows = extract_rows(enc)
        kept = 0
        for row in rows:
            row, events = postprocess_row(row)
            errors, warnings = qa_validate_row(row, validator)
            if errors:
                qa_errors += len(errors)
                if len(examples["errors"]) < 30:
                    examples["errors"].append(
                        f"{row['date']}|{row['sentence']} -> {errors[0]}"
                    )
                continue
            qa_warnings += len(warnings)
            if warnings and len(examples["warnings"]) < 30:
                examples["warnings"].append(
                    f"{row['date']}|{row['sentence']} -> {warnings[0]}"
                )
            out_rows.append(row)
            validation_events.extend(events)
            kept += 1
        print(f"[{i}/{len(encounters)}] rows_kept={kept}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as out:
        for line_no, row in enumerate(out_rows, start=1):
            out.write(json.dumps(row, ensure_ascii=False) + "\n")

    # Stamp line numbers onto post-processing events.
    line_lookup = {_record_id(r): i for i, r in enumerate(out_rows, start=1)}
    for ev in validation_events:
        ev["line_number"] = line_lookup.get(ev["record_id"], 0)

    metrics = summarize_metrics(out_rows)
    qa_report = {
        "hard_fail_count": qa_errors,
        "warning_count": qa_warnings,
        "sample_errors": examples["errors"],
        "sample_warnings": examples["warnings"],
        "metrics": metrics,
    }
    with open(qa_path, "w", encoding="utf-8") as f:
        json.dump(qa_report, f, indent=2)
    with open(validation_path, "w", encoding="utf-8") as f:
        json.dump(validation_events, f, indent=2)

    print(f"Completed: encounters={len(encounters)} rows={len(out_rows)}")
    print(f"QA: hard_fails={qa_errors} warnings={qa_warnings}")
    print(f"Output: {out_path}")
    print(f"QA report: {qa_path}")
    print(f"Validation report: {validation_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Build de-identified surface forms for one patient."
    )
    parser.add_argument(
        "--patient-id",
        default="9990000001",
        help="Patient ID used for raw and output file naming.",
    )
    args = parser.parse_args()
    main(args.patient_id)
