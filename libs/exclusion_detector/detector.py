"""Cancer exclusion detector — post-referral encounter classification.

Fetches encounters in the 0–100 day window after a cancer referral,
applies rule-based pre-filtering, then uses 2-model LLM consensus to
classify each encounter as cancer_excluded / cancer_confirmed /
still_investigating / pending_letter / not_relevant.

Follows the encounter_classifier pattern: AWS small + Azure small for
consensus, structured JSON output, deidentified text.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from libs.llm_client.factory import LLMResponse, create_llm
from libs.prompts.registry import get_prompt
from libs.utils.deidentify import deidentify_text

logger = logging.getLogger(__name__)

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)

VALID_OUTCOMES = frozenset(
    {
        "cancer_excluded",
        "cancer_confirmed",
        "still_investigating",
        "pending_letter",
        "not_relevant",
    }
)

DEFAULT_WINDOW_DAYS = 100


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class EncounterOutcome:
    encounter_id: str
    encounter_date: str
    outcome: str
    confidence: float
    evidence_text: str
    reasoning: str
    detection_method: str  # "rule" | "llm_consensus" | "llm_single"
    model_a_outcome: str = ""
    model_b_outcome: str = ""
    text_excerpt: str = ""


@dataclass
class PendingLetter:
    encounter_id: str
    encounter_date: str
    text_excerpt: str
    detection_method: str  # "rule" | "llm"


@dataclass
class ExclusionResult:
    patient_id: str
    referral_date: str
    referral_cancer_type: str
    outcome: str  # aggregated patient-level
    confidence: float = 0.0
    encounter_outcomes: list[EncounterOutcome] = field(default_factory=list)
    pending_letters: list[PendingLetter] = field(default_factory=list)
    encounters_scanned: int = 0
    encounters_skipped: int = 0
    window_end: str = ""


# ---------------------------------------------------------------------------
# Rule-based pre-filters
# ---------------------------------------------------------------------------

EXCLUSION_KEYWORDS = [
    "cancer excluded",
    "no cancer",
    "no evidence of cancer",
    "no evidence of malignancy",
    "no malignancy",
    "cancer ruled out",
    "non-malignant",
    "no neoplasm",
    "cancer not found",
    "discharged from cancer",
    "discharged from 2ww",
    "discharged from fast track",
    "no evidence of tumour",
    "no evidence of tumor",
]

SOFT_EXCLUSION_KEYWORDS = [
    "benign",
    "all clear",
    "reassured",
    "no further action",
    "discharged",
    "excluded",
]

DIAGNOSIS_KEYWORDS = [
    "carcinoma",
    "adenocarcinoma",
    "melanoma",
    "lymphoma",
    "sarcoma",
    "myeloma",
    "leukaemia",
    "leukemia",
    "malignant tumour",
    "malignant tumor",
    "malignant neoplasm",
    "biopsy confirmed",
    "histology confirmed",
    "mdt confirmed",
    "diagnosed with cancer",
    "cancer diagnosis",
]

INVESTIGATION_KEYWORDS = [
    "awaiting biopsy",
    "awaiting histology",
    "pending biopsy",
    "pending histology",
    "under investigation",
    "referred for ct",
    "referred for mri",
    "referred for scan",
    "colonoscopy",
    "endoscopy",
    "gastroscopy",
    "cystoscopy",
    "mammogram",
    "ultrasound scan",
    "core needle biopsy",
    "stereotactically guided",
    "2ww",
    "fast track referral",
    "seen in fast track",
]

LETTER_KEYWORDS = [
    "clinic letter from",
    "letter from oncology",
    "letter from haematology",
    "letter from urology",
    "letter from dermatology",
    "letter from breast",
    "letter from colorectal",
    "letter from gastroenterology",
    "letter from gynaecology",
    "letter from respiratory",
    "discharge letter from",
    "outpatient letter",
    "see hospital letter",
    "as per letter",
    "results letter from",
]

_CANCER_SPECIALTY_LETTER_RE = re.compile(
    r"(?:Oncology|Urology|Breast Clinic|Colorectal|Gastroenterology|"
    r"Dermatology|Gynaecology|Haematology|Histology|Pathology)"
    r"\s+to\s+",
    re.IGNORECASE,
)

_ADMIN_SKIP_RE = re.compile(
    r"(?:"
    r"^(?:SMS|Reminder|Appointment|SystmOne|Record Sharing|Registration)\b"
    r"|Summary Care Record Update"
    r"|Short message service text message"
    r"|Patient telephone number \(9159"
    r"|^\(R\)\s"
    r"|^Dear (?:patient|Mr|Mrs|Ms|Miss)"
    r"|Seasonal (?:Influenza|flu) Vaccination"
    r"|RSV Immunisation"
    r"|You did not attend your appointment"
    r"|we would like to know your sa"
    r"|we would like to call you today"
    r"|N\+S Encounter type"
    r"|^Pharmacy First:"
    r"|Auto-filed\s*$"
    r"|^\d{2}:\d{2}\s*-\s*Surgery:\s*Auto-filed"
    r")",
    re.IGNORECASE | re.MULTILINE,
)

_LAB_RESULT_RE = re.compile(
    r"(?:Serum|Plasma|Blood|Urine|Haemoglobin|Platelet|White cell|"
    r"Nucleated|Monocyte|Eosinophil|Neutrophil|Lymphocyte|Basophil|"
    r"Cholesterol|Triglyceride|Creatinine|Albumin|Bilirubin|"
    r"Glucose|Sodium|Potassium|Calcium|Magnesium|Phosphate|"
    r"ALT|AST|GGT|ALP|CRP|ESR|TSH|HbA1c|eGFR|INR|"
    r"Bone profile|Liver function|Renal function|Full blood count|"
    r"Lipid profile|Thyroid function|Coagulation screen|"
    r"Vitamin [BD]\d*|Folate|Ferritin|Iron)"
    r"\b.*(?:mmol|g/L|ng/|iu/L|nmol|10\^9|mL|umol|\[[\d\s\-\.]+\])",
    re.IGNORECASE,
)


def _has_keywords(text: str, keywords: list[str]) -> bool:
    lower = text.lower()
    return any(kw in lower for kw in keywords)


def _is_skip_encounter(text: str) -> bool:
    """Return True if the encounter is admin, prescriptions, labs, or noise."""
    stripped = text.strip()
    if len(stripped) < 15:
        return True
    if _ADMIN_SKIP_RE.search(stripped):
        return True
    # Auto-filed lab results: starts with "Auto-filed" header or is
    # predominantly lab values (multiple reference ranges on separate lines).
    lines = stripped.split("\n")
    lab_lines = sum(1 for ln in lines if _LAB_RESULT_RE.search(ln))
    if lab_lines >= 2 and lab_lines >= len(lines) * 0.4:
        return True
    return False


def _is_cancer_letter(text: str) -> bool:
    """Return True if the encounter references a letter from a cancer-relevant specialty."""
    if _has_keywords(text, LETTER_KEYWORDS):
        return True
    return bool(_CANCER_SPECIALTY_LETTER_RE.search(text))


def _is_cancer_relevant(text: str) -> bool:
    """Return True if encounter text has cancer-pathway keywords worth sending to LLM."""
    return (
        _has_keywords(text, EXCLUSION_KEYWORDS)
        or _has_keywords(text, SOFT_EXCLUSION_KEYWORDS)
        or _has_keywords(text, DIAGNOSIS_KEYWORDS)
        or _has_keywords(text, INVESTIGATION_KEYWORDS)
    )


# ---------------------------------------------------------------------------
# Neo4j queries
# ---------------------------------------------------------------------------

_FETCH_REFERRALS_QUERY = """\
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)-[d:DOCUMENTS]->(c)
WHERE toString(p.id) = $pid
  AND d.domain IN ['fast_track_referrals', 'seen_by_specialist']
