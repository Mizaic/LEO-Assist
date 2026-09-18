"""Build a Situation headline from present coded facts.

Atlas trace:
  DO: DO-FE774247
  DI: DI-ED65569C
"""

from __future__ import annotations

import re
from typing import Any

from libs.sbar.clinic_reason_fit import reason_names_a_finding, term_fits_clinic

_PMB_PHRASES = (
    "postmenopausal bleeding",
    "post-menopausal bleeding",
    "post menopausal bleeding",
    "postmenopausal vaginal bleeding",
    "post-menopausal vaginal bleeding",
    "post menopausal vaginal bleeding",
)

_ABSENT = frozenset({"absent", "negated", "refuted"})
_FORM_CHROME = frozenset({"form_schema_checkbox"})
_WEAK = (
    "postmenopausal state",
    "post menopausal for",
    "body mass",
    "blood pressure",
    "heart rate",
    "pulse regular",
    "ex-smoker",
    "smoker",
    "alcohol intake",
    "alcohol units",
    "body weight",
    "body height",
    "bmi",
)

_NO_PREFIX = re.compile(r"^(?:no|not|denies)\s+", re.I)
_MIN_ABSENT_PHRASE = 8
_LEAD_HINTS = (
    "nipple",
    "lump",
    "hypertrophy",
    "discharge",
    "bleeding",
)
_SITE_SKIP = frozenset(
    {
        "breast",
        "vagina",
        "vaginal",
        "cervix",
        "cervical",
        "ovarian",
        "uterine",
        "endometrial",
        "gynaecology",
        "gynecology",
        "referral",
        "reason",
        "documented",
        "pathway",
        "clinic",
    }
)


def headline_from_coded_facts(
    entities: list[dict[str, Any]] | None,
    clinic_type: str | None = None,
    priority_concept_ids: set[int] | set[str] | None = None,
) -> str | None:
    """Name undenied form ticks first. Never name absent PMB."""
    ticks, suspected, findings = _split_headline_facts(
        entities, clinic_type, priority_concept_ids
    )
    if ticks:
        parts = [row[1] for row in ticks[:3]]
    else:
        parts = [row[1] for row in suspected[:1]] + [row[1] for row in findings[:1]]
    if not parts:
        return None
    return ". ".join(parts) + "."


def absent_finding_terms(entities: list[dict[str, Any]] | None) -> list[str]:
    """Terms coded absent, so Situation must not name them as the trigger."""
    out: list[str] = []
    for entity in entities or []:
        if str(entity.get("assertion") or "").strip().lower() not in _ABSENT:
            continue
        term = _short_term(entity)
        if term and term not in out:
            out.append(term)
    return out[:8]


def drop_invented_pmb(
    markdown: str,
    present_terms: list[str] | None = None,
    structured_headline: str | None = None,
) -> str:
    """Remove a PMB trigger the letter and codes do not support."""
    text = (markdown or "").strip()
    if not text or _pmb_is_present(present_terms):
        return markdown
    if not any(phrase in text.lower() for phrase in _PMB_PHRASES):
        return markdown
    kept = [
        part.strip()
        for part in re.split(r"(?<=[.!?])\s+", text)
        if part.strip() and not any(phrase in part.lower() for phrase in _PMB_PHRASES)
    ]
    if kept:
        return " ".join(kept)
    return (structured_headline or "").strip() or markdown


def drop_invented_absent_findings(
    markdown: str,
    absent_terms: list[str] | None = None,
    present_terms: list[str] | None = None,
    structured_headline: str | None = None,
) -> str:
    """Remove a trigger the codes already marked absent."""
    text = (markdown or "").strip()
    forbidden = _positive_absent_phrases(absent_terms, present_terms)
    if not text or not forbidden:
        return markdown
    if not any(phrase in text.lower() for phrase in forbidden):
        return markdown
    kept = [
        part.strip()
        for part in re.split(r"(?<=[.!?])\s+", text)
        if part.strip() and not any(phrase in part.lower() for phrase in forbidden)
    ]
    if kept:
        return " ".join(kept)
    return (structured_headline or "").strip() or markdown


