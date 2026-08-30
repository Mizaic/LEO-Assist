"""Wrap AND-of-findings as AND(sex, OR(findings)) for NICE OR wording.

Used when a NICE row says lump OR ulceration OR bleeding but the
extracted tree ANDs those findings. Sex stays a hard AND sibling.
Seeds and source_row_text are copied through unchanged.

Atlas:
  UN-5F3BF083
  DI-8BAC9BB3
  DO-62FE139E
  VT-766B13F8
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

_AND = "AND"
_OR = "OR"
_CONCEPT = "CONCEPT"
_DEMO = "DEMOGRAPHIC"


def or_wrap_and_findings(tree: dict[str, Any]) -> dict[str, Any]:
    """Return a copy with sibling CONCEPT findings OR-wrapped under AND."""
    out = deepcopy(tree)
    if not _is_and_of_sex_and_findings(out):
        return out
    children = [c for c in (out.get("children") or []) if isinstance(c, dict)]
    sex_nodes = [c for c in children if _is_sex_leaf(c)]
    findings = [c for c in children if _is_concept(c)]
    out["children"] = [*sex_nodes, {"kind": _OR, "children": findings}]
    return out


def _is_and_of_sex_and_findings(node: dict[str, Any]) -> bool:
    if str(node.get("kind") or "").upper() != _AND:
        return False
    children = [c for c in (node.get("children") or []) if isinstance(c, dict)]
    if len(children) < 3:
        return False
    if any(_is_or_of_concepts(c) for c in children):
        return False
    sex = [c for c in children if _is_sex_leaf(c)]
    findings = [c for c in children if _is_concept(c)]
    if len(sex) != 1 or len(findings) < 2:
        return False
    return len(sex) + len(findings) == len(children)


def _is_sex_leaf(node: dict[str, Any]) -> bool:
    return (
        str(node.get("kind") or "").upper() == _DEMO
        and str(node.get("field") or "").lower() == "sex"
    )


def _is_concept(node: dict[str, Any]) -> bool:
    return str(node.get("kind") or "").upper() == _CONCEPT


def _is_or_of_concepts(node: dict[str, Any]) -> bool:
    if str(node.get("kind") or "").upper() != _OR:
        return False
    kids = [c for c in (node.get("children") or []) if isinstance(c, dict)]
    return bool(kids) and all(_is_concept(c) for c in kids)
