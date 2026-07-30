/**
 * Pure helpers for editing a logic tree by node id.
 *
 * Every helper returns a NEW tree -- the input is never mutated. Stable
 * client-side ``node_id`` values let us locate a target without depending on
 * object identity, so the editor can safely re-derive React keys after a
 * structural change.
 *
 * The helpers also strip the synthetic ``node_id`` when serialising the tree
 * for the API: server-side validation accepts ``node_id`` but does not
 * require it, so we drop it to keep the persisted JSON tidy.
 *
 * Atlas trace:
 *   DI: DI-42246DA7
 *   DO: DO-F8C56339
 *   Look up via: get_design_control(dc_type="design-input", dc_id="DI-42246DA7")
 */
import { findPathwaySplit } from "./pathwayDetection";
import type {
  EditableLogicNode,
  EditableObservationPayload,
  LogicCriterion,
  LogicNodeKind,
  LogicSeed,
  NodeUpdate,
  RuleAction,
} from "./types";

/**
 * Recursive Partial: every node in a seed tree may omit ``node_id`` (and
 * indeed any other field). ``assignNodeIds`` accepts a seed of this shape
 * and returns a fully-populated ``EditableLogicNode``. This keeps the
 * editor and tests free to construct trees from literal object expressions
 * without having to thread synthetic node_ids through every level.
 */
export type LogicNodeSeed = Omit<Partial<EditableLogicNode>, "children"> & {
  children?: LogicNodeSeed[];
};

let _idCounter = 0;
/**
 * Exported (not just used internally) so the highlight-to-build
 * wizard orchestrator can mint node ids when constructing a brand
 * new pathway skeleton in one atomic `replace_root` -- see
 * `HighlightWizard/wizardMapping.ts` -- without a second, drifting
 * copy of this counter.
 */
export function freshNodeId(): string {
  _idCounter += 1;
  return `n_${Date.now().toString(36)}_${_idCounter}`;
}

let _pathwayKeyCounter = 0;
/**
 * Mint a fresh, globally-unique pathway identity. Namespaced
 * separately from ``freshNodeId`` -- the two counters are unrelated,
 * and a pathway_key must never be confused with (or accidentally
 * collide against) a node_id since they have different lifetimes
 * (node_id is ephemeral/client-only; pathway_key is persisted).
 */
export function mintPathwayKey(): string {
  _pathwayKeyCounter += 1;
  return `pw_${Date.now().toString(36)}_${_pathwayKeyCounter}`;
}

/**
 * Recursively assign a node_id to any node missing one and normalise the
 * ``kind`` value into the canonical uppercase form. Returns a new tree.
 *
 * The persisted ``logicJson`` produced by the LLM rule extractor uses lowercase
 * leaf-kinds (``"concept"``, ``"demographic"``) per
 * ``libs/prompts/guidance_rule_extraction_output_schema.py``. The editor and
 * the server-side validator both work in uppercase, so we coerce on load --
 * otherwise leaf nodes fall through to the group renderer and trigger a
 * spurious "'concept' group cannot be empty" validation error.
 */
export function assignNodeIds(node: LogicNodeSeed): EditableLogicNode {
  const children = (node.children ?? []).map((c) => assignNodeIds(c));
  const base = {
    ...node,
    node_id: node.node_id ?? freshNodeId(),
    kind: normaliseKind(node.kind),
    ...(node.operator !== undefined ? { operator: normaliseOperator(node.operator) } : {}),
    ...(children.length ? { children } : {}),
  } as EditableLogicNode;

  // Split persisted [low, high] pair back into value + value2 for the editor.
  if (base.operator === "between" && Array.isArray(base.value)) {
    const pair = base.value as unknown as Array<number | string>;
    if (pair.length === 2) {
      base.value = pair[0];
      base.value2 = pair[1];
    }
  }

  // AI drafts store the guideline phrase as ``raw_term`` (demographics)
  // or ``criterion.source_text`` (concepts). The wizard anchors via
  // ``source_row_text`` -- promote on load so glossary labels like
  // "children and young people" highlight when those words are present.
  promoteSourceRowText(base, node);

  return base;
}

function promoteSourceRowText(
  base: EditableLogicNode,
  seed: LogicNodeSeed,
): void {
  if (base.source_row_text?.trim()) return;
  const raw = (seed as { raw_term?: unknown }).raw_term;
  if (typeof raw === "string" && raw.trim()) {
    base.source_row_text = raw.trim();
    return;
  }
  if (base.kind !== "CONCEPT") return;
  const sourceText = (
    seed as { criterion?: { source_text?: unknown } }
  ).criterion?.source_text;
  if (typeof sourceText === "string" && sourceText.trim()) {
    base.source_row_text = sourceText.trim();
  }
}

const KIND_MAP: Record<string, LogicNodeKind> = {
  AND: "AND",
  OR: "OR",
  NOT: "NOT",
  AT_LEAST: "AT_LEAST",
  ATLEAST: "AT_LEAST",
  CONCEPT: "CONCEPT",
  DEMOGRAPHIC: "DEMOGRAPHIC",
  OBSERVATION: "OBSERVATION",
  MEDICATION: "MEDICATION",
  ALLERGY: "ALLERGY",
  TREATMENT_HISTORY: "TREATMENT_HISTORY",
  RULE_FIRED: "RULE_FIRED",
};

function normaliseKind(raw: string | undefined): LogicNodeKind {
  if (!raw) return "AND";
  const upper = raw.toUpperCase();
  return KIND_MAP[upper] ?? "AND";
}

// Older extraction runs (pre-dating the "=" convention now baked into
// libs/prompts/guidance_rule_extraction_v1.py) sometimes wrote a
// programmer's equality operator for a DEMOGRAPHIC sex check instead
// of the backend's "=". Left uncorrected, those legacy trees load into
// the wizard fine but fail server-side validation with "DEMOGRAPHIC
// node has unsupported operator '=='" the moment a reviewer tries to
// save -- confirmed live against NG12 1.5.5's pending_review logicJson.
const OPERATOR_ALIASES: Record<string, string> = {
  "==": "=",
};

function normaliseOperator(raw: string | undefined): string | undefined {
  if (!raw) return raw;
  return OPERATOR_ALIASES[raw] ?? raw;
}

