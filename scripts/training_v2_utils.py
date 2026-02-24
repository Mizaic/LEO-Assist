"""Utilities for audit-grade encounter candidate generation (v2).

This module is deterministic by default:
- de-identification and leak checks
- payload hashing
- schema/offset validation gates
- append-only audit event helpers
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


EMAIL_RE = re.compile(r"\b[\w.\-+]+@[\w.\-]+\.\w+\b", re.IGNORECASE)
PHONE_RE = re.compile(r"\b(?:\+44|0)\d[\d\s\-]{8,}\d\b")
NHS_RE = re.compile(r"\b\d{3}\s?\d{3}\s?\d{4}\b")
POSTCODE_RE = re.compile(
    r"\b(?:GIR\s?0AA|[A-Z]{1,2}\d[A-Z\d]?\s?\d[A-Z]{2})\b", re.IGNORECASE
)
NAME_STYLE_RE = re.compile(
    r"\b[A-Z][A-Z\-']+,\s*[A-Z][a-zA-Z\-']+\s*\((?:Mr|Mrs|Ms|Miss|Dr|Prof)\)"
)
HONORIFIC_NAME_RE = re.compile(
    r"\b(?:Mr|Mrs|Ms|Miss|Dr|Prof)\s+[A-Z][a-zA-Z\-']+\b"
)

DATE_SLASH_RE = re.compile(r"\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b")
DATE_DOT_RE = re.compile(r"\b\d{1,2}\.\d{1,2}\.\d{2,4}\b")
DATE_ISO_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")


ALLOWED_SUBJECTS = {"patient", "family", "other"}
ALLOWED_TEMPORALITY = {"present", "past", "planned", "hypothetical", "unknown"}


@dataclass(frozen=True)
class GateResult:
    hard_fails: list[str]
    warnings: list[str]


def iso_now() -> str:
    return datetime.now(UTC).isoformat()


def stable_hash(payload: Any) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def deidentify_text(text: str) -> str:
    out = text
    out = NAME_STYLE_RE.sub("[PERSON]", out)
    out = HONORIFIC_NAME_RE.sub("[PERSON]", out)
    out = EMAIL_RE.sub("[EMAIL]", out)
    out = PHONE_RE.sub("[PHONE]", out)
    out = NHS_RE.sub("[NHS_NUMBER]", out)
    out = POSTCODE_RE.sub("[POSTCODE]", out)
    out = DATE_SLASH_RE.sub("[DATE]", out)
    out = DATE_DOT_RE.sub("[DATE]", out)
    out = DATE_ISO_RE.sub("[DATE]", out)
    return out


def detect_phi_leaks(text: str) -> list[str]:
    leaks: list[str] = []
    if EMAIL_RE.search(text):
        leaks.append("email_pattern_detected")
    if PHONE_RE.search(text):
        leaks.append("phone_pattern_detected")
    if NHS_RE.search(text):
        leaks.append("nhs_number_pattern_detected")
    if POSTCODE_RE.search(text):
        leaks.append("postcode_pattern_detected")
    if NAME_STYLE_RE.search(text) or HONORIFIC_NAME_RE.search(text):
        leaks.append("name_pattern_detected")
    if DATE_ISO_RE.search(text):
        leaks.append("exact_date_pattern_detected")
    return leaks


def build_audit_event(
    *,
    event_type: str,
    actor: str,
    reason: str,
    before_payload: Any,
    after_payload: Any,
    version_bundle: dict[str, str],
) -> dict[str, Any]:
    return {
        "event_type": event_type,
        "actor": actor,
        "reason": reason,
        "timestamp": iso_now(),
        "before_hash": stable_hash(before_payload),
        "after_hash": stable_hash(after_payload),
        "version_bundle": version_bundle,
    }


def _validate_term(
    term: dict[str, Any],
    sentence_text: str,
    *,
    sentence_start: int,
    sentence_end: int,
    deidentified_text: str,
) -> GateResult:
    hard_fails: list[str] = []
    warnings: list[str] = []
    required = {
        "text",
        "span_start",
        "span_end",
        "context",
    }
    missing = required.difference(term.keys())
    if missing:
        return GateResult([f"term_missing_fields:{sorted(missing)}"], warnings)

    t_text = str(term.get("text", ""))
    start = term.get("span_start")
    end = term.get("span_end")
    if not isinstance(start, int) or not isinstance(end, int):
        hard_fails.append("term_span_not_int")
        return GateResult(hard_fails, warnings)
    # Accept legacy sentence-relative offsets and current document-global offsets.
    relative_valid = start >= 0 and end > start and end <= len(sentence_text)
    absolute_valid = (
        start >= sentence_start
        and end <= sentence_end
        and start >= 0
        and end > start
        and end <= len(deidentified_text)
    )
    if not relative_valid and not absolute_valid:
        hard_fails.append("term_span_out_of_range")
        return GateResult(hard_fails, warnings)

    span_text = sentence_text[start:end] if relative_valid else deidentified_text[start:end]
    if span_text.strip() != t_text.strip():
        hard_fails.append("term_text_span_mismatch")

    ctx = term.get("context", {})
    if not isinstance(ctx, dict):
        hard_fails.append("term_context_not_object")
        return GateResult(hard_fails, warnings)

    for key in ("negated", "uncertain", "historical"):
        if not isinstance(ctx.get(key), bool):
            hard_fails.append(f"context_{key}_not_bool")
    subject = ctx.get("subject")
    if subject not in ALLOWED_SUBJECTS:
        hard_fails.append("context_subject_invalid")
    temporality = ctx.get("temporality")
    if temporality not in ALLOWED_TEMPORALITY:
        hard_fails.append("context_temporality_invalid")

    if ctx.get("historical") and temporality == "present":
        warnings.append("historical_true_with_present_temporality")
    if ctx.get("negated") and temporality == "planned":
        warnings.append("negated_with_planned_temporality")

    return GateResult(hard_fails, warnings)


def validate_encounter_payload(encounter_payload: dict[str, Any]) -> GateResult:
    hard_fails: list[str] = []
    warnings: list[str] = []

    required_root = {
        "patient_id",
        "encounter_id",
        "date",
        "source_hash",
        "deidentified_hash",
        "deidentified_text",
        "sentences",
        "approval_status",
        "audit_events",
    }
    missing_root = required_root.difference(encounter_payload.keys())
    if missing_root:
        return GateResult([f"root_missing_fields:{sorted(missing_root)}"], warnings)

    leaks = detect_phi_leaks(str(encounter_payload.get("deidentified_text", "")))
    for leak in leaks:
        hard_fails.append(f"deid_leak:{leak}")

    deidentified_text = str(encounter_payload.get("deidentified_text", ""))
    sentences = encounter_payload.get("sentences", [])
    if not isinstance(sentences, list):
        return GateResult(["sentences_not_list"], warnings)

    for sent in sentences:
        if not isinstance(sent, dict):
            hard_fails.append("sentence_not_object")
            continue
        s_required = {"sentence_id", "text", "start", "end", "terms"}
        s_missing = s_required.difference(sent.keys())
        if s_missing:
            hard_fails.append(f"sentence_missing_fields:{sorted(s_missing)}")
            continue
        text = str(sent.get("text", ""))
        start = sent.get("start")
        end = sent.get("end")
        if not isinstance(start, int) or not isinstance(end, int):
            hard_fails.append("sentence_span_not_int")
        elif start < 0 or end <= start:
            hard_fails.append("sentence_span_invalid")
        terms = sent.get("terms", [])
        if not isinstance(terms, list):
            hard_fails.append("sentence_terms_not_list")
            continue
        for term in terms:
            res = _validate_term(
                term,
                text,
                sentence_start=start if isinstance(start, int) else 0,
                sentence_end=end if isinstance(end, int) else 0,
                deidentified_text=deidentified_text,
            )
            hard_fails.extend(res.hard_fails)
            warnings.extend(res.warnings)

    if encounter_payload.get("approval_status") != "pending":
        warnings.append("approval_status_not_pending")

    audit_events = encounter_payload.get("audit_events", [])
    if not isinstance(audit_events, list) or not audit_events:
        hard_fails.append("audit_events_missing")
    else:
        for event in audit_events:
            if not isinstance(event, dict):
                hard_fails.append("audit_event_not_object")
                continue
            for key in (
                "event_type",
                "actor",
                "reason",
                "timestamp",
                "before_hash",
                "after_hash",
                "version_bundle",
            ):
                if key not in event:
                    hard_fails.append(f"audit_event_missing_{key}")

    return GateResult(hard_fails, warnings)
