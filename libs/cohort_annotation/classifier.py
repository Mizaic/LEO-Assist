"""Deterministic encounter pre-classifier.

Classifies each encounter into one of five classes without an LLM call,
routing the majority of processing cost before any API call is made.

Classes:
    EMPTY      -- admin scaffolding; no clinical content; return empty output.
    STRUCTURED -- predominantly lab results / vitals templates; minimal prose.
    NARRATIVE  -- predominantly free-text clinical narrative.
    LETTER     -- secondary-care outpatient letter (contains RECORD_ARTIFACT).
    MIXED      -- meaningful labs/vitals AND narrative prose.
"""

from __future__ import annotations

import re

from libs.cohort_annotation.state import EncounterClass

# ---------------------------------------------------------------------------
# Admin-only patterns (PF1 in the annotation prompt)
# ---------------------------------------------------------------------------

_STAFF_ROLE_RE = re.compile(
    r"^\s*(?:\d{1,2}:\d{2}\s*-\s*)?(?:Surgery|Clinic|GP Surgery|Patient's Home)"
    r"\s*:\s*(?:\[(?:STAFF|PERSON)\]|\w[\w\s]*)\s*"
    r"\((?:Pharmacist|Receptionist(?:\s+Access\s+Role)?|Admin/Clinical\s+Support"
    r"(?:\s+Access\s+Role)?|Nurse\s+Access\s+Role|Medical\s+Secretary"
    r"(?:\s+Access\s+Role)?|Clinical\s+Practitioner\s+Access\s+Role)\)\s*$",
    re.IGNORECASE,
)

_PAS_UPDATE_RE = re.compile(
    r"Automatically\s+updated\s+from\s+PAS\s+interface",
    re.IGNORECASE,
)

_SCR_UPDATE_RE = re.compile(
    r"Summary\s+Care\s+Record\s+Update\s*[–-]",
    re.IGNORECASE,
)

_BOOKING_RE = re.compile(
    r"appointment\s+has\s+been\s+(?:booked|cancelled)\s+for\b",
    re.IGNORECASE,
)

_SEEN_IN_CLINIC_RE = re.compile(
    r"^Seen\s+in\s+clinic\s*\([A-Za-z0-9&:]+\)\s*$",
    re.IGNORECASE,
)

_SCR_SHARING_RE = re.compile(
    r"Outgoing\s+Record\s+Sharing\s+consent\s+change",
    re.IGNORECASE,
)

_ADMIN_PATTERNS: tuple[re.Pattern, ...] = (
    _PAS_UPDATE_RE,
    _SCR_UPDATE_RE,
    _BOOKING_RE,
    _SEEN_IN_CLINIC_RE,
    _SCR_SHARING_RE,
)

# ---------------------------------------------------------------------------
# Letter envelope patterns (R15 in the annotation prompt)
# ---------------------------------------------------------------------------

_LETTER_RE = re.compile(
    r"\b(?:outpatient\s+letter|clinic\s+letter|discharge\s+summary"
    r"|letter\s+to\s+(?:GP|Dr\b)|letter\s+from\s+\w"
    r"|(?:consultant|registrar)\s+letter)\b",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Structured content patterns
# ---------------------------------------------------------------------------

_STRUCTURED_RE = re.compile(
    r"""
    # Classic lab line with Read code and value
    [A-Za-z][A-Za-z0-9\s\-]+ \s* \([A-Za-z0-9.]{3,8}\) \s* [<>]?\d
    |
    # Vitals block: blood pressure reading, pulse rate, BMI, temperature, weight
    (?:blood\s+pressure|pulse\s+rate|heart\s+rate|body\s+mass\s+index
       |respiratory\s+rate|oxygen\s+saturation|temperature|weight|height)
       \s*[\(\d]
    |
    # GPPAQ or similar structured template lines
    GPPAQ\s+physical\s+activity
    |
    # Short BP reading: "142 / 88" at start of encounter
    ^\s*\d{2,3}\s*/\s*\d{2,3}\s*$
    """,
    re.IGNORECASE | re.VERBOSE | re.MULTILINE,
)

# Prose narrative signals: sentence-like structure
_NARRATIVE_RE = re.compile(
    r"""
    # Common clinical sentence starters
    \b(?:History|Examination|Assessment|Plan|Impression|Complaint|Presenting
        |Patient|He|She|They|Advised|Discussed|Review|Referred|Attended
        |F2F|Telephone|Video)\b
    .{20,}
    """,
    re.IGNORECASE | re.VERBOSE | re.DOTALL,
)


def _is_empty(text: str) -> bool:
    """Return True if the encounter is pure admin scaffolding (PF1)."""
    stripped = text.strip()
    if not stripped:
        return True
    if len(stripped) < 80 and _STAFF_ROLE_RE.match(stripped):
        return True
    for pat in _ADMIN_PATTERNS:
        if pat.search(stripped):
            if len(stripped) < 300:
                return True
    return False


def _has_letter_envelope(text: str) -> bool:
    return bool(_LETTER_RE.search(text[:500]))


def _structured_char_ratio(text: str) -> float:
    """Fraction of characters that fall inside structured-content matches."""
    if not text:
        return 0.0
    total = len(text)
    covered = sum(m.end() - m.start() for m in _STRUCTURED_RE.finditer(text))
    return min(1.0, covered / total)


def _narrative_char_ratio(text: str) -> float:
    if not text:
        return 0.0
    total = len(text)
    covered = sum(m.end() - m.start() for m in _NARRATIVE_RE.finditer(text))
    return min(1.0, covered / total)


def classify(text: str, flags: str = "") -> EncounterClass:
    """Return the EncounterClass for a single encounter.

    Decision is O(len(text)) and allocates no LLM budget.
    """
    if _is_empty(text):
        return EncounterClass.EMPTY

    if _has_letter_envelope(text):
        return EncounterClass.LETTER

    s_ratio = _structured_char_ratio(text)
    n_ratio = _narrative_char_ratio(text)

    if s_ratio >= 0.6 and n_ratio < 0.2:
        return EncounterClass.STRUCTURED
    if n_ratio >= 0.4 and s_ratio < 0.15:
        return EncounterClass.NARRATIVE
    return EncounterClass.MIXED