RETURN toString(e.id) AS encounter_id,
       toString(e.date) AS encounter_date,
       c.name AS concept_name,
       d.domain AS domain
ORDER BY e.date
LIMIT 10
"""

_FETCH_POST_REFERRAL_ENCOUNTERS = """\
MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter)
WHERE toString(p.id) = $pid
  AND toString(e.date) >= $start_date
  AND toString(e.date) <= $end_date
RETURN toString(e.id) AS encounter_id,
       toString(e.date) AS encounter_date,
       e.text AS text,
       e.classification_content_type AS content_type
ORDER BY e.date
"""


def _fetch_post_referral_encounters(
    patient_client: Any,
    patient_id: str,
    referral_date: str,
    window_days: int,
) -> tuple[list[dict[str, Any]], str]:
    """Fetch encounters in the post-referral window. Returns (encounters, end_date)."""
    try:
        start_dt = datetime.strptime(referral_date[:10], "%Y-%m-%d")
    except ValueError:
        return [], referral_date
    end_dt = start_dt + timedelta(days=window_days)
    end_date = end_dt.strftime("%Y-%m-%d")

    rows = patient_client.run(
        _FETCH_POST_REFERRAL_ENCOUNTERS,
        pid=patient_id,
        start_date=referral_date[:10],
        end_date=end_date,
    )
    return [dict(r) for r in rows], end_date


def fetch_referrals(
    patient_client: Any,
    patient_id: str,
) -> list[dict[str, Any]]:
    """Find referral anchors for a patient from DOCUMENTS relationships."""
    rows = patient_client.run(_FETCH_REFERRALS_QUERY, pid=patient_id)
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# LLM classification
# ---------------------------------------------------------------------------


def _parse_llm_response(text: str) -> dict[str, Any]:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = _JSON_RE.search(text)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
    return {}


def _classify_encounter_llm(
    encounter_text: str,
    referral_date: str,
    referral_cancer_type: str,
    encounter_date: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Run 2-model consensus classification on a single encounter.

    Returns (result_a, result_b) dicts parsed from LLM JSON responses.
    """
    system_prompt = get_prompt("exclusion_detect", version=1)
    safe_text = deidentify_text(encounter_text[:3000])

    try:
        ref_dt = datetime.strptime(referral_date[:10], "%Y-%m-%d")
        enc_dt = datetime.strptime(encounter_date[:10], "%Y-%m-%d")
        days_since = (enc_dt - ref_dt).days
    except ValueError:
        days_since = -1

    user_msg = (
        f"REFERRAL CONTEXT:\n"
        f"- Patient was referred for: {referral_cancer_type}\n"
        f"- Referral date: {referral_date}\n"
        f"- This encounter date: {encounter_date}"
        f" ({days_since} days after referral)\n\n"
        f"ENCOUNTER TEXT:\n{safe_text}\n\n"
        f"Classify this encounter's relationship to the cancer referral pathway."
    )

    model_a = create_llm(provider="aws", tier="small")
    model_b = create_llm(provider="azure", tier="small")

    result_a = _call_model(model_a, system_prompt, user_msg, "aws_small")
    result_b = _call_model(model_b, system_prompt, user_msg, "azure_small")

    return result_a, result_b


