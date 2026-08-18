"""Build a redacted Atlas ticket from a pipeline issue signature.

Atlas trace:
  DO: DO-AA3B7FCC
  DI: DI-9456E5BE
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-AA3B7FCC")

Atlas: DI-C7DEF132
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any

from libs.atlas_qms.ncr_shape import NCR_CLOSED_STATUSES

SIG_PREFIX = "LEO-PH"
_DIGIT_RUN = re.compile(r"\d{6,}")
_ID_WORDS = re.compile(r"\b(nhs|patient|mrn|nhsnumber)\b", re.I)
CLOSED_STATUSES = NCR_CLOSED_STATUSES


@dataclass(frozen=True)
class IssueSignal:
    family: str
    key: str
    count: int
    gate: str
    severity: str = "minor"
    tag: str = ""


def signature_for(family: str, key: str) -> str:
    token = hashlib.sha256(f"{family}|{key}".encode("utf-8")).hexdigest()[:12]
    return f"{SIG_PREFIX}|{family}|{token}"


def has_blocked_text(text: str) -> bool:
    raw = text or ""
    return bool(_DIGIT_RUN.search(raw) or _ID_WORDS.search(raw))


def safe_label(text: str, limit: int = 40) -> str:
    clean = " ".join((text or "").split())
    if not clean or has_blocked_text(clean):
        return ""
    return clean[:limit]


def ncr_title(signal: IssueSignal) -> str:
    token = signature_for(signal.family, signal.key).rsplit("|", 1)[-1]
    return f"LEO phone-home: {signal.family} [{token}]"


def ncr_description(signal: IssueSignal) -> str:
    sig = signature_for(signal.family, signal.key)
    parts = [
        "Repeated pipeline issue.",
        f"Family: {signal.family}.",
        f"Seen: {signal.count} times.",
        f"Gate: {signal.gate}.",
        f"Signature: {sig}.",
    ]
    tag = safe_label(signal.tag, 32)
    if tag:
        parts.append(f"Tag: {tag}.")
    label = safe_label(signal.key)
    if label:
        parts.append(f"Key: {label}.")
    parts.append("No person identifiers.")
    return " ".join(parts)


def find_open_ncr(rows: list[dict[str, Any]], signature: str) -> dict[str, Any] | None:
    for row in rows:
        hay = f"{row.get('title', '')} {row.get('description', '')}"
        if signature not in hay:
            continue
        status = str(row.get("status") or "").lower()
        if status in CLOSED_STATUSES:
            continue
        return row
    return None
