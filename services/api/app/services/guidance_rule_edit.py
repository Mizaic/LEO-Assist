"""Manual edit pathway for AI-generated AppropriatenessRules.

Atlas trace:
  DO: DO-D6CE2AA5
  DI: DI-A3107424
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-D6CE2AA5")

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

from pydantic import BaseModel, Field, field_validator, model_validator

from libs.guidance_schema.observation_leaf import (
    ObservationLeaf,
    ObservationLeafValidationError,
)

# Default IS_A descendant depth applied when a seed asks for descendant
# expansion but does not override distance_child. Matches the historical
# default used by the bitmap compiler before UN-LEO-AI-093.
DEFAULT_DESCENDANT_DEPTH = 3

# -- Tree limits ---------------------------------------------------------------
# Caps that defend against pathological trees pushed via the edit API. Real
# NICE rules max out at ~30 nodes and depth 4 (per inspection of the existing
# generated set), so these limits leave plenty of headroom while bounding
# server-side work and downstream bitmap compile time.
MAX_TREE_DEPTH = 6
MAX_NODE_COUNT = 80

_GROUP_KINDS = {"AND", "OR", "NOT", "AT_LEAST"}
# OBSERVATION is the Phase 5 numeric-threshold leaf.
# MEDICATION, ALLERGY, and TREATMENT_HISTORY are Sprint 1 management-pathway
# leaves (DI-2199E670 / DO-0EC3A9CB). They do not use the bitmap path.
# RULE_FIRED is the chained-evaluation leaf (DI-8899D4F3 / DO-274E5A61).
_LEAF_KINDS = {
    "CONCEPT",
    "DEMOGRAPHIC",
    "OBSERVATION",
    "MEDICATION",
    "ALLERGY",
    "TREATMENT_HISTORY",
    "RULE_FIRED",
}
_ALL_KINDS = _GROUP_KINDS | _LEAF_KINDS
_VALID_RULE_FIRED_OUTCOMES = {"fired", "not_fired"}


# -- Pydantic models -----------------------------------------------------------


class LogicSeed(BaseModel):
    """One SNOMED code in a CONCEPT criterion's synonym set (UN-LEO-AI-093).

    Each seed is independently expandable into its IS_A descendants via the
    bitmap compiler's ``_closure_ids``. ``include_descendants=False`` forces
    exact-match for that seed even when the rule-level distance_child default
    is non-zero.
    """

    model_config = {"extra": "forbid"}

    snomed_concept_id: str = Field(min_length=1)
    preferred_term: str = Field(min_length=1)
    semantic_tag: str = ""
    include_descendants: bool = True
    distance_child: int | None = None

    @model_validator(mode="after")
    def _force_exact_for_local(self) -> "LogicSeed":
        from libs.terminology.local_concepts import is_local_concept_id

        if is_local_concept_id(self.snomed_concept_id):
            self.include_descendants = False
            self.distance_child = 0
        return self


class LogicCriterion(BaseModel):
    """Resolved SNOMED criterion attached to a CONCEPT node.

    Backwards compatible: legacy callers may supply ``snomed_concept_id`` +
    ``preferred_term`` only and ``seeds`` defaults to an empty list. New
    callers may supply ``seeds`` (with optional ``primary_concept_id`` and
    ``excluded_concept_ids``); the legacy fields are auto-derived from the
    primary seed so downstream readers always see a non-empty
    ``snomed_concept_id``.
    """

    model_config = {"extra": "forbid"}

    snomed_concept_id: str = ""
    preferred_term: str = ""
    semantic_tag: str = ""
    term: str = ""
    seeds: list[LogicSeed] = Field(default_factory=list)
    excluded_concept_ids: list[str] = Field(default_factory=list)
    primary_concept_id: str = ""

    @model_validator(mode="after")
    def _normalise(self) -> "LogicCriterion":
        # Legacy single-seed shape: nothing to normalise.
        if not self.seeds:
            if not self.snomed_concept_id:
                raise ValueError(
                    "CONCEPT criterion must have at least one seed or a "
                    "snomed_concept_id (legacy shape)."
                )
            return self

        # Multi-seed shape: derive primary + legacy fields when missing.
        if not self.primary_concept_id:
            self.primary_concept_id = self.seeds[0].snomed_concept_id
        primary = next(
            (s for s in self.seeds if s.snomed_concept_id == self.primary_concept_id),
            None,
        )
        if primary is None:
            raise ValueError(
                f"primary_concept_id {self.primary_concept_id!r} does not match any seed."
            )
        if not self.snomed_concept_id:
            self.snomed_concept_id = primary.snomed_concept_id
        if not self.preferred_term:
            self.preferred_term = primary.preferred_term
        if not self.semantic_tag:
            self.semantic_tag = primary.semantic_tag

        seed_ids = {s.snomed_concept_id for s in self.seeds}
        excluded = list(self.excluded_concept_ids or [])
        if len(excluded) != len(set(excluded)):
            raise ValueError("excluded_concept_ids contains duplicates.")
        for x in excluded:
            if not x:
                raise ValueError("excluded_concept_ids contains an empty id.")
            if x in seed_ids:
                raise ValueError(
                    f"Concept id {x!r} is in both seeds and excluded_concept_ids."
                )
        return self


class RuleAction(BaseModel):
    """One recommended clinical action attached to a rule.

    A rule may recommend more than one procedure (e.g. "offer an X-ray
    and refer for a blood test"), each carrying its own strength. See
    DI-42246DA7 acceptance criteria (multi-action support).

    ``action_kind='narrative'`` means free-text guidance (action_text),
    not a SNOMED procedure for compliance checks.
    """

    model_config = {"extra": "forbid"}

    criterion: LogicCriterion
    strength: str = Field(default="unspecified", max_length=64)
    action_kind: str = Field(default="snomed_procedure", max_length=32)
    action_text: str | None = Field(default=None, max_length=4000)


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
    value: float | str | list[float] | None = None
    unit: str | None = None
    # Carries the Phase 5 OBSERVATION leaf payload (numeric threshold,
    # recency window, optional temporal / reference-range / trend /
    # aggregation mode). Only populated when ``kind == "OBSERVATION"``.
    # Kept as a dedicated nested model rather than re-using
    # ``field/operator/value/unit`` (which DEMOGRAPHIC owns) so the two
    # leaf shapes are unambiguous on the wire and cannot accidentally
    # cross-contaminate each other in a malformed payload.
    observation: ObservationLeaf | None = None
    # Sprint 1 management-pathway leaf payloads (DI-2199E670).
    # Each is only populated when ``kind`` matches the leaf kind.
    # drug_class, substance_concept_id, treatment_class, and outcome are
    # validated in the model_validator below.
    drug_class: str | None = None
    substance_concept_id: str | None = None
    allergy_class: str | None = None
    treatment_class: str | None = None
    outcome: str | None = None
    min_duration_days: int | None = None
    concept_id: str | None = None
    # Optional plain-English name for a group node. Surfaces as the
    # pathway card title in the editor and read-only review view so a
    # multi-branch rule can label each branch (e.g. "Possible cancer"
    # vs "Symptom watch") instead of relying on positional letters.
    # Phase 2 of the edit-rule wizard redesign.
    #
    # Capped at 80 chars so a label always fits a card header on a
    # phone-sized viewport. Whitespace-only values normalise to None so
    # downstream consumers see a single "no name set" shape.
    name: str | None = Field(default=None, max_length=80)
    # RULE_FIRED chained-evaluation fields (DI-8899D4F3 / DO-274E5A61).
    # referenced_rule_id: the rule that must have fired (or not fired) for
    # this leaf to be True. display_name carries the human-readable label
    # stored at authoring time so the editor shows a name even when the
    # referenced rule has since been renamed.
    referenced_rule_id: str | None = None
    display_name: str | None = None

    @field_validator("kind")
    @classmethod
    def _check_kind(cls, v: str) -> str:
        upper = v.upper()
        if upper not in _ALL_KINDS:
            raise ValueError(f"Unknown node kind {v!r}; expected one of {sorted(_ALL_KINDS)}")
        return upper

    @field_validator("name")
    @classmethod
    def _check_name(cls, v: str | None) -> str | None:
        if v is None:
            return None
        trimmed = v.strip()
        return trimmed if trimmed else None

    @model_validator(mode="after")
    def _validate_leaf_payload(self) -> "LogicNode":
        kind = self.kind
        if kind == "MEDICATION":
            if not (self.drug_class or "").strip():
                raise ValueError(
                    "MEDICATION leaf requires a non-empty drug_class."
                )
        elif kind == "ALLERGY":
            if not (self.substance_concept_id or "").strip():
                raise ValueError(
                    "ALLERGY leaf requires a non-empty substance_concept_id."
                )
        elif kind == "TREATMENT_HISTORY":
            if not (self.treatment_class or "").strip():
                raise ValueError(
                    "TREATMENT_HISTORY leaf requires a non-empty treatment_class."
                )
        return self


class RuleUpdates(BaseModel):
    """Fields a reviewer may change on a pending rule.

    ``actions`` is the list of SNOMED-coded recommended procedures that
    fire when the rule matches, each with its own strength (e.g. "Offer
    a chest X-ray" + "Refer for a blood test"). ``action`` and the
    top-level ``strength`` are deprecated singular aliases kept for
    backward compatibility with older frontend builds during a rolling
    deploy -- when only they are supplied, ``actions`` is synthesised
    server-side as a single-item list. When both are omitted, the
    predecessor rule's existing actionJson is preserved unchanged --
    there is deliberately no path that silently nulls it out (DI-170).
    """

    model_config = {"extra": "forbid"}

    name: str | None = Field(default=None, max_length=200)
    strength: str | None = Field(default=None, max_length=64)
    logic_tree: LogicNode
    action: LogicCriterion | None = None
    actions: list[RuleAction] | None = None

    @model_validator(mode="after")
    def _synthesise_actions_from_legacy_fields(self) -> "RuleUpdates":
        if self.actions is None and self.action is not None:
            self.actions = [
                RuleAction(criterion=self.action, strength=self.strength or "unspecified")
            ]
        return self


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
        crit = node.criterion  # type: ignore[union-attr]
        if crit.seeds:
            for seed in crit.seeds:
                concept_ids.add(seed.snomed_concept_id)
            for x in crit.excluded_concept_ids:
                concept_ids.add(x)
        else:
            concept_ids.add(crit.snomed_concept_id)
        return
    if kind == "DEMOGRAPHIC":
        _validate_demographic_node(node)
        return
    if kind == "OBSERVATION":
        _validate_observation_node(node, concept_ids)
        return
    if kind == "RULE_FIRED":
        _validate_rule_fired_node(node)
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
    crit = node.criterion
    if not crit.seeds and not crit.snomed_concept_id:
        raise LogicTreeValidationError(
            "CONCEPT criterion needs at least one SNOMED code (seed or snomed_concept_id)."
        )


_VALID_DEMOGRAPHIC_FIELDS = {"age", "sex"}
_VALID_OPERATORS = {">=", "<=", ">", "<", "=", "between"}


def _validate_observation_node(node: LogicNode, concept_ids: set[str]) -> None:
    """Validate an OBSERVATION leaf and register its observable_id.

    The Pydantic model already enforces the shape (operator/value
    pairing, mutual exclusion of mode sub-models, recency envelope).
    This step adds two further guarantees:

      1. The leaf has actually populated ``observation`` -- callers
         that send ``kind="OBSERVATION"`` without the nested payload
         are rejected up-front rather than failing later in the
         compiler.
      2. The observable_id is registered in the same concept_ids set
         used by CONCEPT leaves so the Cypher verifier
         (``_VERIFY_CONCEPTS``) catches typos / unknown observables
         in the same round-trip.
    """
    if node.observation is None:
        raise LogicTreeValidationError(
            "OBSERVATION node is missing the 'observation' payload."
        )
    obs = node.observation
    if not obs.observable_id.strip():
        raise LogicTreeValidationError(
            "OBSERVATION node requires a non-empty observable_id."
        )
    concept_ids.add(obs.observable_id)


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
    if node.operator == "between":
        if not (isinstance(node.value, list) and len(node.value) == 2):
            raise LogicTreeValidationError(
                "DEMOGRAPHIC 'between' node requires value as a two-element list [low, high]."
            )
    elif node.value is None or (isinstance(node.value, str) and not node.value.strip()):
        raise LogicTreeValidationError("DEMOGRAPHIC node is missing a value.")


def _validate_rule_fired_node(node: LogicNode) -> None:
    if not (node.referenced_rule_id or "").strip():
        raise LogicTreeValidationError(
            "RULE_FIRED node requires a non-empty referenced_rule_id."
        )
    outcome = (node.outcome or "").strip()
    if outcome not in _VALID_RULE_FIRED_OUTCOMES:
        raise LogicTreeValidationError(
            f"RULE_FIRED node outcome must be 'fired' or 'not_fired'; got {outcome!r}."
        )


# -- Cypher --------------------------------------------------------------------

# Verify that every SNOMED concept referenced by the edited logic tree
# exists in the knowledge graph.
#
# Historically the knowledge graph held two parallel SNOMED concept node
# types -- canonical `(:Concept {id})` written by the SNOMED loader and a
# legacy `(:SnomedConcept {conceptId})` parallel namespace written by the
# v1 guidance rule generator. DI-LEO-AI-528 unified writes onto the
# canonical label and shipped a one-shot migration
# (`scripts/migrations/2026_link_or_delete_orphan_snomed_concepts.py`)
# that rewires legacy guidance edges onto canonical nodes.
#
# This verifier still accepts EITHER label so that:
#   - new-style v2 rules (concepts come from the FE picker -> :Concept)
#     can be edited even before the migration runs.
#   - legacy fixtures and any environment where the migration has not
#     yet completed keep working without breaking edits.
#
# Once the migration has run in every environment AND we have at least
# one release of breathing room to roll back, the legacy match below
# can be deleted. Until then it costs one OPTIONAL MATCH per id with a
# label index, and prevents a class of "Unknown SNOMED concept ids"
# errors that we have already burned reviewer time chasing.
_VERIFY_CONCEPTS = """
UNWIND $concept_ids AS cid
OPTIONAL MATCH (canonical:Concept {id: cid})
OPTIONAL MATCH (legacy:SnomedConcept {conceptId: cid})
RETURN cid AS concept_id,
       (canonical IS NOT NULL OR legacy IS NOT NULL) AS exists
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

# When the AI generator is re-run, multiple pending_review rules can hang
# off the same Recommendation via separate [:HAS_RULE] edges. Approving or
# editing one version should retire the stale siblings so reviewers are not
# left choosing between duplicate drafts for the same NICE recommendation.
_REJECT_SIBLING_PENDING_RULES = """
MATCH (chosen:AppropriatenessRule {id: $rule_id})<-[:HAS_RULE]-(rec:Recommendation)
MATCH (rec)-[:HAS_RULE]->(sibling:AppropriatenessRule)
WHERE sibling.id <> $rule_id
  AND sibling.status = 'pending_review'
SET sibling.status = 'rejected',
    sibling.reviewedAt = datetime(),
    sibling.reviewedBy = $reviewer
RETURN collect(sibling.id) AS rejected_ids
"""


def reject_sibling_pending_rules(
    client: Any,
    *,
    rule_id: str,
    reviewer: str,
) -> list[str]:
    """Reject other pending drafts linked to the same recommendation."""
    rows = client.run(
        _REJECT_SIBLING_PENDING_RULES,
        rule_id=rule_id,
        reviewer=reviewer,
    )
    if not rows:
        return []
    rejected = rows[0].get("rejected_ids") or []
    return [str(rule_id) for rule_id in rejected]


def _actions_payload(actions: list["RuleAction"]) -> list[dict[str, Any]]:
    """Compose the actionJson array payload persisted on an edited rule.

    Mirrors the shape produced by the rule extraction pipeline (plus a
    per-action ``strength``) so that downstream consumers (bitmap
    compiler, inference engine, UI display) can read either the legacy
    single-object shape or this new array shape without a migration.
    """
    return [
        {
            "term": ra.criterion.term or ra.criterion.preferred_term,
            "snomed_concept_id": ra.criterion.snomed_concept_id,
            "preferred_term": ra.criterion.preferred_term,
            "semantic_tag": ra.criterion.semantic_tag or "procedure",
            "strength": ra.strength or "unspecified",
            "action_kind": ra.action_kind or "snomed_procedure",
            "action_text": ra.action_text,
            "verification_status": "human_edited",
        }
        for ra in actions
    ]


def _action_concept_ids(actions: list["RuleAction"]) -> set[str]:
    """Collect every SNOMED concept id referenced across a list of actions.

    Mirrors the seed/exclusion handling ``_walk`` applies to CONCEPT
    logic-tree nodes so a multi-seed action criterion is fully verified.
    """
    ids: set[str] = set()
    for ra in actions:
        crit = ra.criterion
        if crit.seeds:
            for seed in crit.seeds:
                ids.add(seed.snomed_concept_id)
            for excluded in crit.excluded_concept_ids:
                ids.add(excluded)
        else:
            ids.add(crit.snomed_concept_id)
    return ids


def _check_no_duplicate_action_concepts(actions: list["RuleAction"]) -> None:
    """Reject a rule whose actions recommend the same SNOMED procedure twice.

    Two actions sharing a primary concept id is always a mistake (either
    a duplicate row from the UI or an AI-generation glitch) and would
    otherwise silently double up a recommendation in the SBAR narrative.
    """
    seen: dict[str, int] = {}
    for index, ra in enumerate(actions):
        concept_id = ra.criterion.snomed_concept_id
        if concept_id in seen:
            raise LogicTreeValidationError(
                f"Duplicate recommended action: SNOMED concept {concept_id!r} "
                f"appears in both action {seen[concept_id]} and {index}. "
                "Each recommended action must be a distinct procedure."
            )
        seen[concept_id] = index


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
    # Action SNOMED concepts (when supplied) are verified alongside the
    # logic-tree concepts so a single round-trip catches all unknowns.
    if updates.actions:
        _check_no_duplicate_action_concepts(updates.actions)
        concept_ids = set(concept_ids) | _action_concept_ids(updates.actions)

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
    if updates.actions:
        new_strength = (updates.actions[0].strength or "unspecified").strip()
    else:
        new_strength = (updates.strength or pred.get("strength") or "unspecified").strip()
    logic_json = json.dumps(updates.logic_tree.model_dump(exclude_none=True))
    # Pass None when the reviewer did not change any action, so the
    # _INSERT_EDITED_RULE coalesce falls through to pred.actionJson and
    # we never silently null out a previously-coded recommendation.
    action_json: str | None = (
        json.dumps(_actions_payload(updates.actions)) if updates.actions else None
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

    reject_sibling_pending_rules(
        client,
        rule_id=new_rule_id,
        reviewer=reviewer,
    )

    return {"rule_id": new_rule_id, "predecessor_id": predecessor_rule_id}


__all__ = [
    "DEFAULT_DESCENDANT_DEPTH",
    "MAX_NODE_COUNT",
    "MAX_TREE_DEPTH",
    "EditNotApplicable",
    "LogicCriterion",
    "LogicNode",
    "LogicSeed",
    "LogicTreeValidationError",
    "ObservationLeaf",
    "ObservationLeafValidationError",
    "RuleAction",
    "RuleUpdates",
    "apply_rule_edit",
    "reject_sibling_pending_rules",
    "validate_logic_tree",
]


# Resolve forward refs on the recursive Pydantic model.
LogicNode.model_rebuild()