def drop_copied_empty_reason(
    markdown: str,
    structured_headline: str | None = None,
) -> str:
    """Replace placeholder 'no presenting symptom' copy with the coded headline."""
    text = (markdown or "").strip()
    headline = (structured_headline or "").strip()
    if not text or not headline:
        return markdown
    if reason_names_a_finding(text):
        return markdown
    return headline


def prefer_coded_headline(
    markdown: str,
    structured_headline: str | None = None,
) -> str:
    """Name the coded finding when the LLM only wrote a generic clinic line."""
    text = (markdown or "").strip()
    headline = (structured_headline or "").strip()
    if not text or not headline:
        return markdown
    anchors = _headline_anchors(headline)
    if not anchors:
        return markdown
    low = text.lower()
    if any(anchor in low for anchor in anchors):
        return markdown
    body = text.rstrip(".")
    return f"{body}. Headline trigger: {headline}"


def sanitize_situation_markdown(
    markdown: str,
    *,
    present_terms: list[str] | None = None,
    absent_terms: list[str] | None = None,
    structured_headline: str | None = None,
) -> str:
    """Apply Situation safety filters in a fixed order."""
    md = drop_invented_pmb(markdown, present_terms, structured_headline)
    md = drop_invented_absent_findings(
        md, absent_terms, present_terms, structured_headline
    )
    md = drop_copied_empty_reason(md, structured_headline)
    return prefer_coded_headline(md, structured_headline)


def _headline_anchors(headline: str) -> list[str]:
    words = re.findall(r"[a-z]{4,}", headline.lower())
    return [word for word in words if word not in _SITE_SKIP]


def _positive_absent_phrases(
    absent_terms: list[str] | None,
    present_terms: list[str] | None,
) -> list[str]:
    present_low = " ".join(present_terms or []).lower()
    out: list[str] = []
    for term in absent_terms or []:
        phrase = _positive_finding_phrase(term)
        if len(phrase) < _MIN_ABSENT_PHRASE or phrase in present_low:
            continue
        if phrase not in out:
            out.append(phrase)
    return out


def _positive_finding_phrase(term: str) -> str:
    low = str(term or "").strip().lower()
    if " (" in low:
        low = low.split(" (", 1)[0].strip()
    return _NO_PREFIX.sub("", low).strip()


def _pmb_is_present(present_terms: list[str] | None) -> bool:
    for term in present_terms or []:
        low = term.lower()
        if any(phrase in low for phrase in _PMB_PHRASES):
            return True
    return False


def present_finding_terms(entities: list[dict[str, Any]] | None) -> list[str]:
    """Present coded terms that may lead Situation."""
    denied = absent_finding_terms(entities)
    out: list[str] = []
    for entity in entities or []:
        if str(entity.get("assertion") or "").strip().lower() in _ABSENT:
            continue
        term = _short_term(entity)
        if not term or _is_weak(term) or term in out:
            continue
        if _is_form_chrome(entity) and _tick_denied(term, denied):
            continue
        out.append(term)
    return out[:8]


def _split_headline_facts(
    entities: list[dict[str, Any]] | None,
    clinic_type: str | None,
    priority_concept_ids: set[int] | set[str] | None = None,
) -> tuple[
    list[tuple[tuple[int, int, int], str]],
    list[tuple[tuple[int, int, int], str]],
    list[tuple[tuple[int, int, int], str]],
]:
    clinic = str(clinic_type or "")
    denied = absent_finding_terms(entities)
    ticks: list[tuple[tuple[int, int, int], str]] = []
    suspected: list[tuple[tuple[int, int, int], str]] = []
    findings: list[tuple[tuple[int, int, int], str]] = []
    for entity in entities or []:
        if str(entity.get("assertion") or "").strip().lower() in _ABSENT:
            continue
        term = _short_term(entity)
        if not term or _is_weak(term):
            continue
        rank = _lead_rank(term, entity, clinic)
        if _is_form_chrome(entity):
            if not _tick_denied(term, denied):
                ticks.append((rank, term))
            continue
        if _is_suspected(term, entity):
            if clinic and not term_fits_clinic(term, clinic):
                continue
            suspected.append((rank, term))
        elif _is_finding(term, entity):
            findings.append((rank, term))
    ticks.sort()
    suspected, findings = _prefer_form_priority(
        suspected, findings, entities, priority_concept_ids
    )
    return ticks, suspected, findings