// ---------------------------------------------------------------------------
// Criterion / seed allowlists (mirrors LogicCriterion + LogicSeed in
// services/api/app/services/guidance_rule_edit.py).
//
// Both Pydantic models are declared with model_config = {"extra": "forbid"},
// so any key the FE forwards that the BE does not know about triggers a 422
// and the entire save fails. The LLM rule-extraction pipeline writes a much
// richer criterion into logicJson (node_id, source_text, original_phrase,
// expansion_source, expanded_from, candidates, verification_status,
// verification_reason, confidence, resolver_turns, needs_human_review,
// search_history, etc.) for traceability -- those fields ride back to the
// editor when the rule is loaded but MUST be stripped before POST.
//
// Keep these arrays in lockstep with the BE schema. Adding a new field on
// the BE means whitelisting it here too; renaming a field means updating
// both ends in the same change.
// ---------------------------------------------------------------------------

const ALLOWED_CRITERION_KEYS = new Set<keyof LogicCriterion>([
  "snomed_concept_id",
  "preferred_term",
  "semantic_tag",
  "term",
  "seeds",
  "excluded_concept_ids",
  "primary_concept_id",
  // Confidence signal (highlight-to-build wizard, confidence-surfacing).
  // Previously stripped here, which meant AI confidence survived exactly
  // one review pass then was gone forever. Now round-trips through save
  // so the confidence lifecycle in confidenceGate.ts can work at all.
  "confidence",
  "needs_human_review",
  "human_reviewed_at",
  "human_reviewed_by",
]);

function sanitiseSeed(seed: LogicSeed): LogicSeed {
  const out: LogicSeed = {
    snomed_concept_id: seed.snomed_concept_id,
    preferred_term: seed.preferred_term,
  };
  if (seed.semantic_tag !== undefined) {
    out.semantic_tag = seed.semantic_tag;
  }
  if (seed.include_descendants !== undefined) {
    out.include_descendants = seed.include_descendants;
  }
  if (seed.distance_child !== undefined) {
    out.distance_child = seed.distance_child;
  }
  return out;
}

/**
 * Whitelist a criterion to the keys the BE LogicCriterion model accepts.
 * Drops LLM provenance fields (source_text, candidates, confidence, ...)
 * and stale UI-only keys so the BE never sees an unknown field.
 */
export function sanitiseCriterion(
  criterion: LogicCriterion,
): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(criterion)) {
    if (!ALLOWED_CRITERION_KEYS.has(k as keyof LogicCriterion)) continue;
    if (k === "seeds" && Array.isArray(v)) {
      out.seeds = (v as LogicSeed[]).map(sanitiseSeed);
    } else {
      out[k] = v;
    }
  }
  return out;
}

/**
 * Whitelist a single recommended action before sending it to the BE.
 * Mirrors ``sanitiseCriterion`` for the nested criterion so LLM
 * provenance fields never reach the ``RuleAction`` Pydantic model
 * (``extra: "forbid"``).
 */
export function sanitiseAction(action: RuleAction): Record<string, unknown> {
  const out: Record<string, unknown> = {
    criterion: sanitiseCriterion(action.criterion),
    strength: action.strength,
  };
  const groupId = action.group_id?.trim();
  if (groupId) {
    out.group_id = groupId;
    if (
      action.group_mode === "all" ||
      action.group_mode === "any" ||
      action.group_mode === "preferred_fallback"
    ) {
      out.group_mode = action.group_mode;
    }
    if (
      typeof action.group_rank === "number" &&
      Number.isFinite(action.group_rank)
    ) {
      out.group_rank = Math.floor(action.group_rank);
    }
  }
  return out;
}

/** Sanitise every action in an array (see ``sanitiseAction``). */
export function sanitiseActionsForSave(
  actions: RuleAction[],
): Array<Record<string, unknown>> {
  return actions.map(sanitiseAction);
}

/**
 * Strip node_id (and any other UI-only / LLM-only metadata) before sending
 * the tree to the BE. The criterion on each CONCEPT leaf is also passed
 * through ``sanitiseCriterion`` so the BE's ``extra: "forbid"`` validator
 * never sees an unknown key.
 */
export function stripNodeIds(node: EditableLogicNode): Record<string, unknown> {
  const out: Record<string, unknown> = { kind: node.kind };
  // Unlike node_id (client-only, regenerated every load), pathway_key
  // is a persisted stable identity -- see the "Stable identity" plan
  // section. Preserved verbatim, never regenerated here.
  if (node.pathway_key) out.pathway_key = node.pathway_key;
  if (node.criterion) out.criterion = sanitiseCriterion(node.criterion);
  if (node.field !== undefined) out.field = node.field;
  if (node.operator !== undefined) out.operator = node.operator;
  if (node.value !== undefined && node.value !== null) {
    if (node.operator === "between" && node.value2 != null) {
      out.value = [node.value, node.value2];
    } else {
      out.value = node.value;
    }
  }
  if (node.unit !== undefined && node.unit !== null) out.unit = node.unit;
  if (node.min !== undefined) out.min = node.min;
  // Phase 2: keep the pathway name when it's a non-empty string. Empty
  // strings drop so the BE's ``model_config = {"extra": "forbid"}``
  // Pydantic model never sees an empty ``name`` field.
  if (typeof node.name === "string" && node.name.trim()) {
    out.name = node.name.trim();
  }
  // See `EditableLogicNode.source_row_text`'s doc comment -- persisted
  // (like `name`) so a wizard-added leaf still resolves its own Step 3
  // row the next time this rule is reopened, not just in the session
  // it was added in.
  if (typeof node.source_row_text === "string" && node.source_row_text.trim()) {
    out.source_row_text = node.source_row_text.trim();
  }
  // Phase 6a: round-trip the OBSERVATION payload verbatim.
  if (node.kind === "OBSERVATION" && node.observation) {
    out.observation = stripObservation(node.observation);
  }
  // RULE_FIRED chained-evaluation fields (DI-8899D4F3).
  if (node.kind === "RULE_FIRED") {
    if (node.referenced_rule_id) out.referenced_rule_id = node.referenced_rule_id;
    out.outcome = node.outcome ?? "fired";
    if (node.display_name) out.display_name = node.display_name;
  }
  if (node.children?.length) out.children = node.children.map(stripNodeIds);
  return out;
}

