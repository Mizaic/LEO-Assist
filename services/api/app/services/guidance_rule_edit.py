"""Manual edit pathway for AI-generated AppropriatenessRules.

When a reviewer edits a pending rule (rather than approve/reject), this
module is responsible for:

1. Validating the edited logic tree (shape, depth, node count, that every
   referenced SNOMED concept exists in the knowledge graph).
2. Writing a brand-new ``AppropriatenessRule`` node carrying the edited
   ``logicJson``, with status ``active``.
3. Marking the predecessor rule ``superseded`` and linking the new rule
   to it via ``[:SUPERSEDES]`` so the existing diff/audit views keep working.
4. Writing a ``GuidanceAuditEvent`` recording who made the edit and why.

Kept in its own module so the router file does not balloon further and so
the validation logic can be unit-tested in isolation.

Design Controls: DI-LEO-AI-154, DO-LEO-AI-150, R-LEO-AI-106, VT-LEO-AI-152.
"""

from __future__ import annotations

import json
import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

# -- Tree limits ---------------------------------------------------------------
# Caps that defend against pathological trees pushed via the edit API. Real
# NICE rules max out at ~30 nodes and depth 4 (per inspection of the existing
# generated set), so these limits leave plenty of headroom while bounding
# server-side work and downstream bitmap compile time.
MAX_TREE_DEPTH = 6
MAX_NODE_COUNT = 80

_GROUP_KINDS = {"AND", "OR", "NOT", "AT_LEAST"}
_LEAF_KINDS = {"CONCEPT", "DEMOGRAPHIC"}
_ALL_KINDS = _GROUP_KINDS | _LEAF_KINDS


# -- Pydantic models -----------------------------------------------------------


class LogicCriterion(BaseModel):
    """Resolved SNOMED criterion attached to a CONCEPT node."""

    snomed_concept_id: str = Field(min_length=1)
    preferred_term: str = Field(min_length=1)
    semantic_tag: str = ""
    term: str = ""


class LogicNode(BaseModel):
    """One node in the rule logic tree. Recursive via ``children``.

    ``model_config = {"extra": "forbid"}`` rejects unknown keys so a malformed
    payload cannot smuggle hidden state into the persisted rule.
    """

    model_config = {"extra": "forbid"}

    kind: str
    node_id: str | None = None
    children: list["LogicNode"] | None = None
    min: int | None = None
    criterion: LogicCriterion | None = None
    field: str | None = None
    operator: str | None = None
    value: float | str | None = None
    unit: str | None = None

    @field_validator("kind")
    @classmethod
    def _check_kind(cls, v: str) -> str:
        upper = v.upper()
        if upper not in _ALL_KINDS:
            raise ValueError(f"Unknown node kind {v!r}; expected one of {sorted(_ALL_KINDS)}")
        return upper


class RuleUpdates(BaseModel):
    """Fields a reviewer may change on a pending rule.

    ``action`` is the SNOMED-coded recommended procedure that fires when
    the rule matches (e.g. "Plain chest X-ray"). When omitted, the
    predecessor rule's existing actionJson is preserved unchanged --
    there is deliberately no path that silently nulls it out (DI-170).
    """

    model_config = {"extra": "forbid"}

    name: str | None = Field(default=None, max_length=200)
    strength: str | None = Field(default=None, max_length=64)
    logic_tree: LogicNode
    action: LogicCriterion | None = None


# -- Validation ----------------------------------------------------------------


class LogicTreeValidationError(ValueError):
    """Raised when the supplied logic tree fails server-side validation."""


def validate_logic_tree(root: LogicNode) -> set[str]:
    """Walk the tree, enforce limits, return the set of SNOMED concept ids used.

    Raises ``LogicTreeValidationError`` on any structural problem. The returned
    concept-id set is used downstream to confirm every referenced concept
    exists in the knowledge graph before the new rule is persisted.
    """
    counter = {"nodes": 0}
    concept_ids: set[str] = set()
    _walk(root, depth=1, counter=counter, concept_ids=concept_ids)
    if counter["nodes"] > MAX_NODE_COUNT:
        raise LogicTreeValidationError(
            f"Tree has {counter['nodes']} nodes; max allowed is {MAX_NODE_COUNT}."
        )
    return concept_ids


