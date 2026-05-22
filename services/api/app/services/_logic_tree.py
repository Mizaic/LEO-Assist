"""Shared walker for AppropriatenessRule.logicJson trees.

Atlas trace:
  DO: DO-92F92EFB
  DI: DI-88C1715A
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-92F92EFB")

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


def extract_satisfying_concepts(node: Any) -> list[dict]:
    """Return the smallest set of triggers that would FIRE the rule.

    Many production rules are written as OR / AT_LEAST trees: the
    mesothelioma 2WW rule fires on age >= 40 plus EITHER two of six
    symptoms OR a smoker plus one symptom OR asbestos exposure plus
    one symptom. Asking the LLM to invent every concept is wasteful
    and (worse) breaks the scaffolder if the model picks a different
    legal subset to write up. The validator demands the LLM mention
    every term it is given, so the briefing list MUST be the minimum
    that makes the rule fire and nothing more.

    Walker semantics:

      - ``concept``    -> [the trigger]
      - ``demographic`` -> [] (handled outside this walker)
      - ``NOT``        -> [] (must NOT appear in notes)
      - ``AND``        -> union of every non-empty child satisfying-set
      - ``OR``         -> the smallest non-empty child satisfying-set,
                          ties broken by document order
      - ``AT_LEAST(min, children)`` -> the ``min`` smallest non-empty
                          child satisfying-sets, unioned

    The result is de-duped by ``concept_id`` in document order, so the
    LLM sees a stable, smallest "you must mention these" briefing.

    Returns the same trigger shape as :func:`extract_concept_triggers`
    so callers can swap the two without re-mapping fields.
    """
    if not isinstance(node, dict):
        return []
    triggers = _satisfying(node)
    seen: set[str] = set()
    out: list[dict] = []
    for trig in triggers:
        cid = trig["concept_id"]
        if cid in seen:
            continue
        seen.add(cid)
        out.append(trig)
    return out


def extract_satisfying_concept_sets(node: Any) -> list[list[dict]]:
    """Return one minimum trigger set for each top-level pathway.

    ``extract_satisfying_concepts`` intentionally returns only one
    minimum set so a single AI scaffold does not have to mention every
    alternative branch. For test coverage, however, callers sometimes
    need one patient per alternative pathway. This helper recognises
    the common pathway shapes:

      - ``OR[pathway_a, pathway_b, ...]``
      - ``AND[global_prereq..., OR[pathway_a, pathway_b, ...]]``

    and returns a de-duplicated satisfying concept set for each branch.
    Non-pathway trees fall back to a single satisfying set.
    """
    return [p["triggers"] for p in extract_satisfying_pathways(node)]


def extract_satisfying_pathways(node: Any) -> list[dict]:
    """Return pathway-specific triggers and demographic constraints.

    A rule can be split by concepts, demographics, or both. For
    example, an OR may have one branch for age < 50 and another for
    age >= 50 with the same trigger concept. Returning only concept
    sets would collapse those two branches into one patient.
    """
    if not isinstance(node, dict):
        return []
    return _dedup_pathways(_pathways(node))


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
        criterion.get("preferred_term") or criterion.get("term") or str(concept_id)
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


# ---------------------------------------------------------------------------
# Satisfying-path walker -- minimum trigger subset that fires the rule.
# ---------------------------------------------------------------------------


def _satisfying(node: dict) -> list[dict]:
    """Return one minimal satisfying trigger list for ``node``.

    Tolerant: unknown ``kind`` values yield an empty list rather than
    raising, so a half-edited rule still scaffolds against whatever
    branches the walker can interpret.
    """
    kind = str(node.get("kind") or "").lower()
    if kind == "concept":
        trig = _concept_to_trigger(node.get("criterion"))
        return [trig] if trig is not None else []
    if kind in ("demographic", "not"):
        # Demographics are validated separately; NOT clauses must be
        # absent from the notes, never present, so contribute nothing.
        return []
    children = [c for c in (node.get("children") or []) if isinstance(c, dict)]
    if kind == "and":
        return _satisfying_and(children)
    if kind == "or":
        return _satisfying_or(children)
    if kind == "at_least":
        return _satisfying_at_least(node, children)
    return []


def _satisfying_and(children: list[dict]) -> list[dict]:
    out: list[dict] = []
    for child in children:
        out.extend(_satisfying(child))
    return out


def _satisfying_or(children: list[dict]) -> list[dict]:
    best: list[dict] | None = None
    for child in children:
        result = _satisfying(child)
        if not result:
            continue
        if best is None or len(result) < len(best):
            best = result
    return best or []


def _satisfying_at_least(node: dict, children: list[dict]) -> list[dict]:
    try:
        minimum = int(node.get("min") or 1)
    except (TypeError, ValueError):
        minimum = 1
    if minimum < 1:
        minimum = 1
    candidates = [r for r in (_satisfying(c) for c in children) if r]
    if len(candidates) < minimum:
        # Cannot satisfy AT_LEAST(min) -- caller treats empty as
        # "no trigger path"; the scaffolder will then fall back or
        # raise ScaffoldError further up the stack.
        return []
    candidates.sort(key=len)
    out: list[dict] = []
    for chosen in candidates[:minimum]:
        out.extend(chosen)
    return out


def _pathways(node: dict) -> list[dict]:
    kind = str(node.get("kind") or "").lower()
    if kind == "concept":
        trig = _concept_to_trigger(node.get("criterion"))
        return [_pathway([trig], [])] if trig is not None else []
    if kind == "demographic":
        constraint = _demographic_to_constraint(node)
        return [_pathway([], [constraint])] if constraint is not None else []
    if kind == "not":
        return [_pathway([], [])]
    children = _child_dicts(node)
    if kind == "and":
        return _and_pathways(children)
    if kind == "or":
        return _dedup_pathways([p for child in children for p in _pathways(child)])
    if kind == "at_least":
        return _at_least_pathways(node, children)
    return []


def _and_pathways(children: list[dict]) -> list[dict]:
    paths = [_pathway([], [])]
    for child in children:
        child_paths = _pathways(child)
        if not child_paths:
            continue
        paths = [_merge_pathways(a, b) for a in paths for b in child_paths]
    return _dedup_pathways(paths)


def _at_least_pathways(node: dict, children: list[dict]) -> list[dict]:
    try:
        minimum = max(1, int(node.get("min") or 1))
    except (TypeError, ValueError):
        minimum = 1
    candidates = [p for child in children for p in _pathways(child)]
    candidates = [
        p for p in candidates if p["triggers"] or p["demographic_constraints"]
    ]
    if len(candidates) < minimum:
        return []
    candidates.sort(key=lambda p: len(p["triggers"]))
    merged = _pathway([], [])
    for candidate in candidates[:minimum]:
        merged = _merge_pathways(merged, candidate)
    return [merged]


def _pathway(triggers: list[dict | None], constraints: list[dict | None]) -> dict:
    return {
        "triggers": _dedup_triggers([t for t in triggers if t is not None]),
        "demographic_constraints": _dedup_constraints(
            [c for c in constraints if c is not None]
        ),
    }


def _merge_pathways(left: dict, right: dict) -> dict:
    return _pathway(
        [*left.get("triggers", []), *right.get("triggers", [])],
        [
            *left.get("demographic_constraints", []),
            *right.get("demographic_constraints", []),
        ],
    )


def _child_dicts(node: dict) -> list[dict]:
    return [c for c in (node.get("children") or []) if isinstance(c, dict)]


def _dedup_pathways(pathways: list[dict]) -> list[dict]:
    out: list[dict] = []
    seen: set[tuple] = set()
    for raw in pathways:
        path = _pathway(
            raw.get("triggers", []),
            raw.get("demographic_constraints", []),
        )
        if not path["triggers"] and not path["demographic_constraints"]:
            continue
        key = (
            tuple(t["concept_id"] for t in path["triggers"]),
            _constraint_key(path["demographic_constraints"]),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(path)
    return out


def _dedup_triggers(triggers: list[dict]) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for trig in triggers:
        cid = trig.get("concept_id")
        if not cid or cid in seen:
            continue
        seen.add(cid)
        out.append(trig)
    return out


def _dedup_constraints(constraints: list[dict]) -> list[dict]:
    seen: set[tuple] = set()
    out: list[dict] = []
    for constraint in constraints:
        key = _constraint_key([constraint])
        if key in seen:
            continue
        seen.add(key)
        out.append(constraint)
    return out


def _constraint_key(constraints: list[dict]) -> tuple:
    return tuple(
        (
            c.get("field"),
            c.get("operator"),
            _hashable(c.get("value")),
            c.get("unit"),
        )
        for c in constraints
    )