/**
 * Serialise an OBSERVATION payload for the BE.
 *
 * - Drops mode-spec keys that are null or undefined so the Pydantic
 *   model never sees a null where the schema expects "field absent".
 * - Drops an empty ``observable_term`` because the BE derives a
 *   fallback from the SNOMED PT at validation time.
 * - Leaves the active mode spec fully intact so temporal /
 *   reference_range / trend / aggregation rules authored in Advanced
 *   mode or from ingest round-trip unchanged.
 */
function stripObservation(
  obs: EditableObservationPayload,
): Record<string, unknown> {
  const out: Record<string, unknown> = {
    kind: "OBSERVATION",
    observable_id: obs.observable_id,
    operator: obs.operator,
    value: obs.value,
    unit: (obs.unit ?? "").trim(),
  };
  if (obs.observable_term && obs.observable_term.trim()) {
    out.observable_term = obs.observable_term.trim();
  }
  if (typeof obs.within_days === "number") out.within_days = obs.within_days;
  if (obs.temporal) out.temporal = obs.temporal;
  if (obs.reference_range) out.reference_range = obs.reference_range;
  if (obs.trend) out.trend = obs.trend;
  if (obs.aggregation) out.aggregation = obs.aggregation;
  return out;
}

// ---------------------------------------------------------------------------
// Synonym-chip helpers (UN-LEO-AI-093)
// ---------------------------------------------------------------------------

/**
 * Promote a legacy single-seed criterion into the synonym-set shape so the
 * helpers below can operate on it uniformly. Returns a NEW criterion. Safe
 * to call repeatedly (idempotent when ``seeds`` is already populated).
 */
function ensureSeeds(criterion: LogicCriterion): LogicCriterion {
  const seeds = criterion.seeds ?? [];
  if (seeds.length > 0) {
    return {
      ...criterion,
      seeds,
      excluded_concept_ids: criterion.excluded_concept_ids ?? [],
      primary_concept_id:
        criterion.primary_concept_id || seeds[0].snomed_concept_id,
    };
  }
  if (!criterion.snomed_concept_id) return criterion;
  const primary: LogicSeed = {
    snomed_concept_id: criterion.snomed_concept_id,
    preferred_term: criterion.preferred_term,
    semantic_tag: criterion.semantic_tag,
    include_descendants: true,
  };
  return {
    ...criterion,
    seeds: [primary],
    excluded_concept_ids: criterion.excluded_concept_ids ?? [],
    primary_concept_id: criterion.snomed_concept_id,
  };
}

function withCriterion(
  node: EditableLogicNode,
  fn: (c: LogicCriterion) => LogicCriterion,
): EditableLogicNode {
  if (node.kind !== "CONCEPT" || !node.criterion) return node;
  return { ...node, criterion: fn(ensureSeeds(node.criterion)) };
}

function syncLegacyFields(criterion: LogicCriterion): LogicCriterion {
  const seeds = criterion.seeds ?? [];
  if (seeds.length === 0) return criterion;
  const primary =
    seeds.find((s) => s.snomed_concept_id === criterion.primary_concept_id) ??
    seeds[0];
  return {
    ...criterion,
    primary_concept_id: primary.snomed_concept_id,
    snomed_concept_id: primary.snomed_concept_id,
    preferred_term: primary.preferred_term,
    semantic_tag: primary.semantic_tag ?? criterion.semantic_tag ?? "",
  };
}

export function addSeed(
  node: EditableLogicNode,
  seed: LogicSeed,
): EditableLogicNode {
  return withCriterion(node, (c) => {
    const seeds = c.seeds ?? [];
    if (seeds.some((s) => s.snomed_concept_id === seed.snomed_concept_id)) {
      return c;
    }
    return syncLegacyFields({
      ...c,
      seeds: [
        ...seeds,
        { include_descendants: true, ...seed },
      ],
    });
  });
}

export function removeSeed(
  node: EditableLogicNode,
  conceptId: string,
): EditableLogicNode {
  return withCriterion(node, (c) => {
    const seeds = c.seeds ?? [];
    if (seeds.length <= 1) return c;
    const next = seeds.filter((s) => s.snomed_concept_id !== conceptId);
    if (next.length === seeds.length) return c;
    let primary = c.primary_concept_id;
    if (primary === conceptId) primary = next[0].snomed_concept_id;
    return syncLegacyFields({ ...c, seeds: next, primary_concept_id: primary });
  });
}

export function setPrimarySeed(
  node: EditableLogicNode,
  conceptId: string,
): EditableLogicNode {
  return withCriterion(node, (c) => {
    const seeds = c.seeds ?? [];
    if (!seeds.some((s) => s.snomed_concept_id === conceptId)) return c;
    return syncLegacyFields({ ...c, primary_concept_id: conceptId });
  });
}

export function toggleIncludeDescendants(
  node: EditableLogicNode,
  conceptId: string,
): EditableLogicNode {
  return withCriterion(node, (c) => {
    const seeds = (c.seeds ?? []).map((s) =>
      s.snomed_concept_id === conceptId
        ? { ...s, include_descendants: !(s.include_descendants ?? true) }
        : s,
    );
    return { ...c, seeds };
  });
}

export function setSeedDistance(
  node: EditableLogicNode,
  conceptId: string,
  distance: number | null,
): EditableLogicNode {
  return withCriterion(node, (c) => {
    // A depth of 0 would only match the exact code -- identical to
    // switching descendant expansion off -- so 1 is the effective floor
    // whenever a seed has descendants enabled.
    const next =
      distance === null || Number.isNaN(distance)
        ? null
        : Math.max(1, Math.floor(distance));
    const seeds = (c.seeds ?? []).map((s) =>
      s.snomed_concept_id === conceptId ? { ...s, distance_child: next } : s,
    );
    return { ...c, seeds };
  });
}

export function addExcluded(
  node: EditableLogicNode,
  conceptId: string,
): EditableLogicNode {
  return withCriterion(node, (c) => {
    if (!conceptId) return c;
    const seeds = c.seeds ?? [];
    if (seeds.some((s) => s.snomed_concept_id === conceptId)) return c;
    const excluded = c.excluded_concept_ids ?? [];
    if (excluded.includes(conceptId)) return c;
    return { ...c, excluded_concept_ids: [...excluded, conceptId] };
  });
}

export function removeExcluded(
  node: EditableLogicNode,
  conceptId: string,
): EditableLogicNode {
  return withCriterion(node, (c) => {
    const excluded = c.excluded_concept_ids ?? [];
    const next = excluded.filter((id) => id !== conceptId);
    if (next.length === excluded.length) return c;
    return { ...c, excluded_concept_ids: next };
  });
}

