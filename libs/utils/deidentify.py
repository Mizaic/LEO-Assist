"""Shared regex-based de-identification for GP encounter text.

Strips the PII patterns most commonly found in SystmOne / EMIS exports before
encounter text is sent to external LLMs or stored in training artefacts.

Patterns covered:
    - SURNAME, Forename (SystmOne Role)  →  [PERSON]
    - SURNAME, Forename (Title)          →  [PERSON]
    - Dr/Mr/Mrs/Ms/Miss/Prof Surname     →  [PERSON]
    - ALL-CAPS SURNAME, Forename         →  [PERSON]  (handles O'NEILL, hyphenated)
    - Local organisations (deployment-specific list)  →  [ORGANISATION]
    - NHS numbers (10-digit)             →  [NHS_NUMBER]
    - UK postcodes                       →  [POSTCODE]
    - UK phone numbers                   →  [PHONE]
    - Email addresses                    →  [EMAIL]
    - UK street addresses                →  [ADDRESS]
    - Dates (DD/MM/YYYY, DD.MM.YYYY, YYYY-MM-DD)  →  [DATE]

Intentionally NOT stripped (preserves clinical utility):
    - Coded terms (XaBC1, SNOMED codes)
    - Medication names and doses
    - Clinical values and units
    - Times (HH:MM — not PII in themselves)

NOTE — first names in free-text narrative (e.g. "discussed with Christopher")
are not catchable by regex alone.  Run a spaCy PERSON NER pass over the text
before calling deidentify_text() if that coverage is required.
"""

from __future__ import annotations

import os
import re

# ---------------------------------------------------------------------------
# Deployment-specific local organisations
# ---------------------------------------------------------------------------
# These names identify the source practice / trust and must be scrubbed from
# training exports.
#
# GAP-014: configurable at runtime via the DEIDENTIFY_LOCAL_ORGS env var.
# Set it to a pipe-separated list:
#   DEIDENTIFY_LOCAL_ORGS="Royal Free Hospital|Moorfields Eye|UCL"
# Falls back to the built-in list below when the env var is absent.
_BUILTIN_ORGS: tuple[str, ...] = (
    "Loughborough Urgent Treatment Centre",
    "Woodbrook Medical Centre",
    "LLR Charnwood DN",
    "LLR Charnwood",
    "LLR SPA",
    "Ward 28, LGH",
    "LGH",
)


def _load_local_orgs() -> tuple[str, ...]:
    raw = os.environ.get("DEIDENTIFY_LOCAL_ORGS", "").strip()
    if raw:
        orgs = tuple(o.strip() for o in raw.split("|") if o.strip())
        if orgs:
            return orgs
    return _BUILTIN_ORGS


_LOCAL_ORGS: tuple[str, ...] = _load_local_orgs()


def _build_org_re(orgs: tuple[str, ...]) -> re.Pattern[str]:
    if not orgs:
        return re.compile(r"(?!)")  # never-matching pattern
    # Longest match first so "LLR Charnwood DN" beats "LLR Charnwood"
    parts = sorted((re.escape(o) for o in orgs), key=len, reverse=True)
    return re.compile(r"(?:" + "|".join(parts) + r")", re.IGNORECASE)


LOCAL_ORG_RE = _build_org_re(_LOCAL_ORGS)

# ---------------------------------------------------------------------------
# Compiled patterns
# ---------------------------------------------------------------------------

# SURNAME, Forename (SystmOne access/role description ending in "Role")
# e.g. BEGUM, Senuara (Medical Secretary Access Role)
#      O'NEILL, Anna-Louise (Admin/Clinical Support Access Role)
#      DAVIES, Caron (Clerical Access Role)
NAME_ROLE_RE = re.compile(
    r"\b[A-Z][A-Z'\-]{2,},\s*[A-Z][a-zA-Z'\-]+(?:\s+[A-Z][a-zA-Z'\-]+)?\s*\([^)]+\bRole\)"
)

