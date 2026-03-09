from __future__ import annotations

import re
from typing import Any

_ABNORMAL_PATTERNS = (
    re.compile(r"\babnormal\b", re.I),
    re.compile(r"\babove upper normal range\b", re.I),
    re.compile(r"\bbelow\b.*\brange\b", re.I),
    re.compile(r"\bcritically low\b", re.I),
    re.compile(r"\bcritical\b", re.I),
    re.compile(r"\bseverely reduced\b", re.I),
)
_FOLLOW_UP_PATTERNS = (
    re.compile(r"\brepeat\b", re.I),
    re.compile(r"\bmonitor\b", re.I),
    re.compile(r"\bfollow[- ]?up\b", re.I),
)


def detect_abnormal_results(
    patient_id: str,
    start_date: str,
    end_date: str,
    patient_client,
) -> list[dict[str, Any]]:
    rows = list(
        patient_client.run(
            "MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter) RETURN e",
            patient_id=patient_id,
            start_date=start_date,
            end_date=end_date,
        )
        or []
    )
    findings: list[dict[str, Any]] = []
    for row in rows:
        text = str(row.get("text") or "").strip()
        if not text:
            continue
        if not any(pattern.search(text) for pattern in _ABNORMAL_PATTERNS):
            continue
        if any(pattern.search(text) for pattern in _FOLLOW_UP_PATTERNS):
            continue
        findings.append(
            {
                "patient_id": patient_id,
                "encounter_id": row.get("encounter_id"),
                "date": row.get("date"),
                "severity": "critical" if re.search(r"\bcritical|critically low\b", text, re.I) else "warning",
                "description": text,
            }
        )
    return findings
