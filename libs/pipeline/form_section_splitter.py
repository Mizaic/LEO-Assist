"""Deterministic section splitter for referral form teaching.

Finds Section A/B/C, SECTION 1/2/3 and named admin headers even when
they sit inside markdown tables or HTML cells. Used when the LLM returns
nothing useful.

Atlas trace: DI-5C9CA57B, DO-D0C19842, DI-C1744ED5, DO-1C8E7598
"""

from __future__ import annotations

import re
from typing import Any

_SECTION = re.compile(r"(?i)^section\s+([a-z]|\d{1,2})\b")
_NAMED = re.compile(
    r"(?i)^(patient details|practice details|minimum dataset|"
    r"for trust use|hospital number|hospital use only|pmb primary care|"
    r"patient awareness|bmi|blood results|medication|allergies|"
    r"clinical frailty|frailty scale)"
)
_ADMIN = re.compile(
    r"(?i)^(patient details|practice details|for trust use|hospital number|"
    r"hospital use only)"
)
# Numbered forms print the admin heading after the number, e.g.
# "SECTION 1 - PATIENT DEMOGRAPHIC DETAILS".
_ADMIN_NUMBERED = re.compile(r"(?i)^section\s+\d{1,2}\b.*\bdemographic")
# Lines that match _NAMED but contain a measurement or result value after the
# label -- treat them as data rows, not section headings.
_DATA_MEAS = re.compile(
    r":\s*\d[\d\.,]"  # colon then digit, e.g. "BMI: 20.2" or "Medication: 1."
)
# Numbered-scale item lines, e.g. "1. Very Fit [X]" or "1. Very Fit [ ]"
_SCALE_ITEM = re.compile(r"^\d+\.\s+\w[\w\s]{1,40}\[(?:X|x|\*|\s*)\]")
# ECOG inline ordinal row, e.g. "0 [ ] 1 [X] 2 [ ] 3 [ ]"
_ECOG_ROW = re.compile(r"(?:\d\s*\[(?:X|x|\*|\s*)\]\s*){2,}")
_SITE_ENTITY = {
    "cervix": "Cervical cancer suspected",
    "ovary": "Ovarian cancer suspected",
    "endometrium": "Endometrial cancer suspected",
    "vagina": "Vaginal cancer suspected",
    "vulva": "Vulval cancer suspected",
}
_TITLE = re.compile(
    r"(?i)urgent\s+suspected\s+cancer|gynaecolog(?:ical|y).{0,40}"
    r"(malignancy|2ww|referral)"
)
_CHECKED = re.compile(r"\[(?:X|x|\*)\]")
_UNCHECKED = re.compile(r"\[\s*\]")
_YES_NO = re.compile(r"Yes\s*\[(?:X|x)?\s*\]\s*No\s*\[(?:X|x)?\s*\]", re.I)
_SCALE = re.compile(r"\b1\.\s+\w[\w\s]+\[(?:X|\s*)\]")
_TESTS = re.compile(
    r"mandatory|fbc|lft|ues|urea|calcium|creatinine|blood\s+results?", re.I
)
_TAG = re.compile(r"<[^>]+>")
_BLOCK = re.compile(r"(?i)<br\s*/?>|</(?:p|div|tr|h[1-6]|li)>")
_TD = re.compile(r"(?i)</td>")
_LEAD_PIPE = re.compile(r"(?m)^\s*\|\s*")
_TAIL_PIPE = re.compile(r"(?m)\s*\|\s*$")
_SECTION_SPLIT = re.compile(r"(?i)(?<![A-Za-z])(section\s+(?:[a-z]|\d{1,2})\b)")


def normalize_form_text(text: str) -> str:
    """Turn HTML / table markup into line-oriented form text."""
    cleaned = (text or "").replace("\r\n", "\n")
    cleaned = _BLOCK.sub("\n", cleaned)
    cleaned = _TD.sub(" | ", cleaned)
    cleaned = _TAG.sub(" ", cleaned)
    cleaned = _LEAD_PIPE.sub("", cleaned)
    cleaned = _TAIL_PIPE.sub("", cleaned)
    cleaned = _SECTION_SPLIT.sub(r"\n\1", cleaned)
    return re.sub(r"[ \t]+", " ", cleaned)