function mapNode(
  node: EditableLogicNode,
  fn: (n: EditableLogicNode) => EditableLogicNode | null,
): EditableLogicNode | null {
  const replaced = fn(node);
  if (replaced === null) return null;
  if (!replaced.children?.length) return replaced;
  const newChildren = replaced.children
    .map((c) => mapNode(c, fn))
    .filter((c): c is EditableLogicNode => c !== null);
  return { ...replaced, children: newChildren };
}

/**
 * Drop empty AT_LEAST shells that only existed to hold cluster leaves
 * (lead/trailing). Leaving them after the last child is removed blocked
 * Save with "One of the groups is empty" even though the reviewer had
 * already cleared the list on purpose.
 */
export function pruneEmptyClusterShells(node: EditableLogicNode): EditableLogicNode {
  if (!node.children?.length) return node;
  const children = node.children
    .map(pruneEmptyClusterShells)
    .filter(
      (c) =>
        !(
          c.kind === "AT_LEAST" &&
          c.cluster_role &&
          (c.children ?? []).length === 0
        ),
    );
  if (
    children.length === node.children.length &&
    children.every((c, i) => c === node.children![i])
  ) {
    return node;
  }
  return { ...node, children };
}

/**
 * Walk the tree looking for the first node whose direct ``children``
 * array is the one ``rewrite`` should act on (``rewrite`` returns
 * ``null`` when this array is not the target, letting the walk
 * continue deeper). Unlike ``mapNode`` (one node in, one node or null
 * out -- fine for replace/remove), split and merge need to turn one
 * child into two, or two children into one, which changes the shape
 * of the *array*, not of a single node. Stops at the first match
 * (a node_id is unique, so there is at most one array that contains
 * it) rather than searching every remaining branch once found.
 */
function mapChildrenArray(
  node: EditableLogicNode,
  rewrite: (children: EditableLogicNode[]) => EditableLogicNode[] | null,
): EditableLogicNode {
  if (!node.children?.length) return node;
  const rewritten = rewrite(node.children);
  if (rewritten !== null) {
    return { ...node, children: rewritten };
  }
  return {
    ...node,
    children: node.children.map((c) => mapChildrenArray(c, rewrite)),
  };
}

/** Apply an update operation, returning a new tree (or null if root removed). */
export function applyUpdate(
  root: EditableLogicNode,
  update: NodeUpdate,
): EditableLogicNode | null {
  switch (update.kind) {
    case "replace_concept":
      return mapNode(root, (n) =>
        n.node_id === update.nodeId && n.kind === "CONCEPT"
          ? { ...n, criterion: update.criterion }
          : n,
      );
    case "set_min":
      return mapNode(root, (n) =>
        n.node_id === update.nodeId && n.kind === "AT_LEAST"
          ? { ...n, min: Math.max(1, Math.floor(update.min)) }
          : n,
      );
    case "set_demographic": {
      const { value2, ...base } = update;
      return mapNode(root, (n) => {
        if (n.node_id !== update.nodeId || n.kind !== "DEMOGRAPHIC") return n;
        const updated: typeof n = {
          ...n,
          field: base.field,
          operator: base.operator,
          value: base.value,
          unit: base.unit,
        };
        if (value2 !== undefined) updated.value2 = value2;
        else delete updated.value2;
        return updated;
      });
    }
    case "change_kind":
      return mapNode(root, (n) =>
        n.node_id === update.nodeId ? coerceKind(n, update.newKind) : n,
      );
    case "remove": {
      if (root.node_id === update.nodeId) return null;
      const removed = mapNode(root, (n) => (n.node_id === update.nodeId ? null : n));
      return removed ? pruneEmptyClusterShells(removed) : null;
    }
    case "add_concept":
      return mapNode(root, (n) =>
        n.node_id === update.parentNodeId
          ? appendChildPromotingLeaf(
              root,
              n,
              makeConceptNode(update.criterion, update.sourceRowText),
            )
          : n,
      );
    case "add_group":
      return mapNode(root, (n) => {
        if (n.node_id !== update.parentNodeId) {
          return n;
        }
        // A new direct child of a pathway-split OR is itself a new
        // pathway (this is exactly what PathwayList.tsx's "Add
        // pathway" button targets) -- mint its stable pathway_key
        // now, at first creation, per the "Stable identity" plan
        // section. Any other add_group target (a nested AT_LEAST
        // cluster inside a pathway's own AND, for example) is not a
        // pathway and gets no key.
        const child = makeGroupNode(update.groupKind, update.min);
        if (n.kind === "OR") {
          child.pathway_key = mintPathwayKey();
        }
        if (update.clusterRole) {
          child.cluster_role = update.clusterRole;
        }
        return appendChildPromotingLeaf(root, n, child);
      });
    case "add_demographic": {
      const demo = makeDemographicNode(update.field, update.prefill, update.sourceRowText);
      return mapNode(root, (n) => {
        if (n.node_id !== update.parentNodeId) return n;
        if (isOrGroupSymptomsOnly(n)) {
          return addPrerequisiteToOrSymptoms(n, demo);
        }
        return appendChildPromotingLeaf(root, n, demo);
      });
    }
    case "add_observation": {
      const observation = makeObservationNode(update.seed);
      return mapNode(root, (n) => {
        if (n.node_id !== update.parentNodeId) return n;
        if (isOrGroupSymptomsOnly(n)) {
          return addPrerequisiteToOrSymptoms(n, observation);
        }
        return appendChildPromotingLeaf(root, n, observation);
      });
    }
    case "set_observation":
      return mapNode(root, (n) =>
        n.node_id === update.nodeId && n.kind === "OBSERVATION"
          ? { ...n, observation: { ...update.observation } }
          : n,
      );
    case "set_name": {
      // Only group nodes may carry a plain-English name. Silent no-op
      // on leaves so a stale handler wired to a CONCEPT / DEMOGRAPHIC
      // / OBSERVATION chip cannot smuggle an unsupported field into
      // the persisted tree.
      const trimmed = update.name.trim();
      return mapNode(root, (n) => {
        if (n.node_id !== update.nodeId) return n;
        if (!canHaveChildren(n.kind)) return n;
        if (!trimmed) {
          // Clearing the name: drop the property so ``stripNodeIds``
          // never emits an empty string.
          if (n.name === undefined) return n;
          const { name: _drop, ...rest } = n;
          void _drop;
          return rest as EditableLogicNode;
        }
        return { ...n, name: trimmed };
      });
    }
    case "add_seed":
      return mapNode(root, (n) =>
        n.node_id === update.nodeId ? addSeed(n, update.seed) : n,
      );
    case "remove_seed":
      return mapNode(root, (n) =>
        n.node_id === update.nodeId ? removeSeed(n, update.conceptId) : n,
      );
    case "set_primary_seed":
      return mapNode(root, (n) =>
        n.node_id === update.nodeId ? setPrimarySeed(n, update.conceptId) : n,
      );
    case "toggle_include_descendants":
      return mapNode(root, (n) =>
        n.node_id === update.nodeId
          ? toggleIncludeDescendants(n, update.conceptId)
          : n,
      );
    case "set_seed_distance":
      return mapNode(root, (n) =>
        n.node_id === update.nodeId
          ? setSeedDistance(n, update.conceptId, update.distance)
          : n,
      );
    case "add_excluded":
      return mapNode(root, (n) =>
        n.node_id === update.nodeId ? addExcluded(n, update.conceptId) : n,
      );
    case "remove_excluded":
      return mapNode(root, (n) =>
        n.node_id === update.nodeId ? removeExcluded(n, update.conceptId) : n,
      );
    case "set_name":
      return mapNode(root, (n) =>
        n.node_id === update.nodeId && canHaveChildren(n.kind)
          ? renameGroup(n, update.name)
          : n,
      );
    case "add_rule_fired":
      return mapNode(root, (n) =>
        n.node_id === update.parentNodeId
          ? appendChildPromotingLeaf(root, n, makeRuleFiredNode())
          : n,
      );
    case "set_rule_fired":
      return mapNode(root, (n) =>
        n.node_id === update.nodeId && n.kind === "RULE_FIRED"
          ? {
              ...n,
              referenced_rule_id: update.referenced_rule_id,
              outcome: update.outcome,
              display_name: update.display_name,
            }
          : n,
      );
    case "replace_root":
      return update.node;
    case "split_pathway":
      return mapChildrenArray(root, (children) =>
        splitPathwayChildren(children, update.nodeId, update.splitAt),
      );
    case "merge_pathways":
      return mapChildrenArray(root, (children) =>
        mergePathwayChildren(children, update.firstNodeId, update.secondNodeId),
      );
    default:
      return root;
  }
}