# SURNAME, Forename (Title) — e.g. BORSADA, Stanley (Dr), PALMER, Betty (Mrs)
NAME_STYLE_RE = re.compile(
    r"\b[A-Z][A-Z\-']+,\s*[A-Z][a-zA-Z\-']+\s*\((?:Mr|Mrs|Ms|Miss|Dr|Prof)\)"
)

# Title Surname — e.g. Dr Smith, Mrs Jones
HONORIFIC_NAME_RE = re.compile(r"\b(?:Mr|Mrs|Ms|Miss|Dr|Prof)\s+[A-Z][a-zA-Z\-']+\b")

# ALL-CAPS surname followed by comma and first name — catches:
#   HEUNIS, JAN          (all-caps firstname)
#   ATKIN, Sharon        (TitleCase firstname, no standard title suffix)
#   MACLEOD-BROWN, Alice (hyphenated surname)
#   O'NEILL, Siobhan     (apostrophe surname — [A-Z'][A-Z'\\-]{2,} covers this)
# Requires 3+ chars (including apostrophe/hyphen) in surname to reduce false positives.
CAPS_NAME_RE = re.compile(r"\b[A-Z][A-Z'\-]{2,},\s+[A-Z][a-zA-Z]{2,}\b")

# Stray CAPS token (2–5 chars) left immediately before [PERSON] — arises when a
# multi-word CAPS name (e.g. "KOK LEE, Ming") was only partially matched and the
# leading element was not consumed.
STRAY_CAPS_PREFIX_RE = re.compile(r"\b[A-Z]{2,5}\s+(?=\[PERSON\])")

# NHS number: 10 digits optionally split by spaces or hyphens
NHS_RE = re.compile(r"\b\d{3}[\s\-]?\d{3}[\s\-]?\d{4}\b")

# Named healthcare facility — e.g. "City Hospital", "Royal Infirmary",
# "Queen's Medical Centre", "Leicester General Hospital".
#
# Matches: 1-4 title-case name words (including connectors like "of/the")
#          followed by a facility-type keyword.
# Replaces the name prefix with [LOCATION] and keeps the facility-type word
# so clinical context is preserved.
#   "City Hospital"         →  "[LOCATION] Hospital"
#   "Royal Infirmary"       →  "[LOCATION] Infirmary"
#   "Queen's Medical Centre" → "[LOCATION] Medical Centre"
#   "Leicester Royal"       →  NOT matched (no facility-type suffix)
#
# Does NOT fire on bare "hospital" / "clinic" alone (no preceding proper name).
FACILITY_NAME_RE = re.compile(
    r"\b"
    # One or more title-case name tokens each followed by a space.
    # Covers: "City ", "Royal ", "St Mary's ", "Leicester General ", "Queen's "
    r"(?:[A-Z][a-zA-Z'\-]+\s+)+"
    # Facility-type keyword (named group so replacement can preserve it).
    r"(?P<ftype>Hospital|Infirmary|Hospice|Clinic|Sanatorium"
    r"|Medical\s+Centre|Health\s+Centre|Healthcare\s+Centre"
    r"|NHS\s+(?:Foundation\s+)?Trust)"
    r"\b",
)

# UK street address — e.g. "44 Carnation Road, Loughborough"
# Matches house-number + at least one street-name word + road type.
ADDRESS_RE = re.compile(
    r"\b\d+\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\s+"
    r"(?:Road|Street|Avenue|Lane|Drive|Close|Way|Place|Gardens?|Crescent|"
    r"Terrace|Grove|Court|Walk|Rise|Hill|Park|View|Mews|Square|Row|Boulevard)\b",
    re.IGNORECASE,
)

# UK postcode
POSTCODE_RE = re.compile(
    r"\b(?:GIR\s?0AA|[A-Z]{1,2}\d[A-Z\d]?\s?\d[A-Z]{2})\b", re.IGNORECASE
)

