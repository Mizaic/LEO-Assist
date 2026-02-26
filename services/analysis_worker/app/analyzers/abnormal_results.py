"""Abnormal / incomplete test results detector.

Scans coded encounters for observable entities (lab results, vitals)
that are flagged as abnormal or outside reference ranges, and checks
for follow-up actions.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

_ABNORMAL_PATTERNS = re.compile(
    r"(?i)(?:outside\s+reference\s+range|abnormal|high|low|critical|"
    r"above\s+(?:upper|normal)|below\s+(?:lower|normal))"
)

_FOLLOWUP_PATTERNS = re.compile(
    r"(?i)(?:repeat|recheck|monitor|review|follow.?up|re-?test)"
)


def detect_abnormal_results(
    patient_id: str,
    start_date: str,
    end_date: str,
    patient_client,
) -> List[Dict[str, Any]]:
    """Find abnormal results lacking documented follow-up."""
    encounters = patient_client.run(
        "MATCH (p:Patient)-[:HAS_ENCOUNTER]->(e:Encounter) "
        "WHERE toString(p.id) = $pid AND toString(e.date) >= $s AND toString(e.date) <= $e "
        "RETURN e.id AS encounter_id, e.text AS text, toString(e.date) AS date "
        "ORDER BY e.date",
        pid=patient_id, s=start_date, e=end_date,
    )

    flagged: list[dict[str, Any]] = []
    for enc in encounters:
        text = str(enc.get("text", ""))
        if not text:
            continue
        if _ABNORMAL_PATTERNS.search(text):
            has_followup = bool(_FOLLOWUP_PATTERNS.search(text))
            if not has_followup:
                flagged.append({
                    "encounter_id": str(enc.get("encounter_id", "")),
                    "date": enc.get("date", ""),
                    "description": "Abnormal result without documented follow-up action",
                    "severity": "warning",
                })

    return flagged