def _walk(
    node: LogicNode,
    *,
    depth: int,
    counter: dict[str, int],
    concept_ids: set[str],
) -> None:
    counter["nodes"] += 1
    if depth > MAX_TREE_DEPTH:
        raise LogicTreeValidationError(
            f"Tree exceeds max depth of {MAX_TREE_DEPTH} levels."
        )

    kind = node.kind
    if kind == "CONCEPT":
        _validate_concept_node(node)
        concept_ids.add(node.criterion.snomed_concept_id)  # type: ignore[union-attr]
        return
    if kind == "DEMOGRAPHIC":
        _validate_demographic_node(node)
        return

    children = node.children or []
    if not children:
        raise LogicTreeValidationError(f"{kind} node must have at least one child.")
    if kind == "NOT" and len(children) != 1:
        raise LogicTreeValidationError("NOT node must have exactly one child.")
    if kind == "AT_LEAST":
        if node.min is None or node.min < 1:
            raise LogicTreeValidationError("AT_LEAST node requires min >= 1.")
        if node.min > len(children):
            raise LogicTreeValidationError(
                "AT_LEAST min cannot be greater than the number of children."
            )

    for child in children:
        _walk(child, depth=depth + 1, counter=counter, concept_ids=concept_ids)


def _validate_concept_node(node: LogicNode) -> None:
    if node.criterion is None:
        raise LogicTreeValidationError("CONCEPT node is missing a criterion.")
    if not node.criterion.snomed_concept_id:
        raise LogicTreeValidationError("CONCEPT criterion is missing snomed_concept_id.")


_VALID_DEMOGRAPHIC_FIELDS = {"age", "sex"}
_VALID_OPERATORS = {">=", "<=", ">", "<", "=", "between"}


def _validate_demographic_node(node: LogicNode) -> None:
    if not node.field or node.field.lower() not in _VALID_DEMOGRAPHIC_FIELDS:
        raise LogicTreeValidationError(
            f"DEMOGRAPHIC node has unsupported field {node.field!r}; "
            f"expected one of {sorted(_VALID_DEMOGRAPHIC_FIELDS)}."
        )
    if not node.operator or node.operator not in _VALID_OPERATORS:
        raise LogicTreeValidationError(
            f"DEMOGRAPHIC node has unsupported operator {node.operator!r}."
        )
    if node.value is None or (isinstance(node.value, str) and not node.value.strip()):
        raise LogicTreeValidationError("DEMOGRAPHIC node is missing a value.")


# -- Cypher --------------------------------------------------------------------

_VERIFY_CONCEPTS = """
UNWIND $concept_ids AS cid
OPTIONAL MATCH (c:SnomedConcept {conceptId: cid})
RETURN cid AS concept_id, c.conceptId IS NOT NULL AS exists
"""


_FETCH_PREDECESSOR = """
MATCH (rule:AppropriatenessRule {id: $rule_id})<-[:HAS_RULE]-(rec:Recommendation)
RETURN rule.status AS status,
       rule.name AS name,
       rule.strength AS strength,
       coalesce(rule.compileScopeId, '') AS compile_scope_id,
       rec.id AS recommendation_id,
       coalesce(rec.verbatim, '') AS verbatim
"""


_INSERT_EDITED_RULE = """
MATCH (rec:Recommendation {id: $recommendation_id})
MATCH (pred:AppropriatenessRule {id: $predecessor_id})
CREATE (rule:AppropriatenessRule {
    id:                          $rule_id,
    name:                        $name,
    strength:                    $strength,
    status:                      'active',
    schemaVersion:               2,
    logicJson:                   $logic_json,
    actionJson:                  coalesce($action_json, pred.actionJson),
    verifierJson:                pred.verifierJson,
    rawLogicJson:                pred.rawLogicJson,
    generatedBy:                 'human_edit',
    promptConfigName:            pred.promptConfigName,
    promptConfigVer:             pred.promptConfigVer,
    compileScopeType:            'guideline',
    compileScopeId:              pred.compileScopeId,
    previousRecommendationText:  $verbatim,
    createdAt:                   datetime(),
    reviewedAt:                  datetime(),
    reviewedBy:                  $reviewer
})
MERGE (rec)-[:HAS_RULE]->(rule)
MERGE (rule)-[:SUPERSEDES]->(pred)
SET pred.status        = 'superseded',
    pred.supersededAt  = datetime(),
    pred.supersededBy  = $reviewer
MERGE (audit:GuidanceAuditEvent {id: $event_id})
ON CREATE SET
    audit.ruleId              = $rule_id,
    audit.predecessorRuleId   = $predecessor_id,
    audit.action              = 'edit',
    audit.reviewer            = $reviewer,
    audit.reason              = $reason,
    audit.timestamp           = datetime(),
    audit.immutable           = true
MERGE (rule)-[:HAS_AUDIT_EVENT]->(audit)
RETURN rule.id AS id
"""


