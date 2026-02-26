"""Post-processing rules engine applied after LLM extraction.

Rules are derived from reviewer correction patterns on approved encounters.
Each rule returns a modified candidate dict (terms added, removed, or flagged).
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Rule result tracking
# ---------------------------------------------------------------------------

@dataclass
class RuleAction:
    rule_id: str
    action: str  # "strip_all", "remove_term", "add_term", "dedup", "auto_approve"
    detail: str


@dataclass
class PostProcessResult:
    actions: list[RuleAction] = field(default_factory=list)
    auto_approve: bool = False
    terms_removed: int = 0
    terms_added: int = 0


# ---------------------------------------------------------------------------
# Admin / boilerplate detection patterns
# ---------------------------------------------------------------------------

_ADMIN_ONLY_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"^Dear\b.*\bappointment has been booked\b", re.IGNORECASE | re.DOTALL),
    re.compile(r"^\*\*\s*Care (started|ended)\b", re.IGNORECASE),
    re.compile(r"^(Confirmation|Reminder) of appointment\b", re.IGNORECASE),
    re.compile(r"^see sick note\s+https?://", re.IGNORECASE),
    re.compile(r"SystmOne (Incoming|Outgoing) Record Sharing", re.IGNORECASE),
    re.compile(r"Activity:\s*Record Keeping", re.IGNORECASE),
    re.compile(r"Identity Verification", re.IGNORECASE),
    re.compile(r"^Admission to\b.*NHS Trust", re.IGNORECASE),
    re.compile(r"Summary Care Record Update", re.IGNORECASE),
]

_ADMIN_HEADER_PATTERN = re.compile(
    r"^(?:\d{2}:\d{2}\s*-\s*)?"
    r"(?:Surgery|Office Base|Patient's Home|Clinic):\s*"
    r"[A-Z][A-Za-z',\- ]+\([^)]*(?:Receptionist|Admin|Clerical|Medical Secretary)[^)]*\)",
    re.IGNORECASE,
)

_NO_CLINICAL_CONTENT = re.compile(
    r"^[\s\S]{0,500}$"
)


def _is_admin_only(text: str) -> bool:
    """Return True if the encounter text is purely administrative."""
    for pat in _ADMIN_ONLY_PATTERNS:
        if pat.search(text):
            return True
    return False


def _is_admin_header_no_clinical(text: str) -> bool:
    """Admin-header encounter with no real clinical content below."""
    if not _ADMIN_HEADER_PATTERN.match(text):
        return False
    clean = _ADMIN_HEADER_PATTERN.sub("", text).strip()
    clean = re.sub(r"Entered at:.*?(?:\n|$)", "", clean).strip()
    clean = re.sub(r"N\+S Encounter type.*?(?:\n|$)", "", clean).strip()
    clean = re.sub(r"\*Reason for contact.*?(?:\n|$)", "", clean).strip()
    clean = re.sub(r"Entered By:.*?(?:\n|$)", "", clean).strip()
    clean = re.sub(r",\s*Entered By:.*", "", clean).strip()
    if len(clean) < 20:
        return True
    return False


# ---------------------------------------------------------------------------
# Document-type auto-coding rules
# ---------------------------------------------------------------------------

@dataclass
class DocumentRule:
    pattern: re.Pattern[str]
    codes: list[dict[str, Any]]


_DOCUMENT_RULES: list[DocumentRule] = [
    DocumentRule(
        pattern=re.compile(r"Hospital Discharge Letter\b.*\bto\b", re.IGNORECASE),
        codes=[
            {
                "snomed_concept_id": "911911000000100",
                "snomed_term": "Hospital discharge letter received (finding)",
                "semantic_tag": "finding",
            },
            {
                "snomed_concept_id": "823701000000103",
                "snomed_term": "Discharge letter (record artifact)",
                "semantic_tag": "record artifact",
            },
        ],
    ),
    DocumentRule(
        pattern=re.compile(r"NHS 111 Service\b.*\bto\b", re.IGNORECASE),
        codes=[
            {
                "snomed_concept_id": "819551000000100",
                "snomed_term": "National Health Service 111 Report (record artifact)",
                "semantic_tag": "record artifact",
            },
        ],
    ),
    DocumentRule(
        pattern=re.compile(r"NHS 111 report received\b", re.IGNORECASE),
        codes=[
            {
                "snomed_concept_id": "887641000000105",
                "snomed_term": "National Health Service 111 report received (finding)",
                "semantic_tag": "finding",
            },
        ],
    ),
    DocumentRule(
        pattern=re.compile(r"\bA&E\b.*\bto\b", re.IGNORECASE),
        codes=[
            {
                "snomed_concept_id": "24561000000109",
                "snomed_term": "Accident and emergency report (record artifact)",
                "semantic_tag": "record artifact",
            },
        ],
    ),
    DocumentRule(
        pattern=re.compile(r"Urgent Care Centre\b.*\bto\b", re.IGNORECASE),
        codes=[
            {
                "snomed_concept_id": "312341000000104",
                "snomed_term": "Urgent Care Summary Report - FocusActOrEvent (record artifact)",
                "semantic_tag": "record artifact",
            },
        ],
    ),
    DocumentRule(
        pattern=re.compile(
            r"(?:Colorectal|Urology|Cardiology|Gastroenterology|Orthopaedic|Respiratory|"
            r"Dermatology|Rheumatology|Neurology|Oncology|ENT|Ophthalmology|Gynaecology|"
            r"Haematology|Endocrinology|Nephrology|Vascular|Pain Management|Palliative Care)"
            r"\b.*\bto\b.*Medical Centre",
            re.IGNORECASE,
        ),
        codes=[
            {
                "snomed_concept_id": "911951000000101",
                "snomed_term": "Outpatient clinic letter received (finding)",
                "semantic_tag": "finding",
            },
            {
                "snomed_concept_id": "823691000000103",
                "snomed_term": "Clinical letter (record artifact)",
                "semantic_tag": "record artifact",
            },
        ],
    ),
]


def _match_document_rule(text: str) -> DocumentRule | None:
    for rule in _DOCUMENT_RULES:
        if rule.pattern.search(text):
            return rule
    return None


def _build_auto_term(
    evidence: str,
    code: dict[str, Any],
    sentence_id: str,
    span_start: int,
    span_end: int,
    term_idx: int,
) -> dict[str, Any]:
    return {
        "term_id": f"{sentence_id}_auto{term_idx}",
        "text": evidence,
        "lookup_term": code["snomed_term"],
        "span_start": span_start,
        "span_end": span_end,
        "context": {
            "negated": False,
            "uncertain": False,
            "historical": False,
            "subject": "patient",
            "temporality": "present",
        },
        "coding": {
            "snomed_concept_id": code["snomed_concept_id"],
            "read_code": None,
            "snomed_term": code["snomed_term"],
            "score": 0.95,
            "source": "auto_rule",
        },
        "semantic_tag": code.get("semantic_tag", "finding"),
        "evidence_text": evidence,
        "extraction_method": "post_processing_rule",
        "extraction_confidence": 0.95,
    }


# ---------------------------------------------------------------------------
# Main rules engine
# ---------------------------------------------------------------------------

def apply_rules(candidate: dict[str, Any]) -> PostProcessResult:
    """Apply all post-processing rules to a candidate. Mutates in place."""
    result = PostProcessResult()
    text = candidate.get("deidentified_text") or candidate.get("source_text") or ""
    sentences = candidate.get("sentences", [])

    # Rule 1: Admin-only encounters → strip all LLM terms and auto-approve
    if _is_admin_only(text) or _is_admin_header_no_clinical(text):
        total_stripped = 0
        for sent in sentences:
            count = len(sent.get("terms", []))
            if count > 0:
                sent["terms"] = []
                total_stripped += count
        if total_stripped > 0:
            result.actions.append(RuleAction(
                rule_id="admin_strip",
                action="strip_all",
                detail=f"Stripped {total_stripped} terms from admin-only encounter",
            ))
            result.terms_removed += total_stripped

        # Check for document-type auto-coding even on admin encounters
        doc_rule = _match_document_rule(text)
        if doc_rule:
            _apply_document_codes(candidate, doc_rule, result)
        else:
            result.auto_approve = True
            result.actions.append(RuleAction(
                rule_id="admin_auto_approve",
                action="auto_approve",
                detail="Admin-only encounter with no clinical content",
            ))
        return result

    # Rule 2: Document-type auto-coding
    doc_rule = _match_document_rule(text)
    if doc_rule:
        # Strip any LLM-extracted terms (these doc encounters rarely have clinical content)
        total_stripped = 0
        for sent in sentences:
            count = len(sent.get("terms", []))
            if count > 0:
                sent["terms"] = []
                total_stripped += count
        if total_stripped > 0:
            result.actions.append(RuleAction(
                rule_id="doc_strip",
                action="strip_all",
                detail=f"Stripped {total_stripped} LLM terms from document-transfer encounter",
            ))
            result.terms_removed += total_stripped
        _apply_document_codes(candidate, doc_rule, result)

    # Rule 3: Remove abbreviations that are substrings of a longer term's parenthetical
    _remove_parenthetical_abbrev_dupes(candidate, result)

    # Rule 4: Deduplication — remove duplicate concept_ids within the encounter
    _dedup_terms(candidate, result)

    return result


def _apply_document_codes(
    candidate: dict[str, Any],
    doc_rule: DocumentRule,
    result: PostProcessResult,
) -> None:
    text = candidate.get("deidentified_text") or ""
    sentences = candidate.get("sentences", [])
    if not sentences:
        sentences = [{
            "sentence_id": "s0",
            "start": 0,
            "end": len(text),
            "text": text,
            "section": None,
            "terms": [],
        }]
        candidate["sentences"] = sentences

    target_sent = sentences[0]
    evidence_match = doc_rule.pattern.search(text)
    evidence = evidence_match.group(0) if evidence_match else text[:60]
    span_start = evidence_match.start() if evidence_match else 0
    span_end = evidence_match.end() if evidence_match else min(60, len(text))

    existing_concepts = set()
    for sent in sentences:
        for term in sent.get("terms", []):
            cid = term.get("coding", {}).get("snomed_concept_id")
            if cid:
                existing_concepts.add(cid)

    added = 0
    for idx, code in enumerate(doc_rule.codes):
        if code["snomed_concept_id"] in existing_concepts:
            continue
        term = _build_auto_term(
            evidence=evidence,
            code=code,
            sentence_id=target_sent["sentence_id"],
            span_start=span_start,
            span_end=span_end,
            term_idx=idx,
        )
        target_sent["terms"].append(term)
        added += 1

    if added:
        result.terms_added += added
        result.actions.append(RuleAction(
            rule_id="doc_auto_code",
            action="add_term",
            detail=f"Auto-added {added} document-type codes",
        ))


_PAREN_ABBREV_RE = re.compile(r"\(([A-Za-z]{2,6})\)")


def _remove_parenthetical_abbrev_dupes(
    candidate: dict[str, Any], result: PostProcessResult
) -> None:
    """Remove short abbreviation terms that are just the parenthetical code from a longer term.

    E.g. if terms include "Serum alanine aminotransferase level (ALT): 7 iu/L" and "ALT",
    the standalone "ALT" is redundant and should be removed.
    """
    for sent in candidate.get("sentences", []):
        terms = sent.get("terms", [])
        if len(terms) <= 1:
            continue

        abbrevs_in_long_terms: set[str] = set()
        for term in terms:
            text = term.get("text", "")
            if len(text) > 10:
                for m in _PAREN_ABBREV_RE.finditer(text):
                    abbrevs_in_long_terms.add(m.group(1).upper())

        if not abbrevs_in_long_terms:
            continue

        kept: list[dict[str, Any]] = []
        removed = 0
        for term in terms:
            text = term.get("text", "").strip()
            if text.upper() in abbrevs_in_long_terms and len(text) <= 10:
                removed += 1
                continue
            kept.append(term)

        if removed:
            sent["terms"] = kept
            result.terms_removed += removed
            result.actions.append(RuleAction(
                rule_id="abbrev_in_parens",
                action="remove_term",
                detail=f"Removed {removed} parenthetical abbreviation dupes from sentence {sent.get('sentence_id')}",
            ))


def _dedup_terms(candidate: dict[str, Any], result: PostProcessResult) -> None:
    for sent in candidate.get("sentences", []):
        terms = sent.get("terms", [])
        if len(terms) <= 1:
            continue
        seen: set[str] = set()
        deduped: list[dict[str, Any]] = []
        removed = 0
        for term in terms:
            cid = term.get("coding", {}).get("snomed_concept_id")
            text_key = term.get("text", "").lower()
            key = f"{cid}:{text_key}" if cid else f"none:{text_key}"
            if key in seen:
                removed += 1
                continue
            seen.add(key)
            deduped.append(term)
        if removed:
            sent["terms"] = deduped
            result.terms_removed += removed
            result.actions.append(RuleAction(
                rule_id="dedup",
                action="dedup",
                detail=f"Removed {removed} duplicate terms from sentence {sent.get('sentence_id')}",
            ))
