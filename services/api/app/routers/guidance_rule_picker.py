"""The "pick a rule" endpoint used by the logic-tree RULE_FIRED editor.

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
        return out
    finally:
        client.close()