/**
 * Partition one pathway's children at ``splitAt`` into two new sibling
 * pathways, in place of the original in ``children``. Returns ``null``
 * (meaning "not this array, keep looking") when ``nodeId`` is absent or
 * the split would leave one side empty. The children on each side are
 * the SAME objects as before -- sliced, not rebuilt -- so a confirmed
 * leaf's node_id / criterion survive untouched.
 */
function splitPathwayChildren(
  children: EditableLogicNode[],
  nodeId: string,
  splitAt: number,
): EditableLogicNode[] | null {
  const idx = children.findIndex((c) => c.node_id === nodeId);
  if (idx < 0) return null;
  const target = children[idx];
  const targetChildren = target.children ?? [];
  const clamped = Math.max(1, Math.min(Math.floor(splitAt), targetChildren.length - 1));
  if (targetChildren.length < 2 || clamped <= 0 || clamped >= targetChildren.length) {
    return null;
  }
  const first: EditableLogicNode = {
    ...target,
    node_id: freshNodeId(),
    pathway_key: mintPathwayKey(),
    children: targetChildren.slice(0, clamped),
  };
  const second: EditableLogicNode = {
    ...target,
    node_id: freshNodeId(),
    pathway_key: mintPathwayKey(),
    children: targetChildren.slice(clamped),
  };
  const next = [...children];
  next.splice(idx, 1, first, second);
  return next;
}

/**
 * Concatenate two sibling pathways' children into one new pathway,
 * replacing both originals at the position of the earlier one.
 * Returns ``null`` ("not this array") when either id is missing, they
 * are the same node, or they are not actually siblings in this array.
 */
function mergePathwayChildren(
  children: EditableLogicNode[],
  firstNodeId: string,
  secondNodeId: string,
): EditableLogicNode[] | null {
  const firstIdx = children.findIndex((c) => c.node_id === firstNodeId);
  const secondIdx = children.findIndex((c) => c.node_id === secondNodeId);
  if (firstIdx < 0 || secondIdx < 0 || firstIdx === secondIdx) return null;
  const first = children[firstIdx];
  const second = children[secondIdx];
  const merged: EditableLogicNode = {
    ...first,
    node_id: freshNodeId(),
    pathway_key: mintPathwayKey(),
    children: [...(first.children ?? []), ...(second.children ?? [])],
  };
  const insertAt = Math.min(firstIdx, secondIdx);
  const next = children.filter((_, i) => i !== firstIdx && i !== secondIdx);
  next.splice(insertAt, 0, merged);
  return next;
}

/**
 * Update a group node's optional plain-English ``name`` (Phase 2).
 * Empty / whitespace-only input clears the name so the read-only view
 * falls back to the positional "Pathway A/B/C" label.
 */
function renameGroup(
  node: EditableLogicNode,
  name: string,
): EditableLogicNode {
  const trimmed = name.trim();
  if (trimmed.length === 0) {
    const next = { ...node };
    delete next.name;
    return next;
  }
  return { ...node, name: trimmed };
}

export function canHaveChildren(kind: LogicNodeKind): boolean {
  return kind === "AND" || kind === "OR" || kind === "NOT" || kind === "AT_LEAST";
}

/**
 * True when Step 1 should show the dashed "no symptoms yet" empty state.
 * A leaf node at the root (single CONCEPT / DEMOGRAPHIC / OBSERVATION)
 * is editable content even though it has no ``children``.
 */
export function isTreeVisuallyEmpty(node: EditableLogicNode | null): boolean {
  if (!node) return true;
  if ((node.children ?? []).length > 0) return false;
  return !(
    node.kind === "CONCEPT" ||
    node.kind === "DEMOGRAPHIC" ||
    node.kind === "OBSERVATION" ||
    node.kind === "RULE_FIRED"
  );
}

/**
 * When the persisted rule is a single leaf at the root, wrap it in an
 * AND group so reviewers can attach more conditions via + Add.
 */
