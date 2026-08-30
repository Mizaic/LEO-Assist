"""Classify referral-bundle documents as clinical or administrative.

Atlas trace:
  DI: DI-C2C1E3E8
  DO: DO-BB31F9A5
  VT: VT-6FE171F8
  Risk: R-07FC04CB
  A Generic Referral Cover Sheet is a GP-practice template (NHS Standard
  Contract clause 6.13, Jess's Rule). It must not supply clinical facts
  or the SBAR headline. Classification is by title and body markers,
  not by trust or file type.
"""

from __future__ import annotations

import re
from typing import Iterator, Literal

from libs.ner.form_checkbox_normalizer import NON_EXTRACTABLE_MARKER

DocumentRole = Literal["clinical", "administrative"]

_DOC_HEADER_RE = re.compile(
    r"(---\s*Document:\s*(.+?)\s*---[ \t]*\n?)",
    re.IGNORECASE,
)
_ADMIN_TITLE_RE = re.compile(r"cover\s*sheet", re.IGNORECASE)
_ADMIN_BODY_RE = re.compile(
    r"jess'?s\s+rule|clause\s*6\.13|must\s+not\s+be\s+rejected",
    re.IGNORECASE,
)


def classify_document_role(title: str, text: str) -> DocumentRole:
    """Return administrative for a cover sheet, otherwise clinical."""
    if _ADMIN_TITLE_RE.search(title or ""):
        return "administrative"
    if _ADMIN_BODY_RE.search(text or ""):
        return "administrative"
    return "clinical"


def _iter_documents(text: str) -> Iterator[tuple[str, str, str]]:
    """Yield (title, header, body) for each document in a bundle string."""
    matches = list(_DOC_HEADER_RE.finditer(text))
    if not matches:
        yield "", "", text
        return
    if matches[0].start() > 0:
        yield "", "", text[: matches[0].start()]
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        yield match.group(2).strip(), match.group(1), text[match.end() : end]


def _mark_lines(text: str) -> str:
    """Prefix every non-empty line so llm_facing_text drops the block."""
    marked: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith(NON_EXTRACTABLE_MARKER):
            marked.append(f"{NON_EXTRACTABLE_MARKER} {stripped}")
        else:
            marked.append(line)
    if text.endswith("\n"):
        return "\n".join(marked) + "\n"
    return "\n".join(marked)


def seal_administrative_documents(text: str) -> str:
    """Mark every line of an administrative document as non-extractable."""
    if not text:
        return text
    parts: list[str] = []
    for title, header, body in _iter_documents(text):
        block = f"{header}{body}"
        if classify_document_role(title, block) == "administrative":
            parts.append(_mark_lines(block))
        else:
            parts.append(block)
    return "".join(parts)


def clinical_letter_text(text: str) -> str:
    """Return only clinical documents, for SBAR headline fallback."""
    if not text:
        return ""
    kept: list[str] = []
    for title, header, body in _iter_documents(text):
        block = f"{header}{body}"
        if classify_document_role(title, block) == "clinical":
            stripped = block.strip()
            if stripped:
                kept.append(stripped)
    return "\n\n".join(kept)