def _action_payload(action: LogicCriterion) -> dict[str, Any]:
    """Compose the actionJson payload persisted on an edited rule.

    Mirrors the shape produced by the rule extraction pipeline so that
    downstream consumers (bitmap compiler, inference engine, UI display)
    keep working without a schema change.
    """
    return {
        "term": action.term or action.preferred_term,
        "snomed_concept_id": action.snomed_concept_id,
        "preferred_term": action.preferred_term,
        "semantic_tag": action.semantic_tag or "procedure",
        "verification_status": "human_edited",
    }


# -- Public entry point --------------------------------------------------------


class EditNotApplicable(ValueError):
    """Raised when the predecessor rule cannot be edited (wrong status, missing)."""


def apply_rule_edit(
    client: Any,
    *,
    predecessor_rule_id: str,
    updates: RuleUpdates,
    reviewer: str,
    reason: str,
) -> dict:
    """Persist a reviewer-edited rule version.

    Steps:
      1. Validate the new logic tree (shape, depth, node count).
      2. Look up the predecessor rule + its parent recommendation.
      3. Verify every concept_id referenced by the tree exists in Neo4j.
      4. Write the new rule, link it to the recommendation, supersede the old
         rule, and write an immutable audit event in a single Cypher pass.

    Returns ``{rule_id, predecessor_id}`` on success.
    """
    concept_ids = validate_logic_tree(updates.logic_tree)
    # Action SNOMED concept (when supplied) is verified alongside the
    # logic-tree concepts so a single round-trip catches all unknowns.
    if updates.action is not None:
        concept_ids = set(concept_ids) | {updates.action.snomed_concept_id}

    pred_rows = client.run(_FETCH_PREDECESSOR, rule_id=predecessor_rule_id)
    if not pred_rows:
        raise EditNotApplicable(f"Predecessor rule {predecessor_rule_id} not found.")
    pred = pred_rows[0]
    if pred.get("status") not in ("pending_review", "active"):
        raise EditNotApplicable(
            f"Cannot edit a rule whose status is {pred.get('status')!r}; "
            "only pending_review or active rules can be edited."
        )

    if concept_ids:
        rows = client.run(_VERIFY_CONCEPTS, concept_ids=sorted(concept_ids))
        missing = [r["concept_id"] for r in rows if not r.get("exists")]
        if missing:
            raise LogicTreeValidationError(
                f"Unknown SNOMED concept ids: {', '.join(missing)}. "
                "Pick a concept from the search results."
            )

    new_rule_id = f"{predecessor_rule_id}:edit:{str(uuid.uuid4())[:8]}"
    new_name = (updates.name or pred.get("name") or "").strip()[:200]
    new_strength = (updates.strength or pred.get("strength") or "unspecified").strip()
    logic_json = json.dumps(updates.logic_tree.model_dump(exclude_none=True))
    # Pass None when the reviewer did not change the action, so the
    # _INSERT_EDITED_RULE coalesce falls through to pred.actionJson and
    # we never silently null out a previously-coded recommendation.
    action_json: str | None = (
        json.dumps(_action_payload(updates.action)) if updates.action is not None else None
    )

    rows = client.run(
        _INSERT_EDITED_RULE,
        rule_id=new_rule_id,
        predecessor_id=predecessor_rule_id,
        recommendation_id=pred["recommendation_id"],
        verbatim=pred.get("verbatim", ""),
        name=new_name or "Edited rule",
        strength=new_strength,
        logic_json=logic_json,
        action_json=action_json,
        reviewer=reviewer,
        reason=reason,
        event_id=str(uuid.uuid4()),
    )
    if not rows:
        raise EditNotApplicable(
            "Edited rule could not be written. The recommendation may have moved."
        )

    return {"rule_id": new_rule_id, "predecessor_id": predecessor_rule_id}


__all__ = [
    "MAX_NODE_COUNT",
    "MAX_TREE_DEPTH",
    "EditNotApplicable",
    "LogicCriterion",
    "LogicNode",
    "LogicTreeValidationError",
    "RuleUpdates",
    "apply_rule_edit",
    "validate_logic_tree",
]


# Resolve forward refs on the recursive Pydantic model.
LogicNode.model_rebuild()
