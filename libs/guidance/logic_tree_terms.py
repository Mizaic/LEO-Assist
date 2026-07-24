"""Free-text term -> SNOMED concept lookups over AppropriatenessRule.logicJson.

Atlas trace:
  DO: DO-BE96444E
  DI: DI-BAC284B4
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-BE96444E")

Shared by two callers that both need "which SNOMED concept(s) has this
free-text phrase already been mapped to, across the whole rule library":

  - The live concept-mapping nudge (``services/terminology_api``): given
    one highlighted phrase, suggest the reviewer's own prior pick as a
    default -- never auto-applied, just surfaced (see
    ``highlight-to-build wizard`` plan, "soft nudge only").
  - The periodic term-conflict audit script: given every rule, find
    phrases that currently resolve to MORE than one SNOMED code across
    the library, as a lower-frequency backstop for drift the live nudge
    cannot catch (a reviewer who deliberately picks a different code is
    always free to).

Kept dependency-free (no Neo4j client import) so both callers own their
own query + connection lifecycle; this module only walks/parses the
JSON tree once it already has it.
"""

from __future__ import annotations

import json
import re
from typing import Any

_TRAILING_SEMANTIC_TAG = re.compile(r"\s*\([^)]*\)\s*$")
_NON_WORD = re.compile(r"[^a-z0-9\s]")
_WHITESPACE = re.compile(r"\s+")


def normalise_concept_term(term: str | None) -> str:
    """Lowercase, drop a trailing SNOMED "(semantic tag)" suffix, and
    collapse punctuation/whitespace so "Vomiting (finding)" and
    "vomiting" compare equal.
    """
    if not term:
        return ""
    stripped = _TRAILING_SEMANTIC_TAG.sub("", term).strip().lower()
    stripped = _NON_WORD.sub(" ", stripped)
    return _WHITESPACE.sub(" ", stripped).strip()


def parse_logic_json(value: Any) -> dict | None:
    """Return the parsed logic tree, or None if ``value`` is unusable.

    Mirrors ``services.api.app.services._logic_tree.parse_logic_json``;
    duplicated here (rather than imported) so this module has no
    cross-service dependency -- ``services/terminology_api`` and
    ``services/api`` are deployed as separate Container Apps.
    """
    if isinstance(value, dict):
        return value
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def walk_concept_criteria(node: Any) -> list[dict]:
    """Return every CONCEPT leaf's ``criterion`` dict in document order.

    Tolerant like the sibling walker in ``_logic_tree.py``: missing
    fields, unknown ``kind`` values, and non-dict children are silently
    skipped rather than raising.
    """
    out: list[dict] = []
    _walk(node, out)
    return out


def _walk(node: Any, out: list[dict]) -> None:
    if not isinstance(node, dict):
        return
    if str(node.get("kind") or "").lower() == "concept":
        criterion = node.get("criterion")
        if isinstance(criterion, dict) and criterion.get("snomed_concept_id"):
            out.append(criterion)
        return
    for child in node.get("children") or []:
        _walk(child, out)


def concept_terms(criterion: dict) -> set[str]:
    """Every normalised phrase this criterion could be found under: the
    free-text ``term`` the reviewer typed/highlighted, and the SNOMED
    ``preferred_term`` with its semantic-tag suffix stripped.
    """
    terms: set[str] = set()
    for raw in (criterion.get("term"), criterion.get("preferred_term")):
        normalised = normalise_concept_term(raw)
        if normalised:
            terms.add(normalised)
    return terms