export function wrapRootInAnd(root: EditableLogicNode): EditableLogicNode {
  if (canHaveChildren(root.kind)) return root;
  return assignNodeIds({ kind: "AND", children: [root] });
}

/**
 * Backfill an immutable ``pathway_key`` onto every direct child of the
 * tree's pathway-split OR (see ``pathwayDetection.findPathwaySplit``)
 * that does not already carry one -- legacy persisted rules predate
 * this field entirely, and a pathway added before this backfill ran
 * once still needs a stable identity to reference. Existing keys are
 * left untouched; children of a non-pathway-split tree are untouched
 * too (nothing to backfill). Call once when a tree is loaded, same
 * spot as ``wrapRootInAnd`` / ``assignNodeIds``.
 */
export function ensurePathwayKeys(root: EditableLogicNode): EditableLogicNode {
  const split = findPathwaySplit(root);
  if (!split) return root;

  const keyedChildren = (split.orNode.children ?? []).map((c) =>
    c.pathway_key ? c : { ...c, pathway_key: mintPathwayKey() },
  );
  const newOrNode = { ...split.orNode, children: keyedChildren };

  if (split.orNode === root) return newOrNode;
  return {
    ...root,
    children: (root.children ?? []).map((c) =>
      c.node_id === split.orNode.node_id ? newOrNode : c,
    ),
  };
}

/**
 * Fix the common AI-generation mistake where demographic / observation
 * conditions end up as OR pathway children instead of AND prerequisites.
 *
 * Given an OR root like: OR[ DEMOGRAPHIC(age), CONCEPT(symptom) ]
 * Returns: AND[ DEMOGRAPHIC(age), OR[ CONCEPT(symptom) ] ]
 *
 * Non-demographic children that are alone in the OR are left as an OR
 * inside the AND so the "pathways" shape is preserved. If all children
 * are non-demographic the tree is returned unchanged.
 */
export function promoteOrPrerequisites(
  root: EditableLogicNode,
): EditableLogicNode {
  if (root.kind !== "OR") return root;
  const children = root.children ?? [];
  const prereqs = children.filter(
    (c) => c.kind === "DEMOGRAPHIC" || c.kind === "OBSERVATION",
  );
  const rest = children.filter(
    (c) => c.kind !== "DEMOGRAPHIC" && c.kind !== "OBSERVATION",
  );
  if (prereqs.length === 0) return root;
  const newChildren: EditableLogicNode[] = [
    ...prereqs,
    ...(rest.length > 0
      ? [assignNodeIds({ kind: "OR", children: rest })]
      : []),
  ];
  return assignNodeIds({ kind: "AND", children: newChildren });
}

/**
 * True when the tree has an OR root whose children include at least one
 * DEMOGRAPHIC or OBSERVATION node -- indicating the AI likely generated
 * a prerequisite as a pathway alternative.
 */
export function hasOrRootWithPrerequisites(
  root: EditableLogicNode | null,
): boolean {
  if (!root || root.kind !== "OR") return false;
  return (root.children ?? []).some(
    (c) => c.kind === "DEMOGRAPHIC" || c.kind === "OBSERVATION",
  );
}

const _PREREQUISITE_LEAF_KINDS = new Set<LogicNodeKind>([
  "CONCEPT",
  "OBSERVATION",
]);

/** True when an OR group holds only symptom/lab leaves (no demographics yet). */
export function isOrGroupSymptomsOnly(node: EditableLogicNode): boolean {
  if (node.kind !== "OR") return false;
  const children = node.children ?? [];
  if (children.length === 0) return false;
  return children.every((c) => _PREREQUISITE_LEAF_KINDS.has(c.kind));
}

/**
 * True when the tree is OR[symptom, symptom, ...] with no patient-detail
 * prerequisites yet -- the shape that needs AND[prerequisite, OR[symptoms]].
 */
export function hasOrRootSymptomsOnly(root: EditableLogicNode | null): boolean {
  if (!root) return false;
  return isOrGroupSymptomsOnly(root);
}

/**
 * Restructure OR[symptoms...] into AND[prerequisite, OR[symptoms...]] so a
 * patient detail (sex, age, ...) applies to every pathway alternative.
 */
export function addPrerequisiteToOrSymptoms(
  orNode: EditableLogicNode,
  prerequisite: EditableLogicNode,
): EditableLogicNode {
  const symptoms = orNode.children ?? [];
  return assignNodeIds({
    kind: "AND",
    children: [
      prerequisite,
      assignNodeIds({ kind: "OR", children: symptoms }),
    ],
  });
}

function appendChild(
  parent: EditableLogicNode,
  child: EditableLogicNode,
): EditableLogicNode {
  return {
    ...parent,
    children: [...(parent.children ?? []), child],
  };
}

function wrapLeafInAnd(child: EditableLogicNode): EditableLogicNode {
  if (canHaveChildren(child.kind)) return child;
  return { node_id: freshNodeId(), kind: "AND", children: [child] };
}

/**
 * True when `nodeId` is a direct child of the tree's pathway-split OR
 * (see `pathwayDetection.findPathwaySplit`) -- i.e. it IS a situation
 * container, whatever shape it happens to be stored in.
 */
function isPathwayContainerId(
  root: EditableLogicNode,
  nodeId: string,
): boolean {
  const split = findPathwaySplit(root);
  return split?.orNode.children?.some((c) => c.node_id === nodeId) ?? false;
}

/**
 * Append `child` under the node matching `n` -- or, when `n` is a
 * bare leaf SITUATION (a single-symptom pathway stored as a direct
 * CONCEPT / DEMOGRAPHIC / OBSERVATION child of the situations OR,
 * e.g. NG12 1.3.1's "abdominal mass" situation), promote it into a
 * 2-child AND first so it can take the new child.
 *
 * Every "add_concept" / "add_group" / "add_demographic" /
 * "add_observation" / "add_rule_fired" case used to guard on
 * `canHaveChildren(n.kind)` and silently no-op otherwise. That guard
 * is still correct for an ordinary leaf elsewhere in the tree, but a
 * pathway container has no such restriction -- `readMaterializedPathways`
 * hands Step 3 whatever the OR's direct children are, leaf or group,
 * with no re-wrap on load (only `coerceKind`'s "make into OR" path
 * wraps leaves). So a single-symptom situation could never gain an
 * age/sex/extra condition: "Add age" looked like it did nothing.
 * Scoping the promotion to `isPathwayContainerId` (rather than
 * promoting ANY targeted leaf) keeps the pre-existing no-op guarantee
 * for every other leaf in the tree.
 */
