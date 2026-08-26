"""Heuristic de-identification and normalisation for form templates.

Produces a normalised template string from raw letter text and a saved
FormSchema. Patient-specific values are replaced with placeholder tokens.
Structural skeleton (section headings, checkbox rows, labels) is preserved.

Atlas trace: DI-5C9CA57B
"""

from __future__ import annotations

import re
from typing import Any

# -- Replacement token constants --
_T_NHS = "{{NHS_NUMBER}}"
_T_DOB = "{{DOB}}"
_T_NAME = "{{NAME}}"
_T_TEXT = "{{CLINICAL_TEXT}}"
_T_RESULT = "{{RESULT}}"
_T_ADDR = "{{ADDRESS}}"

# -- Patterns --
_NHS_RE = re.compile(r"\b\d{3}\s?\d{3}\s?\d{4}\b")
_DOB_RE = re.compile(
    r"\b\d{1,2}\s+(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|"
    r"Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|"
    r"Nov(?:ember)?|Dec(?:ember)?)\s+\d{4}\b",
    re.I,
)
_DOB_NUMERIC = re.compile(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b")
_NAME_LABELS = re.compile(
    r"(?i)^(surname|forename|first\s+name|last\s+name|patient\s+name|"
    r"referring\s+gp|gp\s+name|clinician|consultant)\s*[:\-]\s*(.+)$"
)
_ADDR_LABELS = re.compile(
    r"(?i)^(address|postcode|town|city)\s*[:\-]\s*(.+)$"
)
_TABLE_RESULT = re.compile(r"\|\s*([\d\.,]+(?:\s*[a-z/]+)?)\s*\|", re.I)

_SECTION_RE = re.compile(r"(?i)section\s+[a-z]\b")


def generate_normalised_template(
    text: str,
    sections: list[dict[str, Any]],
) -> str:
    """Return a de-identified form template string.

    Args:
        text: Raw letter / form text.
        sections: FormSchema sections (as dicts with at least
            ``section_type`` and ``start_pattern`` keys).

    Returns:
        A string with patient values replaced by placeholder tokens.
    """
    free_text_patterns = _free_text_start_patterns(sections)
    lines = text.splitlines()
    output = _process_lines(lines, free_text_patterns)
    return "\n".join(output)


def _free_text_start_patterns(
    sections: list[dict[str, Any]],
) -> list[re.Pattern[str]]:
    patterns: list[re.Pattern[str]] = []
    for s in sections:
        if s.get("section_type") != "free_text":
            continue
        raw = s.get("start_pattern") or ""
        if raw:
            try:
                patterns.append(re.compile(raw))
            except re.error:
                pass
    return patterns


def _process_lines(
    lines: list[str],
    free_text_patterns: list[re.Pattern[str]],
) -> list[str]:
    output: list[str] = []
    in_free_text = False

    for line in lines:
        if _is_section_boundary(line, free_text_patterns):
            in_free_text = _is_free_text_header(line, free_text_patterns)
            output.append(line)
            continue

        if in_free_text:
            cleaned = _replace_demographics(line)
            if cleaned.strip():
                output.append(_T_TEXT)
            else:
                output.append(line)
            continue

        output.append(_redact_line(line))

    return output


def _is_section_boundary(
    line: str, free_text_patterns: list[re.Pattern[str]]
) -> bool:
    if _SECTION_RE.search(line):
        return True
    for pat in free_text_patterns:
        if pat.search(line):
            return True
    return False


def _is_free_text_header(
    line: str, free_text_patterns: list[re.Pattern[str]]
) -> bool:
    for pat in free_text_patterns:
        if pat.search(line):
            return True
    return False


def _redact_line(line: str) -> str:
    """Replace known patient-specific values in a single non-free-text line."""
    line = _NHS_RE.sub(_T_NHS, line)
    line = _DOB_RE.sub(_T_DOB, line)
    line = _DOB_NUMERIC.sub(_T_DOB, line)
    line = _TABLE_RESULT.sub(f"| {_T_RESULT} |", line)

    name_match = _NAME_LABELS.match(line.strip())
    if name_match:
        label = name_match.group(1)
        return f"{label}: {_T_NAME}"

    addr_match = _ADDR_LABELS.match(line.strip())
    if addr_match:
        label = addr_match.group(1)
        return f"{label}: {_T_ADDR}"

    return line


def _replace_demographics(line: str) -> str:
    """Lightweight redaction for free-text body lines."""
    line = _NHS_RE.sub(_T_NHS, line)
    line = _DOB_RE.sub(_T_DOB, line)
    return line
