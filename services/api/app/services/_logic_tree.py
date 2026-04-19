"""Shared walker for AppropriatenessRule.logicJson trees.

The v2 guidance schema persists every concept criterion and demographic
constraint as a nested JSON tree on ``rule.logicJson``. There are no
``:CriteriaGroup`` nodes or ``:APPLIES_TO`` relationships in the live
knowledge graph, so any code that needs to know "what does this rule
trigger on?" must read the JSON, not the relationships.

Two consumers share this walker so they always see the same answer:

  - test_patient_scaffolder -- needs the full trigger list and any
    demographic constraints to instruct Haiku what to draft and to
    reject drafts that break a constraint.
  - test_patient_service.list_rules_for_picker -- needs the first few
    SNOMED preferred-terms so the rule picker can show a concrete cue
    next to the rule name.

Tree shape (abbreviated):

    {
      "kind": "AND" | "OR" | "AT_LEAST" | "NOT" | "concept" | "demographic",
      "min": <int, AT_LEAST only>,
      "field": "age" | "sex" | ..., "operator": ">=", "value": 40,
      "unit": "years",                                      # demographic leaf
      "criterion": {
        "snomed_concept_id": "49727002",
        "preferred_term": "Cough (finding)",
        "term": "cough"
      },                                                    # concept leaf
      "children": [...]
    }

The walker is intentionally tolerant: missing fields, unknown ``kind``
values and non-dict children are silently skipped instead of raising,
so a half-edited rule still surfaces whatever criteria it does have.
The scaffolder layers its own loud-failure check on top (no concept
leaves -> ScaffoldError).
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


def parse_logic_json(value: Any) -> dict | None:
    """Return the parsed logic tree, or None if ``value`` is unusable.

    Accepts either an already-decoded dict (some callers pre-parse) or a
    JSON string (Cypher returns it as a string property). Anything else
    returns None so callers can branch on a single None check.
    """
    if isinstance(value, dict):
        return value
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        logger.debug("logicJson failed to parse, treating as empty", exc_info=True)
        return None
    return parsed if isinstance(parsed, dict) else None


def extract_concept_triggers(node: Any) -> list[dict]:
    """Walk the tree and return concept triggers in document order.

    Each trigger is shaped like the row the old Cypher walk used to
    produce::

        {
          "concept_id":     "49727002",
          "preferred_term": "Cough (finding)",
          "predicate":      "LOGIC"
        }

    so downstream callers (the prompt formatter, the validator, the
    picker preview) keep their existing field names.

    Triggers are de-duped by ``concept_id`` -- a single concept that
    appears in three branches of an OR still shows up once.
    """
    if not isinstance(node, dict):
        return []
    seen: set[str] = set()
    out: list[dict] = []
    _walk_for_triggers(node, seen, out)
    return out


def extract_demographic_constraints(node: Any) -> list[dict]:
    """Walk the tree and return every ``demographic`` leaf.

    Each constraint is shaped like the row the old ``APPLIES_TO`` walk
    used to produce::

        {"field": "age", "operator": ">=", "value": 40, "unit": "years"}

    Constraints are de-duped by (field, operator, value, unit).
    """
    if not isinstance(node, dict):
        return []
    seen: set[tuple] = set()
    out: list[dict] = []
    _walk_for_demographics(node, seen, out)
    return out


def trigger_terms_preview(node: Any, *, limit: int = 3) -> list[str]:
    """Return up to ``limit`` SNOMED preferred terms for a picker preview.

    Mirrors the old ``LIST_RULES_FOR_PICKER`` behaviour of taking the
    first three terms in document order. Missing terms fall back to the
    short ``term`` field, then to the SNOMED id, then are skipped.
    """
    out: list[str] = []
    seen: set[str] = set()
    for trig in extract_concept_triggers(node):
        term = (trig.get("preferred_term") or "").strip()
        if not term or term in seen:
            continue
        seen.add(term)
        out.append(term)
        if len(out) >= limit:
            break
    return out


# ---------------------------------------------------------------------------
# Internal walker -- kept short to stay under the cyclomatic limit.
# ---------------------------------------------------------------------------


def _walk_for_triggers(node: dict, seen: set[str], out: list[dict]) -> None:
    kind = str(node.get("kind") or "").lower()
    if kind == "concept":
        trig = _concept_to_trigger(node.get("criterion"))
        if trig is not None and trig["concept_id"] not in seen:
            seen.add(trig["concept_id"])
            out.append(trig)
        return
    for child in node.get("children") or []:
        if isinstance(child, dict):
            _walk_for_triggers(child, seen, out)


def _concept_to_trigger(criterion: Any) -> dict | None:
    if not isinstance(criterion, dict):
        return None
    concept_id = criterion.get("snomed_concept_id") or criterion.get("concept_id")
    if not concept_id:
        return None
    preferred = (
        criterion.get("preferred_term")
        or criterion.get("term")
        or str(concept_id)
    )
    return {
        "concept_id": str(concept_id),
        "preferred_term": str(preferred),
        "predicate": "LOGIC",
    }


def _walk_for_demographics(node: dict, seen: set[tuple], out: list[dict]) -> None:
    kind = str(node.get("kind") or "").lower()
    if kind == "demographic":
        constraint = _demographic_to_constraint(node)
        if constraint is not None:
            key = (
                constraint["field"],
                constraint["operator"],
                _hashable(constraint["value"]),
                constraint["unit"],
            )
            if key not in seen:
                seen.add(key)
                out.append(constraint)
        return
    for child in node.get("children") or []:
        if isinstance(child, dict):
            _walk_for_demographics(child, seen, out)


def _demographic_to_constraint(node: dict) -> dict | None:
    field = (node.get("field") or "").strip().lower()
    operator = (node.get("operator") or "").strip()
    if not field and not operator:
        return None
    return {
        "field": field or None,
        "operator": operator or None,
        "value": node.get("value"),
        "unit": (node.get("unit") or "").strip() or None,
    }


def _hashable(value: Any) -> Any:
    if isinstance(value, (list, dict)):
        return json.dumps(value, sort_keys=True)
    return value
