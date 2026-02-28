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

import re

# ---------------------------------------------------------------------------
# Deployment-specific local organisations
# ---------------------------------------------------------------------------
# These names identify the source practice / trust and must be scrubbed from
# training exports.  Update this tuple for each deployment site.
_LOCAL_ORGS: tuple[str, ...] = (
    "Loughborough Urgent Treatment Centre",
    "Woodbrook Medical Centre",
    "LLR Charnwood DN",
    "LLR Charnwood",
    "LLR SPA",
    "Ward 28, LGH",
    "LGH",
)


def _build_org_re(orgs: tuple[str, ...]) -> re.Pattern[str]:
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
HONORIFIC_NAME_RE = re.compile(
    r"\b(?:Mr|Mrs|Ms|Miss|Dr|Prof)\s+[A-Z][a-zA-Z\-']+\b"
)

# ALL-CAPS surname followed by comma and first name — catches:
#   HEUNIS, JAN          (all-caps firstname)
#   ATKIN, Sharon        (TitleCase firstname, no standard title suffix)
#   MACLEOD-BROWN, Alice (hyphenated surname)
#   O'NEILL, Siobhan     (apostrophe surname — [A-Z'][A-Z'\\-]{2,} covers this)
# Requires 3+ chars (including apostrophe/hyphen) in surname to reduce false positives.
CAPS_NAME_RE = re.compile(
    r"\b[A-Z][A-Z'\-]{2,},\s+[A-Z][a-zA-Z]{2,}\b"
)

# Stray CAPS token (2–5 chars) left immediately before [PERSON] — arises when a
# multi-word CAPS name (e.g. "KOK LEE, Ming") was only partially matched and the
# leading element was not consumed.
STRAY_CAPS_PREFIX_RE = re.compile(r"\b[A-Z]{2,5}\s+(?=\[PERSON\])")

# NHS number: 10 digits optionally split by spaces
NHS_RE = re.compile(r"\b\d{3}\s?\d{3}\s?\d{4}\b")

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

# UK phone number
PHONE_RE = re.compile(r"\b(?:\+44|0)\d[\d\s\-]{8,}\d\b")

# Email
EMAIL_RE = re.compile(r"\b[\w.\-+]+@[\w.\-]+\.\w+\b", re.IGNORECASE)

# Dates
DATE_SLASH_RE = re.compile(r"\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b")
DATE_DOT_RE = re.compile(r"\b\d{1,2}\.\d{1,2}\.\d{2,4}\b")
DATE_ISO_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")

# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------

def deidentify_text(text: str) -> str:
    """Return ``text`` with PII patterns replaced by safe placeholder tokens.

    Safe to call multiple times (idempotent — placeholders don't match the
    patterns again).
    """
    out = text
    # Order matters: most-specific patterns first
    out = LOCAL_ORG_RE.sub("[ORGANISATION]", out) # deployment-specific orgs first
    out = FACILITY_NAME_RE.sub(r"[LOCATION] \g<ftype>", out)  # City Hospital → [LOCATION] Hospital
    out = NAME_ROLE_RE.sub("[PERSON]", out)       # SURNAME, Firstname (SystmOne Role)
    out = NAME_STYLE_RE.sub("[PERSON]", out)      # SURNAME, Firstname (Mr/Mrs/Dr)
    out = HONORIFIC_NAME_RE.sub("[PERSON]", out)  # Dr/Mr Surname
    out = CAPS_NAME_RE.sub("[PERSON]", out)       # SURNAME, Firstname (bare)
    out = STRAY_CAPS_PREFIX_RE.sub("", out)       # KOK [PERSON] → [PERSON]
    out = ADDRESS_RE.sub("[ADDRESS]", out)
    out = EMAIL_RE.sub("[EMAIL]", out)
    out = PHONE_RE.sub("[PHONE]", out)
    out = NHS_RE.sub("[NHS_NUMBER]", out)
    out = POSTCODE_RE.sub("[POSTCODE]", out)
    out = DATE_SLASH_RE.sub("[DATE]", out)
    out = DATE_DOT_RE.sub("[DATE]", out)
    out = DATE_ISO_RE.sub("[DATE]", out)
    return out


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
    if POSTCODE_RE.search(text):
        found.append("postcode")
    if DATE_ISO_RE.search(text):
        found.append("iso_date")
    return found