# CTV3 / Read v2 clinical code shape: exactly 5 alphanumeric characters
# (e.g. "Ya03d", "B00zz", "X78HC", "8BAD0") with optional trailing dot padding
# for Read v2 ("B0...", "B00..", "B000."). These collide with the compact-form
# UK postcode regex (e.g. "B00zz" parses as letter-digit-digit-letter-letter).
# Canonical UK postcodes in clinical text are written with a space between
# outward and inward parts ("SW1A 1AA"), so any 5-char no-space match is far
# more likely to be a clinical code than a postcode.
READ_CODE_SHAPE_RE = re.compile(r"^[A-Za-z0-9]{1,5}\.{0,4}$")


def _looks_like_read_code(token: str) -> bool:
    """True if token looks like a CTV3 / Read v2 clinical code, not a postcode."""
    s = token.strip()
    if not s or " " in s or "\t" in s:
        return False
    if len(s) != 5:
        return False
    return bool(READ_CODE_SHAPE_RE.match(s))


def _replace_postcode(match: re.Match[str]) -> str:
    """Substitute [POSTCODE] but preserve clinical Read codes."""
    matched = match.group(0)
    if _looks_like_read_code(matched):
        return matched
    return "[POSTCODE]"

# UK phone number (handles optional space/hyphen after +44)
PHONE_RE = re.compile(r"(?:\+44[\s\-]?\d|\b0\d)[\d\s\-]{8,}\d\b")

# Email
EMAIL_RE = re.compile(r"\b[\w.\-+]+@[\w.\-]+\.\w+\b", re.IGNORECASE)