def split_form_sections(text: str) -> list[dict[str, Any]]:
    """Propose FormSchema sections from raw or table-wrapped form text."""
    lines = normalize_form_text(text).split("\n")
    breaks = _breakpoints(lines)
    if not breaks:
        return []
    sections: list[dict[str, Any]] = []
    for i, (idx, label) in enumerate(breaks):
        next_idx = breaks[i + 1][0] if i + 1 < len(breaks) else len(lines)
        body = [ln.strip() for ln in lines[idx + 1 : next_idx] if ln.strip()]
        section_type = _section_type(label, body)
        letter = _SECTION.match(label)
        section_id = letter.group(1).upper() if letter else f"H{i}"
        sections.append(
            {
                "section_id": section_id,
                "label": label,
                "section_type": section_type,
                "start_pattern": _start_pattern(label),
                "items": _items(section_type, body),
            }
        )
        extra = _detect_scale_subsections(body)
        if extra:
            for sub_label, sub_body in extra:
                sub_type = _classify(sub_body) if sub_body else "scale"
                if sub_type == "free_text":
                    sub_type = "scale"
                sections.append(
                    {
                        "section_id": (
                            f"{section_id}_"
                            f"{re.sub(r'[^A-Za-z]', '', sub_label)[:6]}"
                        ),
                        "label": sub_label,
                        "section_type": sub_type,
                        "start_pattern": _start_pattern(sub_label),
                        "items": _items(sub_type, sub_body),
                    }
                )
    return _with_extras(text, sections, lines)


def is_incomplete_schema(sections: list[dict[str, Any]]) -> bool:
    """True when there are no usable clinical sections to teach.

    A schema is incomplete when either:
    - It is empty, or
    - Every section is an admin/noise skip type, or
    - Every clinical section has an empty label (LLM returned structure
      but omitted the content strings).
    """
    if not sections:
        return True
    skip = {"admin", "template_noise"}
    clinical = [s for s in sections if str(s.get("section_type") or "") not in skip]
    if not clinical:
        return True
    return all(not str(s.get("label") or "").strip() for s in clinical)


def _clean_label(raw: str) -> str:
    """Strip markdown table artifacts and normalise whitespace from a label."""
    label = raw.replace("#", " ").strip()
    # Remove trailing pipe-separated table fragments e.g. "Section E ... | | |"
    label = re.sub(r"\s*\|.*$", "", label).strip()
    return label


def _is_data_line(label: str) -> bool:
    """True when a line matching _NAMED looks like a data/measurement row."""
    return bool(_DATA_MEAS.search(label))


def _breakpoints(lines: list[str]) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    for idx, raw in enumerate(lines):
        label = _clean_label(raw)
        if not label:
            continue
        if _SECTION.match(label):
            found.append((idx, label))
        elif _NAMED.match(label) and not _is_data_line(label):
            found.append((idx, label))
        elif re.search(r"(?i)\bclinical frailty|frailty scale\b", label):
            found.append((idx, label))
        elif re.search(r"(?i)\becog\b", label) and not _SECTION.match(label):
            found.append((idx, label))
    return found


def _detect_scale_subsections(
    body: list[str],
) -> list[tuple[str, list[str]]] | None:
    """Detect CFS-style numbered scale blocks and ECOG ordinal rows in body.

    Returns a list of (header_label, body_lines) pairs for each sub-block
    found, or None if no sub-blocks are detected.
    """
    subsections: list[tuple[str, list[str]]] = []
    current_header: str | None = None
    current_body: list[str] = []

    for ln in body:
        if re.search(r"(?i)clinical frailty|frailty scale|cfs\b", ln):
            if current_header is not None:
                subsections.append((current_header, current_body))
            current_header = re.sub(r"\s*[:(].*", "", ln).strip() or ln.strip()
            current_body = []
        elif re.search(r"(?i)\becog\b|\bwho\s+ps\b|\bperformance status\b", ln):
            if _ECOG_ROW.search(ln) or re.search(r"\d\s*\[\s*\]", ln):
                if current_header is not None:
                    subsections.append((current_header, current_body))
                current_header = "ECOG / WHO Performance Status"
                current_body = [ln]
                subsections.append((current_header, current_body))
                current_header = None
                current_body = []
        elif current_header is not None:
            current_body.append(ln)

    if current_header is not None and current_body:
        subsections.append((current_header, current_body))

    return subsections if subsections else None


def detect_form_name(text: str) -> str:
    """Use the first clinical title line, not a generic form name."""
    for raw in (text or "").splitlines():
        line = raw.replace("#", " ").replace("|", " ").strip()
        if _TITLE.search(line):
            return re.sub(r"\s+", " ", line)[:120]
    return "Referral form"


