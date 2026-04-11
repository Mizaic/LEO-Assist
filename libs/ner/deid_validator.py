"""Strict de-identification validator for NER training records.

Two concerns:
1.  PHI leak detection  — scan text and metadata for patterns that survive
    de-identification (residual identifiers after deidentify_text() pass).
2.  Training record de-id enforcement — ensure no direct identifiers appear
    in the output JSONL fields (patient_id, encounter_id as raw values, etc.).

Usage
-----
    from libs.ner.deid_validator import DeIdValidator, DeIdIssue

    validator = DeIdValidator()
    issues = validator.check_record(record)
    if issues:
        # record has PHI leaks
        ...
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any

# ---------------------------------------------------------------------------
# Pattern catalogue (mirrors / extends libs/utils/deidentify.py patterns)
# ---------------------------------------------------------------------------

_NHS_RE = re.compile(r"\b\d{3}\s?\d{3}\s?\d{4}\b")
_POSTCODE_RE = re.compile(
    r"\b(?:GIR\s?0AA|[A-Z]{1,2}\d[A-Z\d]?\s?\d[A-Z]{2})\b", re.IGNORECASE
)
_PHONE_RE = re.compile(r"\b(?:\+44|0)\d[\d\s\-]{8,}\d\b")
_EMAIL_RE = re.compile(r"\b[\w.\-+]+@[\w.\-]+\.\w+\b", re.IGNORECASE)
_ADDRESS_RE = re.compile(
    r"\b\d+\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\s+"
    r"(?:Road|Street|Avenue|Lane|Drive|Close|Way|Place|Gardens?|Crescent|"
    r"Terrace|Grove|Court|Walk|Rise|Hill|Park|View|Mews|Square|Row|Boulevard)\b",
    re.IGNORECASE,
)
_DATE_SLASH_RE = re.compile(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b")
_DATE_DOT_RE = re.compile(r"\b\d{1,2}\.\d{1,2}\.\d{2,4}\b")
_DATE_ISO_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_DATE_NATURAL_RE = re.compile(
    r"\b\d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{2,4}\b",
    re.IGNORECASE,
)
_HONORIFIC_NAME_RE = re.compile(r"\b(?:Mr|Mrs|Ms|Miss|Dr|Prof)\s+[A-Z][a-zA-Z\-']+\b")
_NAME_ROLE_RE = re.compile(
    r"\b[A-Z][A-Z'\-]{2,},\s*[A-Z][a-zA-Z'\-]+(?:\s+[A-Z][a-zA-Z'\-]+)?\s*\([^)]+\bRole\)"
)
_CAPS_NAME_RE = re.compile(r"\b[A-Z][A-Z'\-]{2,},\s+[A-Z][a-zA-Z]{2,}\b")
# UUID-like patterns that might be raw Neo4j IDs leaked into text
_UUID_RE = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
    re.IGNORECASE,
)
# Raw numeric IDs > 8 digits (Neo4j node IDs, patient IDs etc.)
_RAW_NUMERIC_ID_RE = re.compile(r"\b\d{9,}\b")

# Placeholders that indicate the text was already de-identified — skip these spans
_PLACEHOLDER_RE = re.compile(
    r"\[(PERSON|ORGANISATION|DATE|ADDRESS|EMAIL|PHONE|POSTCODE|NHS_NUMBER|TITLE)\]"
)


def _strip_placeholders(text: str) -> str:
    """Remove placeholder tokens so they don't generate false PHI hits."""
    return _PLACEHOLDER_RE.sub("", text)


# ---------------------------------------------------------------------------
# Issue dataclass
# ---------------------------------------------------------------------------


@dataclass
class DeIdIssue:
    field: str  # which field triggered the issue
    issue_type: str  # e.g. "raw_patient_id", "residual_postcode"
    detail: str = ""  # matched snippet or explanation

    def to_dict(self) -> dict[str, str]:
        return {
            "field": self.field,
            "issue_type": self.issue_type,
            "detail": self.detail,
        }


# ---------------------------------------------------------------------------
# Hashing helpers (used when sanitising metadata)
# ---------------------------------------------------------------------------


def _hash_id(value: str, prefix: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}_{digest}"


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------