function appendChildPromotingLeaf(
  root: EditableLogicNode,
  n: EditableLogicNode,
  child: EditableLogicNode,
): EditableLogicNode {
  if (canHaveChildren(n.kind)) return appendChild(n, child);
  if (!isPathwayContainerId(root, n.node_id)) return n;
  // `mapNode` recurses into whatever `fn` returns, so the wrapped
  // leaf MUST get a fresh node_id here -- otherwise it still equals
  // `update.parentNodeId` on the very next pass, `fn` matches again,
  // and the leaf gets re-wrapped forever (stack overflow).
  return {
    node_id: freshNodeId(),
    kind: "AND",
    children: [{ ...n, node_id: freshNodeId() }, child],
  };
}

function coerceKind(
  node: EditableLogicNode,
  newKind: LogicNodeKind,
): EditableLogicNode {
  if (!canHaveChildren(node.kind) || !canHaveChildren(newKind)) return node;
  if (newKind === "AT_LEAST") {
    return { ...node, kind: newKind, min: node.min ?? 1 };
  }
  const stripped = { ...node, kind: newKind };
  delete stripped.min;
  // When becoming OR each child must be a group so PathwayCard renders correctly.
  if (newKind === "OR" && stripped.children) {
    stripped.children = stripped.children.map(wrapLeafInAnd);
  }
  return stripped;
}

function makeConceptNode(
  criterion: LogicCriterion,
  sourceRowText?: string,
): EditableLogicNode {
  return {
    node_id: freshNodeId(),
    kind: "CONCEPT",
    criterion,
    ...(sourceRowText ? { source_row_text: sourceRowText } : {}),
  };
}

function makeGroupNode(kind: LogicNodeKind, min?: number): EditableLogicNode {
  return {
    node_id: freshNodeId(),
    kind,
    children: [],
    ...(kind === "AT_LEAST"
      ? { min: Math.max(1, Math.floor(min ?? 1)) }
      : {}),
  };
}

function makeDemographicNode(
  field: "age" | "sex" = "age",
  prefill?: {
    operator?: string;
    value?: string | number;
    value2?: string | number;
    unit?: string | null;
  },
  sourceRowText?: string,
): EditableLogicNode {
  const base: EditableLogicNode =
    field === "sex"
      ? {
          node_id: freshNodeId(),
          kind: "DEMOGRAPHIC",
          field: "sex",
          operator: "=",
          value: "female",
          unit: null,
        }
      : {
          node_id: freshNodeId(),
          kind: "DEMOGRAPHIC",
          field: "age",
          operator: ">=",
          value: 40,
          unit: "years",
        };
  return {
    ...base,
    ...(prefill?.operator !== undefined ? { operator: prefill.operator } : {}),
    ...(prefill?.value !== undefined ? { value: prefill.value } : {}),
    ...(prefill?.value2 !== undefined ? { value2: prefill.value2 } : {}),
    ...(prefill?.unit !== undefined ? { unit: prefill.unit } : {}),
    ...(sourceRowText ? { source_row_text: sourceRowText } : {}),
  };
}

/**
 * Blank OBSERVATION leaf the reviewer can fill in. ``observable_id``
 * and ``unit`` start empty so ``findValidationError`` surfaces a
 * friendly message until the reviewer picks an observable and unit
 * via the concept-search popover (Phase 6b).
 */
/** Apply a SNOMED pick onto an existing OBSERVATION leaf payload. */
export function observationWithCriterion(
  existing: EditableObservationPayload,
  criterion: LogicCriterion,
): EditableObservationPayload {
  return {
    ...existing,
    observable_id: criterion.snomed_concept_id,
    observable_term:
      criterion.preferred_term ?? criterion.term ?? existing.observable_term,
  };
}

/**
 * Blank RULE_FIRED leaf the author can fill in via the rule picker.
 * outcome defaults to "fired" (the more common case).
 */
export function makeRuleFiredNode(): EditableLogicNode {
  return {
    node_id: freshNodeId(),
    kind: "RULE_FIRED",
    referenced_rule_id: "",
    outcome: "fired",
    display_name: "",
  };
}

function makeObservationNode(
  seed?: Partial<EditableObservationPayload>,
): EditableLogicNode {
  const base: EditableObservationPayload = {
    kind: "OBSERVATION",
    observable_id: "",
    observable_term: "",
    operator: ">=",
    value: 0,
    unit: "",
    within_days: 365,
  };
  // Phase 6b: when the reviewer picks an observable concept in the
  // search panel, we preload the observable_id / observable_term /
  // unit so the reviewer only has to type the threshold. The seed is
  // shallow-merged on top of the blank defaults.
  return {
    node_id: freshNodeId(),
    kind: "OBSERVATION",
    observation: seed ? { ...base, ...seed } : base,
  };
}

/**
 * Checks ONE node's own validity, ignoring its children's own problems
 * (the caller handles recursion). Shared by ``findValidationError`` (first
 * problem only) and ``findAllValidationErrors`` (every problem, with the
 * offending node's id, for "jump to issue" navigation) so the two never
 * drift apart. Messages follow the health-literacy rule (reading age
 * 9-11, plain English, active voice).
 */
function checkNodeOwnError(node: EditableLogicNode): string | null {
  if (node.kind === "CONCEPT") {
    return checkConceptOwnError(node);
  }
  if (node.kind === "DEMOGRAPHIC") {
    if (!node.field) {
      return "Pick what to check on the patient (age or sex).";
    }
    if (node.value === undefined || node.value === null || node.value === "") {
      return "Add a number for this patient detail. For example: age 40.";
    }
    return null;
  }
  if (node.kind === "RULE_FIRED") {
    if (!node.referenced_rule_id || !node.referenced_rule_id.trim()) {
      return "Pick a rule to depend on. Use the rule picker below.";
    }
    return null;
  }
  if (node.kind === "OBSERVATION") {
    return checkObservationOwnError(node.observation);
  }
  return checkGroupOwnError(node);
}

