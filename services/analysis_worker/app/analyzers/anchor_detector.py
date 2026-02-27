"""Anchor detection: finds referral, diagnosis, and treatment anchors.

Ported from VRB clinical-ai/app/agent/subagents/anchor_detector.py.
Two-pass approach: coded concepts first, then text-based regex fallback.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_FAST_TRACK_RE = re.compile(
    r"(?i)fast\s*track\s*referral\s+for\s+suspected\s+(\S[\w\s()]+?)(?:\s*\(|$)"
)
_2WW_RE = re.compile(
    r"(?i)(?:2ww|two\s*week\s*wait|2\s*week\s*wait)\s+(?:referral\s+)?(?:to\s+)?(\w[\w\s]*?)(?:\s*[-.]|$)"
)
_CANCER_TYPE_MAP = {
    "lower gi": "lower gastrointestinal",
    "upper gi": "upper GI",
    "colorectal": "colorectal",
    "bowel": "colorectal",
    "breast": "breast",
    "lung": "lung",
    "skin": "skin",
    "urolog": "urological",
    "gynae": "gynaecological",
    "haematol": "haematology",
    "head and neck": "head and neck",
}
_DIAGNOSIS_STRUCTURE_RE = re.compile(
    r"(?i)(?:"
    r"biopsy\s+(?:confirmed|shows?|revealed)\s+(\S[\w\s]+?)(?:\s*[-.,;(]|$)"
    r"|diagnosed?\s+(?:with|as)\s+(\S[\w\s]+?)(?:\s*[-.,;(]|$)"
    r"|MDT\s+(?:confirmed|outcome)\s*:?\s*(\S[\w\s]+?)(?:\s*[-.,;(]|$)"
    r")"
)


@dataclass
class AnchorResult:
    patient_id: str
    referral_anchors: List[Dict[str, Any]] = field(default_factory=list)
    diagnosis_anchors: List[Dict[str, Any]] = field(default_factory=list)
    treatment_anchors: List[Dict[str, Any]] = field(default_factory=list)
    earliest_date: Optional[str] = None
    latest_date: Optional[str] = None
    expanded_start: Optional[str] = None
    expanded_end: Optional[str] = None
    expanded_encounters: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def has_referral(self) -> bool:
        return len(self.referral_anchors) > 0


def detect_anchors(
    patient_id: str,
    start_date: str,
    end_date: str,
    patient_client,
    expand_months: int = 3,
) -> AnchorResult:
    result = AnchorResult(patient_id=patient_id)

    encounters = _fetch_encounters_with_text(patient_id, start_date, end_date, patient_client)

    for enc in encounters:
        text = enc.get("text") or ""
        enc_id = str(enc.get("encounter_id", ""))
        enc_date = str(enc.get("date", ""))

        condition_type = _detect_referral_in_text(text)
        if condition_type:
            result.referral_anchors.append({
                "encounter_id": enc_id,
                "encounter_date": enc_date,
                "concept_name": f"Fast track referral for suspected {condition_type} cancer",
                "source": "text_search",
            })

        if _DIAGNOSIS_STRUCTURE_RE.search(text):
            m = _DIAGNOSIS_STRUCTURE_RE.search(text)
            matched = next((g for g in m.groups() if g), "unknown") if m else "unknown"
            result.diagnosis_anchors.append({
                "encounter_id": enc_id,
                "encounter_date": enc_date,
                "concept_name": matched.strip(),
                "source": "text_search",
            })

    _expand_window(patient_id, expand_months, result, patient_client)
    return result


def _fetch_encounters_with_text(patient_id, start_date, end_date, client):
    return client.run(
        "MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter) "
        "WHERE toString(p.id) = $pid AND toString(e.date) >= $start AND toString(e.date) <= $end "
        "RETURN e.id AS encounter_id, toString(e.date) AS date, e.text AS text "
        "ORDER BY e.date",
        pid=patient_id, start=start_date, end=end_date,
    )


def _detect_referral_in_text(text: str) -> Optional[str]:
    m = _FAST_TRACK_RE.search(text)
    if m:
        return _normalise_condition_type(m.group(1).strip())
    m = _2WW_RE.search(text)
    if m:
        return _normalise_condition_type(m.group(1).strip())
    return None


def _normalise_condition_type(raw: str) -> str:
    low = raw.lower().rstrip(".")
    for keyword, standard in _CANCER_TYPE_MAP.items():
        if keyword in low:
            return standard
    return raw.split("(")[0].strip() if raw else "unknown"


def _expand_window(patient_id, expand_months, result, client):
    all_dates = []
    for anchors in [result.referral_anchors, result.diagnosis_anchors, result.treatment_anchors]:
        for a in anchors:
            d = a.get("encounter_date", "")
            if d:
                all_dates.append(d[:10])
    if not all_dates:
        return
    all_dates.sort()
    result.earliest_date = all_dates[0]
    result.latest_date = all_dates[-1]
    try:
        earliest = datetime.strptime(result.earliest_date, "%Y-%m-%d")
        latest = datetime.strptime(result.latest_date, "%Y-%m-%d")
        result.expanded_start = (earliest - timedelta(days=expand_months * 30)).strftime("%Y-%m-%d")
        result.expanded_end = (latest + timedelta(days=expand_months * 30)).strftime("%Y-%m-%d")
    except ValueError:
        pass