def _call_model(
    client: Any,
    system: str,
    user_msg: str,
    label: str,
) -> dict[str, Any]:
    try:
        response: LLMResponse = client.converse(
            system=system,
            messages=[{"role": "user", "content": user_msg}],
            max_tokens=256,
            temperature=0.0,
        )
        return _parse_llm_response(response.text)
    except Exception:
        logger.warning("Exclusion model %s failed", label, exc_info=True)
        return {"outcome": "not_relevant", "confidence": 0.0}


def _consensus_outcome(
    result_a: dict[str, Any],
    result_b: dict[str, Any],
) -> EncounterOutcome:
    """Determine consensus from two model results."""
    outcome_a = result_a.get("outcome", "not_relevant")
    outcome_b = result_b.get("outcome", "not_relevant")

    if outcome_a not in VALID_OUTCOMES:
        outcome_a = "not_relevant"
    if outcome_b not in VALID_OUTCOMES:
        outcome_b = "not_relevant"

    if outcome_a == outcome_b:
        confidence = max(
            result_a.get("confidence", 0.5),
            result_b.get("confidence", 0.5),
        )
        method = "llm_consensus"
    else:
        # Disagreement: pick the more clinically significant one
        priority = [
            "cancer_excluded",
            "cancer_confirmed",
            "pending_letter",
            "still_investigating",
            "not_relevant",
        ]
        rank_a = priority.index(outcome_a) if outcome_a in priority else 99
        rank_b = priority.index(outcome_b) if outcome_b in priority else 99
        if rank_a <= rank_b:
            confidence = result_a.get("confidence", 0.5) * 0.7
        else:
            outcome_a, outcome_b = outcome_b, outcome_a
            confidence = result_b.get("confidence", 0.5) * 0.7
        method = "llm_single"

    winner = result_a if outcome_a == result_a.get("outcome") else result_b

    return EncounterOutcome(
        encounter_id="",
        encounter_date="",
        outcome=outcome_a,
        confidence=round(confidence, 3),
        evidence_text=winner.get("evidence_text", ""),
        reasoning=winner.get("reasoning", ""),
        detection_method=method,
        model_a_outcome=result_a.get("outcome", ""),
        model_b_outcome=result_b.get("outcome", ""),
    )


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def detect_exclusion(
    patient_id: str,
    referral_date: str,
    referral_cancer_type: str,
    patient_client: Any,
    window_days: int = DEFAULT_WINDOW_DAYS,
) -> ExclusionResult:
    """Detect cancer exclusion/confirmation in post-referral encounters.

    Fetches encounters in the [referral_date, referral_date + window_days]
    window, applies rule-based triage, then runs LLM 2-model consensus
    on clinically relevant encounters.
    """
    encounters, window_end = _fetch_post_referral_encounters(
        patient_client,
        patient_id,
        referral_date,
        window_days,
    )

    result = ExclusionResult(
        patient_id=patient_id,
        referral_date=referral_date,
        referral_cancer_type=referral_cancer_type,
        outcome="inconclusive",
        window_end=window_end,
        encounters_scanned=len(encounters),
    )

    if not encounters:
        logger.info(
            "detect_exclusion: patient=%s — no encounters in window", patient_id
        )
        return result

    for enc in encounters:
        enc_id = str(enc.get("encounter_id", ""))
        enc_date = str(enc.get("encounter_date", ""))
        text = str(enc.get("text") or "")
        content_type = enc.get("content_type") or ""

        if not text.strip() or _is_skip_encounter(text):
            result.encounters_skipped += 1
            continue

        # Rule-based: detect letters from cancer-relevant specialties
        is_letter = content_type == "document_transfer" or _is_cancer_letter(text)
        has_cancer_keywords = _is_cancer_relevant(text)

        if is_letter and not has_cancer_keywords:
            result.pending_letters.append(
                PendingLetter(
                    encounter_id=enc_id,
                    encounter_date=enc_date,
                    text_excerpt=text[:200],
                    detection_method="rule",
                )
            )
            result.encounter_outcomes.append(
                EncounterOutcome(
                    encounter_id=enc_id,
                    encounter_date=enc_date,
                    outcome="pending_letter",
                    confidence=0.8,
                    evidence_text=text[:100],
                    reasoning="Letter from cancer-relevant specialty detected by rule",
                    detection_method="rule",
                )
            )
            continue

        # Skip encounters with no cancer-pathway keywords
        if not has_cancer_keywords and not is_letter:
            result.encounters_skipped += 1
            continue

        # LLM classification
        logger.info(
            "detect_exclusion: patient=%s enc=%s date=%s — sending to LLM",
            patient_id,
            enc_id[:8],
            enc_date,
        )
        result_a, result_b = _classify_encounter_llm(
            text,
            referral_date,
            referral_cancer_type,
            enc_date,
        )
        enc_outcome = _consensus_outcome(result_a, result_b)
        enc_outcome.encounter_id = enc_id
        enc_outcome.encounter_date = enc_date
        enc_outcome.text_excerpt = text[:200]
        result.encounter_outcomes.append(enc_outcome)

        if enc_outcome.outcome == "pending_letter":
            result.pending_letters.append(
                PendingLetter(
                    encounter_id=enc_id,
                    encounter_date=enc_date,
                    text_excerpt=text[:200],
                    detection_method="llm",
                )
            )

    # Aggregate patient-level outcome
    result.outcome = _aggregate_outcome(result)
    result.confidence = _aggregate_confidence(result)
    return result


def _aggregate_outcome(result: ExclusionResult) -> str:
    """Determine patient-level outcome from individual encounter outcomes."""
    outcomes = {eo.outcome for eo in result.encounter_outcomes}

    has_excluded = "cancer_excluded" in outcomes
    has_confirmed = "cancer_confirmed" in outcomes

    if has_excluded and has_confirmed:
        return "conflicting"
    if has_excluded:
        return "cancer_excluded"
    if has_confirmed:
        return "cancer_confirmed"
    if result.pending_letters:
        return "pending_letter"
    if "still_investigating" in outcomes:
        return "still_investigating"
    return "inconclusive"


def _aggregate_confidence(result: ExclusionResult) -> float:
    """Pick the highest confidence from encounters matching the aggregated outcome."""
    if not result.encounter_outcomes:
        return 0.0
    matching = [
        eo.confidence
        for eo in result.encounter_outcomes
        if eo.outcome == result.outcome
    ]
    return max(matching) if matching else 0.0