class DeIdValidator:
    """Checks a canonical NER record for PHI leaks."""

    def check_record(self, record: dict[str, Any]) -> list[DeIdIssue]:
        issues: list[DeIdIssue] = []
        issues.extend(self._check_metadata(record))
        text = str(record.get("text") or "")
        issues.extend(self._check_text(text, field="text"))
        for ent in record.get("entities", []):
            ent_text = str(ent.get("text") or "")
            issues.extend(
                self._check_text(
                    ent_text, field=f"entity.{ent.get('entity_id','?')}.text"
                )
            )
        return issues

    # ------------------------------------------------------------------
    def _check_metadata(self, record: dict[str, Any]) -> list[DeIdIssue]:
        issues: list[DeIdIssue] = []

        # patient_id / encounter_id must NOT be raw (unhashed) values
        pid = str(record.get("patient_id") or "")
        eid = str(record.get("encounter_id") or "")
        meta = record.get("metadata") or {}

        if pid and not pid.startswith("pat_"):
            issues.append(DeIdIssue("patient_id", "raw_patient_id", pid[:30]))
        if eid and not eid.startswith(("enc_", "doc_", "e_")):
            issues.append(DeIdIssue("encounter_id", "raw_encounter_id", eid[:30]))

        encounter_date = str(
            meta.get("encounter_date") or record.get("encounter_date") or ""
        )
        if encounter_date and len(encounter_date) > 4 and "-" in encounter_date:
            # Tolerate YYYY-01-01 (year-rounded) but not YYYY-MM-DD exact dates
            parts = encounter_date.split("-")
            if len(parts) == 3 and (parts[1] != "01" or parts[2] != "01"):
                issues.append(
                    DeIdIssue("encounter_date", "exact_encounter_date", encounter_date)
                )

        # Check for leaked UUIDs or long numeric IDs in metadata values
        for k, v in meta.items():
            if k.startswith("_"):
                continue
            v_str = str(v)
            if _UUID_RE.search(v_str):
                issues.append(DeIdIssue(f"metadata.{k}", "uuid_leak", v_str[:40]))
            if _RAW_NUMERIC_ID_RE.search(v_str) and k not in (
                "encounter_year",
                "annotation_date",
            ):
                issues.append(DeIdIssue(f"metadata.{k}", "numeric_id_leak", v_str[:40]))

        return issues

    # ------------------------------------------------------------------
    def _check_text(self, text: str, field: str) -> list[DeIdIssue]:
        issues: list[DeIdIssue] = []
        if not text:
            return issues
        clean = _strip_placeholders(text)

        # Import the facility pattern from the canonical source so it stays in sync.
        from libs.utils.deidentify import FACILITY_NAME_RE as _FACILITY_RE

        checks: list[tuple[re.Pattern[str], str]] = [
            (_NHS_RE, "nhs_number"),
            (_POSTCODE_RE, "postcode"),
            (_PHONE_RE, "phone"),
            (_EMAIL_RE, "email"),
            (_ADDRESS_RE, "address"),
            (_DATE_SLASH_RE, "date_dmy_slash"),
            (_DATE_DOT_RE, "date_dmy_dot"),
            (_DATE_ISO_RE, "date_iso"),
            (_DATE_NATURAL_RE, "date_natural"),
            (_HONORIFIC_NAME_RE, "honorific_name"),
            (_NAME_ROLE_RE, "systmone_name_role"),
            (_CAPS_NAME_RE, "caps_surname_firstname"),
            (_FACILITY_RE, "facility_name"),
        ]
        for pattern, issue_type in checks:
            m = pattern.search(clean)
            if m:
                issues.append(DeIdIssue(field, issue_type, m.group(0)[:60]))
        return issues


# ---------------------------------------------------------------------------
# Record sanitiser (upgrades metadata to training-safe form)
# ---------------------------------------------------------------------------


def sanitise_record_metadata(record: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of record with identifying metadata fields hashed/rounded.

    Does NOT modify text — run deidentify_text() on text before calling this.
    """
    out = dict(record)
    meta = dict(out.get("metadata") or {})

    # Hash raw IDs retained for provenance linkage
    pid = str(out.pop("patient_id", "") or "")
    eid = str(out.pop("encounter_id", "") or "")
    if pid:
        meta["_hashed_patient_id"] = _hash_id(pid, "pat")
    if eid:
        meta["_hashed_encounter_id"] = _hash_id(eid, "enc")

    # Round encounter date to year only
    encounter_date = str(
        out.pop("encounter_date", "") or meta.pop("encounter_date", "") or ""
    )
    if encounter_date:
        meta["encounter_year"] = encounter_date[:4]

    out["metadata"] = meta
    return out
