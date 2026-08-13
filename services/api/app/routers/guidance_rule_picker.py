"""The "pick a rule" endpoint used by the logic-tree RULE_FIRED editor.

Atlas trace:
  DO: DO-EC41233C
  DI: DI-9D0DF618
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-EC41233C")

Split out of the retired test-patients router -- this endpoint has no
dependency on the :TestPatient library, it just lists active rules in
plain English so an author can pick a prerequisite rule.

Mounted under ``/guidance`` (the proxy at /api/* exposes this to the
browser). Requires the ai.admin role.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.db.neo4j_client import CodingGraphClient
from app.services._logic_tree import parse_logic_json, trigger_terms_preview
from app.services.natural_sort import natural_sort_key
from app.deps import require_admin
from libs.auth.org_scope import CallerScope
from libs.cypher.guidance_rule_picker_queries import LIST_RULES_FOR_PICKER

router = APIRouter(prefix="/guidance", tags=["guidance-rule-picker"])


@router.get("/rule-picker")
def list_rules_for_picker(
    guideline_id: str | None = Query(default=None),
    _scope: CallerScope = Depends(require_admin),
) -> list[dict]:
    """Plain-English picker payload for rule-depends-on-rule editing.

    Joins the rule with its Recommendation, Chapter, and ActionGroup so
    the dropdown can show the verbatim NICE recommendation, chapter
    title, action priority, and up to three SNOMED triggers -- the
    author never has to look at the raw rule_id.
    """
    client = CodingGraphClient()
    try:
        rows = client.run(LIST_RULES_FOR_PICKER, guideline_id=guideline_id)
        out: list[dict] = []
        for raw in rows:
            row = dict(raw)
            tree = parse_logic_json(row.pop("logic_json", None))
            row["trigger_terms"] = (
                trigger_terms_preview(tree, limit=3) if tree is not None else []
            )
            out.append(row)
        return _sort_picker_rows(out)
    finally:
        client.close()


def _sort_picker_rows(rows: list[dict]) -> list[dict]:
    """Re-sort picker rows on the dotted rule name, not plain string order.

    The Cypher ``ORDER BY g.title, ch.title, rule.name`` sorts
    ``rule.name`` (e.g. ``"1.11.1"``) as a plain string, so ``"1.11.1"``
    comes back before ``"1.2.1"``. Keeps the coarse guideline/chapter
    grouping (still fine as a plain string sort) and only replaces the
    ``rule.name`` tiebreak with numeric-segment comparison.
    """
    ordered = sorted(
        rows,
        key=lambda row: (
            row.get("guideline_title") or "",
            row.get("chapter_title") or "",
            natural_sort_key(row.get("name") or row.get("rule_id")),
        ),
    )
    return _unique_by_rule_id(ordered)


def _unique_by_rule_id(rows: list[dict]) -> list[dict]:
    """One row per rule. Action joins can otherwise repeat the same id."""
    seen: set[str] = set()
    unique: list[dict] = []
    for row in rows:
        rid = str(row.get("rule_id") or "")
        if not rid or rid in seen:
            continue
        seen.add(rid)
        unique.append(row)
    return unique