def _prefer_form_priority(
    suspected: list[tuple[tuple[int, int, int], str]],
    findings: list[tuple[tuple[int, int, int], str]],
    entities: list[dict[str, Any]] | None,
    priority_concept_ids: set[int] | set[str] | None,
) -> tuple[
    list[tuple[tuple[int, int, int], str]],
    list[tuple[tuple[int, int, int], str]],
]:
    """When FormSchema names trigger codes, those findings own the headline."""
    priority = {str(cid) for cid in (priority_concept_ids or set()) if str(cid)}
    if not priority:
        suspected.sort()
        findings.sort()
        return suspected, findings
    terms = {
        _short_term(entity)
        for entity in entities or []
        if _concept_id(entity) in priority
    }
    terms.discard("")
    if not terms:
        suspected.sort()
        findings.sort()
        return suspected, findings
    preferred = [row for row in findings if row[1] in terms]
    if preferred:
        preferred.sort()
        return [], preferred
    suspected.sort()
    findings.sort()
    return suspected, findings


def _concept_id(entity: dict[str, Any]) -> str:
    return str(entity.get("concept_id") or "").strip()


def _content_words(term: str) -> set[str]:
    words = set(re.findall(r"[a-z]{4,}", str(term or "").lower()))
    return {word for word in words if word not in _SITE_SKIP}


def _tick_denied(term: str, denied_terms: list[str]) -> bool:
    tick_words = _content_words(term)
    if not tick_words:
        return False
    return any(tick_words & _content_words(item) for item in denied_terms)


def _is_form_chrome(entity: dict[str, Any]) -> bool:
    return str(entity.get("__source") or "") in _FORM_CHROME


def _short_term(entity: dict[str, Any]) -> str:
    raw = str(entity.get("term") or entity.get("text") or "").strip()
    if " (" in raw:
        raw = raw.split(" (", 1)[0].strip()
    return raw


def _is_weak(term: str) -> bool:
    low = term.lower()
    return any(token in low for token in _WEAK)


def _is_suspected(term: str, _entity: dict[str, Any]) -> bool:
    low = term.lower()
    if "no known" in low:
        return False
    return "suspected" in low


def _is_finding(term: str, entity: dict[str, Any]) -> bool:
    label = _entity_label(term, entity)
    if label in {"finding", "disorder"}:
        return True
    return "discharge" in term.lower()


def _entity_label(term: str, entity: dict[str, Any]) -> str:
    label = str(entity.get("label") or "").lower()
    if label:
        return label
    if " (" in term and term.endswith(")"):
        return term.rsplit(" (", 1)[-1].rstrip(")").lower()
    return ""


def _lead_rank(term: str, entity: dict[str, Any], clinic: str) -> tuple[int, int, int]:
    blob = " ".join(
        part
        for part in (term, str(entity.get("text") or ""), str(entity.get("term") or ""))
        if part
    )
    low = blob.lower()
    match = 0 if term_fits_clinic(blob, clinic) else 1
    lead = 0 if any(hint in low for hint in _LEAD_HINTS) else 1
    return (match, lead, _kind_rank(entity))


def _kind_rank(entity: dict[str, Any]) -> int:
    label = _entity_label(_short_term(entity), entity)
    if label == "disorder":
        return 0
    if label == "finding":
        return 1
    return 2