function checkConceptOwnError(node: EditableLogicNode): string | null {
  const c = node.criterion;
  const seeds = c?.seeds ?? [];
  const hasLegacy = !!c?.snomed_concept_id;
  if (seeds.length === 0 && !hasLegacy) {
    return "Pick a symptom, sign, procedure, or situation for the empty pill. Use the search box on the right.";
  }
  if (seeds.length === 0) {
    return null;
  }
  const seedIds = new Set(seeds.map((s) => s.snomed_concept_id));
  for (const x of c?.excluded_concept_ids ?? []) {
    if (seedIds.has(x)) {
      return "A code is in both the seeds and the exclude list. Remove it from one of the two.";
    }
  }
  if (c?.primary_concept_id && !seedIds.has(c.primary_concept_id)) {
    return "The chip's main code is no longer in the seed list. Pick a new main code.";
  }
  return null;
}

function checkObservationOwnError(
  obs: EditableObservationPayload | undefined,
): string | null {
  if (!obs) {
    return "Pick a lab test or reading for the empty lab row.";
  }
  if (!obs.observable_id || !obs.observable_id.trim()) {
    return "Pick a lab test or reading (for example: platelet count).";
  }
  if (obs.operator !== "between") {
    if (!Number.isFinite(obs.value as number)) {
      return "Add a number for this lab test (for example: 400).";
    }
    return null;
  }
  const pair = Array.isArray(obs.value) ? obs.value : null;
  if (!pair || pair.length !== 2) {
    return "'Is between' needs two numbers: a low and a high.";
  }
  if (!Number.isFinite(pair[0]) || !Number.isFinite(pair[1])) {
    return "'Is between' needs two numbers.";
  }
  if (pair[0] > pair[1]) {
    return "'Is between' needs the low number to be at most the high number.";
  }
  return null;
}

function checkGroupOwnError(node: EditableLogicNode): string | null {
  const children = node.children ?? [];
  if (children.length === 0) {
    if (node.pathway_key) {
      return (
        "This situation has no conditions yet. Open Who, add what must " +
        "be true for it, or remove the situation."
      );
    }
    if (node.kind === "AT_LEAST" && node.cluster_role) {
      return (
        "A 'match some of these' list is empty. Add symptoms to it, " +
        "or remove the empty list."
      );
    }
    return "One of the groups is empty. Add a symptom, procedure, situation, or patient detail, or remove the group.";
  }
  if (node.kind === "NOT" && children.length !== 1) {
    return "A 'must NOT have' group needs exactly one symptom, sign, procedure, or situation inside it.";
  }
  if (node.kind === "AT_LEAST") {
    const min = node.min ?? 0;
    if (min < 1) {
      return "Pick how many of these the patient must have (at least 1).";
    }
    if (min > children.length) {
      return "You're asking for more symptoms than there are. Lower the number, or add more symptoms.";
    }
  }
  return null;
}

/** A single tree problem, tagged with the node that caused it so the UI
 *  can jump straight to it. ``nodeId`` is null only for the "there is no
 *  tree at all yet" case, where there is nothing on screen to jump to. */
export interface ValidationIssue {
  nodeId: string | null;
  message: string;
}

/**
 * Walk the WHOLE tree and return every problem we find, each tagged with
 * the offending node's id, in plain English (reading age 9-11). Unlike
 * ``findValidationError`` this does not stop at the first problem -- it
 * powers "jump to issue" navigation, which needs to know about every
 * problem up front, not just the first one the reviewer happens to hit.
 */
function findNodeByIdLocal(
  node: EditableLogicNode,
  nodeId: string,
): EditableLogicNode | null {
  if (node.node_id === nodeId) return node;
  for (const child of node.children ?? []) {
    const found = findNodeByIdLocal(child, nodeId);
    if (found) return found;
  }
  return null;
}

/**
 * Issues for the in-wizard banner. Skips empty situation (pathway)
 * shells that the reviewer has not filled yet -- those are expected
 * while coding Situation A of N. Save still uses ``findAllValidationErrors``
 * so unfinished situations cannot be approved.
 */
export function findWizardValidationErrors(
  node: EditableLogicNode | null,
): ValidationIssue[] {
  return findAllValidationErrors(node).filter((issue) => {
    if (!issue.nodeId || !node) return true;
    const target = findNodeByIdLocal(node, issue.nodeId);
    if (!target?.pathway_key) return true;
    return (target.children ?? []).length > 0;
  });
}

export function findAllValidationErrors(
  node: EditableLogicNode | null,
): ValidationIssue[] {
  if (!node) {
    return [
      {
        nodeId: null,
        message:
          "This rule needs at least one condition. Click + to add a symptom, procedure, situation, or patient detail.",
      },
    ];
  }
  const ownError = checkNodeOwnError(node);
  const issues: ValidationIssue[] = ownError
    ? [{ nodeId: node.node_id, message: ownError }]
    : [];
  for (const child of node.children ?? []) {
    issues.push(...findAllValidationErrors(child));
  }
  return issues;
}

/**
 * Walk the tree and return the first problem we find in plain English, or
 * null when the tree is valid. Mirrors the server-side validator so the user
 * gets immediate feedback before clicking Save. Messages follow the
 * health-literacy rule (reading age 9-11, plain English, active voice).
 */
export function findValidationError(node: EditableLogicNode | null): string | null {
  return findAllValidationErrors(node)[0]?.message ?? null;
}

/**
 * A rule always needs at least one recommended procedure, even before
 * every row is fully coded -- an empty ``actions`` array means there is
 * nothing at all for the system to suggest when the rule fires. Mirrors
 * ``findValidationError``'s plain-English style (reading age 9-11).
 */
export function findActionsValidationError(actions: RuleAction[]): string | null {
  if (actions.length === 0) {
    return "This rule needs at least one recommended procedure. Click Add another procedure to add one.";
  }
  return null;
}

/**
 * Validate rule-level clinical priority. Due-days must be blank for
 * routine priority and a non-negative integer otherwise when set.
 */
export function findPriorityValidationError(
  priority: string,
  dueDays: number | null,
): string | null {
  if (
    priority !== "immediate" &&
    priority !== "very_urgent" &&
    priority !== "2ww" &&
    priority !== "urgent" &&
    priority !== "routine"
  ) {
    return (
      "Pick a clinical priority: immediate, very urgent (48 hours), " +
      "2 week wait, urgent, or routine."
    );
  }
  if (priority === "routine") return null;
  if (dueDays == null) return null;
  if (!Number.isFinite(dueDays) || dueDays < 0) {
    return "Due days must be zero or a positive whole number.";
  }
  return null;
}