# Dates
DATE_SLASH_RE = re.compile(r"\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b")
DATE_DOT_RE = re.compile(r"\b\d{1,2}\.\d{1,2}\.\d{2,4}\b")
DATE_ISO_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
DATE_NATURAL_RE = re.compile(
    r"\b\d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{2,4}\b",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Optional spaCy NER second pass (GAP-008)
# ---------------------------------------------------------------------------
# Regex alone cannot catch first names in free-running clinical narrative
# (e.g. "spoke to Christopher about his meds").  A spaCy PERSON-NER pass
# over the text catches these residual mentions.
#
# The NER pass is opt-in:
#  - Set env var DEIDENTIFY_NER_MODEL to a spaCy model name (e.g. en_core_web_lg)
#    to enable it.  The model is loaded once and cached in _NER_NLP.
#  - The env var is read lazily on first call to deidentify_text(ner=True) so
#    that importing this module (e.g. in tests) does not trigger a model load.

_NER_NLP = None  # lazy-loaded spaCy pipeline
_NER_MODEL: str | None = None  # model name used to populate _NER_NLP


def _get_ner_nlp():
    """Return a cached spaCy nlp pipeline for NER, or None if not configured."""
    global _NER_NLP, _NER_MODEL
    model = os.environ.get("DEIDENTIFY_NER_MODEL", "").strip()
    if not model:
        return None
    if _NER_NLP is not None and _NER_MODEL == model:
        return _NER_NLP
    try:
        import spacy

        _NER_NLP = spacy.load(model, disable=["tagger", "parser", "lemmatizer"])
        _NER_MODEL = model
    except Exception as exc:
        import logging as _logging

        _logging.getLogger(__name__).warning(
            "DEIDENTIFY_NER_MODEL=%r could not be loaded — NER pass disabled: %s",
            model,
            exc,
        )
        return None
    return _NER_NLP


def _ner_redact(text: str, nlp) -> str:
    """Replace PERSON entities found by spaCy with [PERSON]."""
    doc = nlp(text)
    if not doc.ents:
        return text
    # Build replacement from right-to-left to preserve character offsets
    chars = list(text)
    for ent in reversed(doc.ents):
        if ent.label_ == "PERSON":
            chars[ent.start_char : ent.end_char] = list("[PERSON]")
    return "".join(chars)


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------


def deidentify_text(text: str, *, ner: bool | None = None) -> str:
    """Return ``text`` with PII patterns replaced by safe placeholder tokens.

    Safe to call multiple times (idempotent — placeholders don't match the
    patterns again).

    Args:
        text: Raw clinical text to de-identify.
        ner:  If True, run a spaCy PERSON-NER second pass after the regex
              pass to catch first names in free narrative.  Defaults to True
              when DEIDENTIFY_NER_MODEL env var is set, False otherwise.
    """
    out = text
    # Order matters: most-specific patterns first
    out = LOCAL_ORG_RE.sub("[ORGANISATION]", out)  # deployment-specific orgs first
    out = FACILITY_NAME_RE.sub(
        r"[LOCATION] \g<ftype>", out
    )  # City Hospital → [LOCATION] Hospital
    out = NAME_ROLE_RE.sub("[PERSON]", out)  # SURNAME, Firstname (SystmOne Role)
    out = NAME_STYLE_RE.sub("[PERSON]", out)  # SURNAME, Firstname (Mr/Mrs/Dr)
    out = HONORIFIC_NAME_RE.sub("[PERSON]", out)  # Dr/Mr Surname
    out = CAPS_NAME_RE.sub("[PERSON]", out)  # SURNAME, Firstname (bare)
    out = STRAY_CAPS_PREFIX_RE.sub("", out)  # KOK [PERSON] → [PERSON]
    out = ADDRESS_RE.sub("[ADDRESS]", out)
    out = EMAIL_RE.sub("[EMAIL]", out)
    out = PHONE_RE.sub("[PHONE]", out)
    out = NHS_RE.sub("[NHS_NUMBER]", out)
    out = POSTCODE_RE.sub(_replace_postcode, out)
    out = DATE_SLASH_RE.sub("[DATE]", out)
    out = DATE_DOT_RE.sub("[DATE]", out)
    out = DATE_ISO_RE.sub("[DATE]", out)
    out = DATE_NATURAL_RE.sub("[DATE]", out)

    # Optional NER second pass — catches residual first names in free narrative
    run_ner = (
        ner
        if ner is not None
        else bool(os.environ.get("DEIDENTIFY_NER_MODEL", "").strip())
    )
    if run_ner:
        nlp = _get_ner_nlp()
        if nlp is not None:
            out = _ner_redact(out, nlp)

    return out


def deidentify_with_span(
    sentence: str,
    span_text: str,
) -> tuple[str, int, int]:
    """Return (de-identified sentence, span start, span end).

    De-identifies the sentence first, then re-finds the span by
    case-insensitive string search. Safe because entity text (clinical
    terms) is never PII.

    When the span cannot be found after de-identification (e.g. the span
    text overlapped with a PII token), returns (-1, -1) as sentinel
    values. Callers MUST skip records with start == -1 to avoid
    corrupting training data.
    """
    deident = deidentify_text(sentence, ner=True)
    idx = deident.lower().find(span_text.lower())
    if idx == -1:
        return deident, -1, -1
    return deident, idx, idx + len(span_text)


def detect_phi(text: str) -> list[str]:
    """Return a list of PII type tags found in ``text`` (for audit / logging).

    Returns an empty list if no PII is detected.
    """
    found: list[str] = []
    if LOCAL_ORG_RE.search(text):
        found.append("organisation")
    if FACILITY_NAME_RE.search(text):
        found.append("facility_name")
    if (
        NAME_ROLE_RE.search(text)
        or NAME_STYLE_RE.search(text)
        or HONORIFIC_NAME_RE.search(text)
        or CAPS_NAME_RE.search(text)
    ):
        found.append("name")
    if ADDRESS_RE.search(text):
        found.append("address")
    if EMAIL_RE.search(text):
        found.append("email")
    if PHONE_RE.search(text):
        found.append("phone")
    if NHS_RE.search(text):
        found.append("nhs_number")
    if any(
        not _looks_like_read_code(m.group(0)) for m in POSTCODE_RE.finditer(text)
    ):
        found.append("postcode")
    if DATE_ISO_RE.search(text):
        found.append("iso_date")
    if DATE_NATURAL_RE.search(text):
        found.append("natural_date")
    return found
