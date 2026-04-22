"""Result-channel signal extractor.

Atlas trace:
  DI: DI-8A5FCF4F

REAL implementation for breast (mammography / biopsy / ultrasound
results). Other sites silently skip.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from ..site_keys import SITE_BREAST
from ..types import Signal, TimelineEvent


_BREAST_INVESTIGATION_TERMS = re.compile(
    r"\b(mammogra|breast ultrasound|breast biopsy|core biopsy of breast|"
    r"fine needle aspiration of breast|breast mri)\b",
    re.IGNORECASE,
)
_BREAST_OBS_CODES = frozenset(
    {
        "169068008",  # Mammography
        "722164000",  # Ultrasound of breast
        "439470001",  # Biopsy of breast
    }
)
_POSITIVE_TERMS = re.compile(
    r"\b(malignant|carcinoma|invasive|dcis|positive for malignancy)\b",
    re.IGNORECASE,
)
_NEGATIVE_TERMS = re.compile(
    r"\b(benign|no malignancy|no abnormality|normal|negative)\b",
    re.IGNORECASE,
)


def _is_breast_investigation(observation: dict) -> bool:
    code = str(observation.get("observation_code") or "")
    if code in _BREAST_OBS_CODES:
        return True
    value = str(observation.get("value") or "")
    return bool(_BREAST_INVESTIGATION_TERMS.search(value))


def _classify_value(observation: dict) -> tuple[str, float] | None:
    value = str(observation.get("value") or "")
    interpretation = str(observation.get("interpretation") or "")
    blob = f"{value} {interpretation}"
    if _POSITIVE_TERMS.search(blob):
        return "confirmed", 0.90
    if _NEGATIVE_TERMS.search(blob):
        return "ruled_out", 0.80
    return None


def extract_result_signals(events: Iterable[TimelineEvent]) -> list[Signal]:
    out: list[Signal] = []
    for event in events:
        for observation in event.observation_results:
            if not _is_breast_investigation(observation):
                continue
            classification = _classify_value(observation)
            if classification is None:
                continue
            intent, confidence = classification
            out.append(
                Signal(
                    channel="result",
                    encounter_id=event.encounter_id,
                    site_key=SITE_BREAST,
                    role="investigation",
                    intent=intent,
                    confidence=confidence,
                    citation=(
                        f"Investigation result "
                        f"{observation.get('observation_code') or 'unknown code'}"
                    ),
                )
            )
    return out
