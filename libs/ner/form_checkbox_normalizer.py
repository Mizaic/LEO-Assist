"""Deterministic referral form checkbox normalisation (extract-input boundary).

Atlas trace:
  DO: DO-7010394B
  DI: DI-5C9CA57B
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-7010394B")

Does not rewrite persisted Neo4j chunk text. Callers pass a copy used only for
LLM extraction input.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

NON_EXTRACTABLE_MARKER = "[NON_EXTRACTABLE]"

_UNCHECKED = re.compile(r"\[\s*\]|\(\s*\)|\[\-\]|\[\u2610\]")
_CHECKED = re.compile(r"\[(?:X|x|YES|yes|\*|\u2713|\u2714|\u2611)\]|\((?:X|x|\*)\)")
_UNCHECKED_ONLY = re.compile(r"^(?:\[\s*\]|\(\s*\)|\[\-\]|\[\u2610\])$")
_CHECKED_ONLY = re.compile(
    r"^(?:\[(?:X|x|YES|yes|\*|\u2713|\u2714|\u2611)\]|\((?:X|x|\*)\))$"
)
_UNCHECKED_PREFIX = re.compile(r"^(?:\[\s*\]|\(\s*\)|\[\-\]|\[\u2610\])\s+")
_CHECKED_PREFIX = re.compile(
    r"^(?:\[(?:X|x|YES|yes|\*|\u2713|\u2714|\u2611)\]|\((?:X|x|\*)\))\s+"
)

_APPENDIX_START = re.compile(
    r"(?i)^\s*(appendix\s+[a-z0-9]+|"
    r"referral criteria|"
    r"serious,\s*non-specific symptoms pathway|"
    r"symptoms pathway)"
)

_APPENDIX_END = re.compile(
    r"(?i)^\s*("
    r"the reason i am concerned|"
    r"reason for referral|"
    r"clinical information|"
    r"blood tests|"
    r"blood results|"
    r"patient details|"
    r"co-morbidities|"
    r"medication|"
    r"allerg"
    r")"
)

_BUILTIN_ADMIN_QUESTION_ALTS = (
    r"has the patient|"
    r"does the patient|"
    r"please confirm|"
    r"is the patient|"
    r"is an interpreter|"
    r"if no,|"
    r"if so,|"
    r"medication list attached|"
    r"transport:"
)


def _build_admin_question_re(custom: list[str]) -> re.Pattern[str]:
    alts = _BUILTIN_ADMIN_QUESTION_ALTS
    if custom:
        alts = alts + "|" + "|".join(custom)
    return re.compile(r"(?i)^\s*(" + alts + r")")


_ADMIN_QUESTION = _build_admin_question_re([])

_FORM_CHROME = re.compile(
    r"(?i)(mandatory field|please place x|referral criteria\s*\(mandatory)"
)

_TABLE_SEP = re.compile(r"^\s*\|?\s*:?-{2,}")


def _has_unchecked(text: str) -> bool:
    return bool(_UNCHECKED.search(text))


def _has_checked(text: str) -> bool:
    return bool(_CHECKED.search(text))


def _cell_core(line: str) -> str:
    return line.strip().lstrip("| ").rstrip(" |").strip()


def _mark(text: str) -> str:
    stripped = text.strip()
    if not stripped:
        return text
    if stripped.startswith(NON_EXTRACTABLE_MARKER):
        return text
    return f"{NON_EXTRACTABLE_MARKER} {stripped}"


def _is_unchecked_only(cell: str) -> bool:
    return bool(_UNCHECKED_ONLY.match(cell.strip()))


def _is_checked_only(cell: str) -> bool:
    return bool(_CHECKED_ONLY.match(cell.strip()))


def _word_before(line: str, index: int) -> str:
    parts = line[:index].split()
    return parts[-1].lower() if parts else ""


def _suppress_unchecked_yes_no(line: str) -> str:
    def _repl(match: re.Match[str]) -> str:
        if _word_before(line, match.start()) in {"yes", "no"}:
            return match.group(0)
        if _CHECKED.search(match.group(1)):
            return match.group(0)
        return f"{NON_EXTRACTABLE_MARKER} {match.group(2)}"

    return re.sub(
        r"(\[[^\]]*\]|\([^)]*\))\s*(Yes|No)\b",
        _repl,
        line,
        flags=re.IGNORECASE,
    )


def _pipe_pair_or_cell(
    cell: str, nxt: str, *, in_appendix: bool
) -> tuple[list[str], int]:
    """Return (output cells, index advance) for one pipe cell and its neighbour."""
    cell_s = cell.strip()
    nxt_s = nxt.strip()

    if in_appendix and cell_s and not _has_checked(cell_s + " " + nxt_s):
        if _is_unchecked_only(nxt_s) or _has_unchecked(cell_s):
            pieces = [_mark(cell_s) if cell_s else cell]
            if nxt_s:
                pieces.append(_mark(nxt_s))
                return pieces, 2
            return pieces, 1

    if cell_s and _is_unchecked_only(nxt_s):
        return [_mark(cell_s), _mark(nxt_s)], 2
    if cell_s and _is_checked_only(nxt_s):
        return [cell_s, nxt_s], 2
    if _is_unchecked_only(cell_s) or (
        _UNCHECKED_PREFIX.match(cell_s) and not _has_checked(cell_s)
    ):
        return [_mark(cell_s)], 1
    if _CHECKED_PREFIX.match(cell_s):
        return [_CHECKED_PREFIX.sub("", cell_s)], 1
    if cell_s and _has_unchecked(cell_s) and not _has_checked(cell_s):
        return [_mark(cell_s)], 1
    if cell_s and _has_unchecked(cell_s) and _has_checked(cell_s):
        return [_suppress_unchecked_yes_no(cell_s)], 1
    if _ADMIN_QUESTION.match(cell_s) or _FORM_CHROME.search(cell_s):
        return [_mark(cell_s) if cell_s else cell], 1
    if in_appendix and cell_s and not _has_checked(cell_s):
        return [_mark(cell_s)], 1
    return [cell], 1


def _normalise_pipe_cells(text: str, *, in_appendix: bool) -> str:
    cells = re.split(r"\s*\|\s*", text)
    out: list[str] = []
    i = 0
    while i < len(cells):
        nxt = cells[i + 1] if i + 1 < len(cells) else ""
        pieces, advance = _pipe_pair_or_cell(cells[i], nxt, in_appendix=in_appendix)
        out.extend(pieces)
        i += advance
    return " | ".join(out)


def _normalise_plain_line(line: str, *, in_appendix: bool) -> str:
    stripped = line.strip()
    if not stripped:
        return line
    if _TABLE_SEP.match(stripped) or _FORM_CHROME.search(stripped):
        return _mark(stripped)
    if _ADMIN_QUESTION.match(stripped):
        return _mark(stripped)
    if in_appendix and not _has_checked(stripped):
        return _mark(stripped)
    line = _suppress_unchecked_yes_no(line)
    stripped = line.strip()
    if _has_unchecked(stripped) and not _has_checked(stripped):
        return _mark(stripped)
    return line


def _needs_normalisation(text: str) -> bool:
    if "[" in text or "]" in text or "(" in text:
        # Cheap gate; detailed patterns run per line.
        if _UNCHECKED.search(text) or _CHECKED.search(text):
            return True
    lower = text.lower()
    return bool(
        "appendix " in lower
        or "referral criteria" in lower
        or "symptoms pathway" in lower
        or "has the patient" in lower
        or "does the patient" in lower
        or "is an interpreter" in lower
        or "please confirm" in lower
        or "please take" in lower
        or "please put" in lower
    )


def normalize_form_checkbox_text(text: str) -> str:
    """Mark unchecked / template / admin form rows as non-extractable."""
    from libs.ner.form_layout_rules import apply_form_layout_rules

    if not text:
        return text
    if not _needs_normalisation(text):
        return apply_form_layout_rules(text)

    lines = text.splitlines()
    in_appendix = False
    result: list[str] = []
    for line in lines:
        core = _cell_core(line)
        if _APPENDIX_START.search(core):
            in_appendix = True
            result.append(_mark(line.strip() or line))
            continue
        if in_appendix and _APPENDIX_END.search(core):
            in_appendix = False
            result.append(_normalise_plain_line(line, in_appendix=False))
            continue
        if "|" in line:
            result.append(_normalise_pipe_cells(line, in_appendix=in_appendix))
        else:
            result.append(_normalise_plain_line(line, in_appendix=in_appendix))
    return apply_form_layout_rules("\n".join(result))


def _fetch_neo4j_checkbox_rules(family: str) -> list[dict]:
    """Fetch :NerGuardRule nodes for the checkbox normaliser from Neo4j.

    Returns [] when Neo4j is unreachable.
    """
    try:
        from libs.pipeline.config_loader import _fetch_neo4j_rules

        return _fetch_neo4j_rules(family)
    except Exception:
        logger.warning(
            "Could not fetch checkbox norm rules from Neo4j -- using builtins",
            exc_info=True,
        )
        return []


def reload_checkbox_norm() -> None:
    """Rebuild the admin-question regex from Neo4j custom rules.

    Call this after creating or deactivating an :NerGuardRule node with
    family='checkbox_norm'.
    """
    global _ADMIN_QUESTION
    import json

    rows = _fetch_neo4j_checkbox_rules("checkbox_norm")
    custom: list[str] = []
    for row in rows:
        if not row.get("active", True):
            continue
        try:
            payload = json.loads(row.get("payload") or "{}")
        except (ValueError, TypeError):
            payload = {}
        rule_type = payload.get("rule_type") or row.get("rule_type", "admin_question")
        pattern = payload.get("pattern") or row.get("pattern", "")
        if pattern and rule_type == "admin_question":
            custom.append(
                re.escape(pattern)
                if not any(c in pattern for c in r".*+?[](){}^$|\\")
                else pattern
            )
    _ADMIN_QUESTION = _build_admin_question_re(custom)
    logger.info(
        "Checkbox norm reloaded: %d custom admin-question patterns", len(custom)
    )


def extractable_clinical_lines(text: str) -> list[str]:
    """Return normalised lines/cells still usable as clinical extraction input."""
    normalised = normalize_form_checkbox_text(text)
    out: list[str] = []
    for raw in normalised.splitlines():
        pieces = raw.split("|") if "|" in raw else [raw]
        for piece in pieces:
            stripped = piece.strip()
            if not stripped:
                continue
            if NON_EXTRACTABLE_MARKER in stripped:
                continue
            if _is_unchecked_only(stripped) or _is_checked_only(stripped):
                continue
            if _has_unchecked(stripped) and not _has_checked(stripped):
                continue
            if _TABLE_SEP.match(stripped) or _FORM_CHROME.search(stripped):
                continue
            if _APPENDIX_START.search(stripped):
                continue
            out.append(stripped)
    return out