def _section_type(label: str, body: list[str]) -> str:
    if re.search(r"(?i)minimum dataset", label):
        return "observable" if _observable_items(body) else "admin"
    if re.search(r"(?i)^bmi\b", label):
        return "observable"
    if re.search(r"(?i)ecog|who\s+ps|performance status", label):
        return "scale"
    if re.search(r"(?i)clinical frailty|frailty scale|cfs\b", label):
        return "scale"
    if _ADMIN.match(label) or _ADMIN_NUMBERED.match(label):
        return "admin"
    if re.search(r"(?i)medication|allergies", label):
        return "free_text"
    if re.search(r"(?i)pmb|awareness|holiday", label):
        return "checkbox_multi"
    return _classify(body)


def _classify(lines: list[str]) -> str:
    if any(_TESTS.search(ln) for ln in lines):
        return "ordered_tests"
    checked = sum(1 for ln in lines if _CHECKED.search(ln))
    unchecked = sum(1 for ln in lines if _UNCHECKED.search(ln))
    if checked + unchecked == 0:
        return "free_text"
    if any(_YES_NO.search(ln) for ln in lines):
        return "checkbox_yesno"
    if any(_SCALE.search(ln) for ln in lines):
        return "scale"
    if unchecked > 0 and checked <= 1:
        return "checkbox_single"
    if checked > 1:
        return "checkbox_multi"
    return "checkbox_single"


def _start_pattern(label: str) -> str:
    """Build a start pattern from a heading label.

    Label words are escaped. Headings such as "Blood Results (Last" carry
    brackets that would otherwise produce an uncompilable pattern.
    """
    letter = _SECTION.match(label)
    if letter and letter.group(1).isdigit():
        return rf"(?i)section\s+{letter.group(1)}\b"
    if letter:
        return rf"(?i)section\s+{letter.group(1).lower()}:"
    first = r"\s+".join(re.escape(word) for word in label.split()[:3])
    return rf"(?i){first}"


def _items(section_type: str, body: list[str]) -> list[dict[str, Any]]:
    if section_type == "observable":
        return _observable_items(body)
    if section_type == "checkbox_yesno":
        return _yes_no_items(body)
    if section_type not in {"checkbox_single", "checkbox_multi"}:
        return []
    item_re = re.compile(r"([A-Za-z][A-Za-z\s]{1,40}?)\s*\[(?:X|x|\*|\s*)\]")
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for ln in body:
        for match in item_re.finditer(ln):
            label = re.sub(r"^\d+[.)]\s*", "", match.group(1)).strip()
            if len(label) < 2 or label in seen:
                continue
            seen.add(label)
            items.append(
                {
                    "pattern": label,
                    "entity_text": _entity_text(label),
                    "semantic_tag": "finding",
                    "assertion": "present",
                }
            )
    return items


def _yes_no_items(body: list[str]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for ln in body:
        match = re.match(r"^(.+?)\s*[|]\s*Yes", ln, re.I) or re.match(
            r"^(B\d+\..+?)\s+Yes\s*\[", ln, re.I
        )
        if not match:
            continue
        label = re.sub(r"^\s*[A-Z]\d*[.:]?\s*", "", match.group(1)).strip()
        if len(label) < 3:
            continue
        items.append(
            {
                "pattern": match.group(1).strip(),
                "entity_text": label,
                "semantic_tag": "finding",
                "assertion": "present",
            }
        )
    return items


def _entity_text(label: str) -> str:
    key = re.sub(r"[^a-z]", "", label.lower())
    return _SITE_ENTITY.get(key, label.strip())


def _observable_items(body: list[str]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for ln in body:
        for name, entity, pattern in (
            ("BMI", "Body mass index", r"(?i)\bBMI\b"),
            ("BP", "Blood pressure", r"(?i)\bBP\b"),
            ("HR", "Heart rate", r"(?i)\b(?:HR|heart rate)\b"),
        ):
            if name in seen or not re.search(pattern, ln):
                continue
            seen.add(name)
            items.append(
                {
                    "pattern": name,
                    "entity_text": entity,
                    "semantic_tag": "observable_entity",
                    "assertion": "present",
                }
            )
    return items


def _with_extras(
    text: str, sections: list[dict[str, Any]], lines: list[str]
) -> list[dict[str, Any]]:
    if not any(
        i.get("pattern") == "BMI" for s in sections for i in s.get("items") or []
    ):
        bmi = _observable_items(lines)
        bmi = [item for item in bmi if item["pattern"] == "BMI"]
        if bmi:
            sections.append(
                {
                    "section_id": "BMI",
                    "label": "BMI",
                    "section_type": "observable",
                    "start_pattern": r"(?i)bmi",
                    "items": bmi,
                }
            )
    return sections
