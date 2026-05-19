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
 *   DO: DO-D6CE2AA5
 *   DI: DI-A3107424
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-D6CE2AA5")
 */
import type {
  EditableLogicNode,
  EditableObservationPayload,
  LogicCriterion,
  LogicNodeKind,
  LogicSeed,
  NodeUpdate,
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
function freshNodeId(): string {
  _idCounter += 1;
  return `n_${Date.now().toString(36)}_${_idCounter}`;
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
  return {
    ...node,
    node_id: node.node_id ?? freshNodeId(),
    kind: normaliseKind(node.kind),
    ...(children.length ? { children } : {}),
  } as EditableLogicNode;
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
};

function normaliseKind(raw: string | undefined): LogicNodeKind {
  if (!raw) return "AND";
  const upper = raw.toUpperCase();
  return KIND_MAP[upper] ?? "AND";
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
 * Strip node_id (and any other UI-only / LLM-only metadata) before sending
 * the tree to the BE. The criterion on each CONCEPT leaf is also passed
 * through ``sanitiseCriterion`` so the BE's ``extra: "forbid"`` validator
 * never sees an unknown key.
 */
export function stripNodeIds(node: EditableLogicNode): Record<string, unknown> {
  const out: Record<string, unknown> = { kind: node.kind };
  if (node.criterion) out.criterion = sanitiseCriterion(node.criterion);
  if (node.field !== undefined) out.field = node.field;
  if (node.operator !== undefined) out.operator = node.operator;
  if (node.value !== undefined && node.value !== null) out.value = node.value;
  if (node.unit !== undefined && node.unit !== null) out.unit = node.unit;
  if (node.min !== undefined) out.min = node.min;
  // Phase 2: keep the pathway name when it's a non-empty string. Empty
  // strings drop so the BE's ``model_config = {"extra": "forbid"}``
  // Pydantic model never sees an empty ``name`` field.
  if (typeof node.name === "string" && node.name.trim()) {
    out.name = node.name.trim();
  }
  // Phase 6a: round-trip the OBSERVATION payload verbatim. The BE
  // Pydantic model accepts the flat shape directly so no field
  // translation is needed. Mode specs that are null / undefined are
  // dropped entirely because Pydantic's ``model_config =
  // {"extra": "forbid"}`` rejects keys it has not declared for the
  // currently-active mode.
  if (node.kind === "OBSERVATION" && node.observation) {
    out.observation = stripObservation(node.observation);
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
    unit: obs.unit,
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
    const next =
      distance === null || Number.isNaN(distance)
        ? null
        : Math.max(0, Math.floor(distance));
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
    case "set_demographic":
      return mapNode(root, (n) =>
        n.node_id === update.nodeId && n.kind === "DEMOGRAPHIC"
          ? {
              ...n,
              field: update.field,
              operator: update.operator,
              value: update.value,
              unit: update.unit,
            }
          : n,
      );
    case "change_kind":
      return mapNode(root, (n) =>
        n.node_id === update.nodeId ? coerceKind(n, update.newKind) : n,
      );
    case "remove":
      if (root.node_id === update.nodeId) return null;
      return mapNode(root, (n) => (n.node_id === update.nodeId ? null : n));
    case "add_concept":
      return mapNode(root, (n) =>
        n.node_id === update.parentNodeId && canHaveChildren(n.kind)
          ? appendChild(n, makeConceptNode(update.criterion))
          : n,
      );
    case "add_group":
      return mapNode(root, (n) =>
        n.node_id === update.parentNodeId && canHaveChildren(n.kind)
          ? appendChild(n, makeGroupNode(update.groupKind))
          : n,
      );
    case "add_demographic":
      return mapNode(root, (n) =>
        n.node_id === update.parentNodeId && canHaveChildren(n.kind)
          ? appendChild(n, makeDemographicNode())
          : n,
      );
    case "add_observation":
      return mapNode(root, (n) =>
        n.node_id === update.parentNodeId && canHaveChildren(n.kind)
          ? appendChild(n, makeObservationNode(update.seed))
          : n,
      );
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
    default:
      return root;
  }
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

function canHaveChildren(kind: LogicNodeKind): boolean {
  return kind === "AND" || kind === "OR" || kind === "NOT" || kind === "AT_LEAST";
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
  return stripped;
}

function makeConceptNode(criterion: LogicCriterion): EditableLogicNode {
  return { node_id: freshNodeId(), kind: "CONCEPT", criterion };
}

function makeGroupNode(kind: LogicNodeKind): EditableLogicNode {
  return {
    node_id: freshNodeId(),
    kind,
    children: [],
    ...(kind === "AT_LEAST" ? { min: 1 } : {}),
  };
}

function makeDemographicNode(): EditableLogicNode {
  return {
    node_id: freshNodeId(),
    kind: "DEMOGRAPHIC",
    field: "age",
    operator: ">=",
    value: 40,
    unit: "years",
  };
}

/**
 * Blank OBSERVATION leaf the reviewer can fill in. ``observable_id``
 * and ``unit`` start empty so ``findValidationError`` surfaces a
 * friendly message until the reviewer picks an observable and unit
 * via the concept-search popover (Phase 6b).
 */
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
 * Walk the tree and return the first problem we find in plain English, or
 * null when the tree is valid. Mirrors the server-side validator so the user
 * gets immediate feedback before clicking Save. Messages follow the
 * health-literacy rule (reading age 9-11, plain English, active voice).
 */
export function findValidationError(node: EditableLogicNode | null): string | null {
  if (!node) {
    return "This rule needs at least one condition. Click + to add a symptom or patient detail.";
  }
  if (node.kind === "CONCEPT") {
    const c = node.criterion;
    const seeds = c?.seeds ?? [];
    const hasLegacy = !!c?.snomed_concept_id;
    if (seeds.length === 0 && !hasLegacy) {
      return "Pick a symptom or sign for the empty pill. Use the search box on the right.";
    }
    if (seeds.length > 0) {
      const seedIds = new Set(seeds.map((s) => s.snomed_concept_id));
      for (const x of c?.excluded_concept_ids ?? []) {
        if (seedIds.has(x)) {
          return "A code is in both the seeds and the exclude list. Remove it from one of the two.";
        }
      }
      if (
        c?.primary_concept_id &&
        !seedIds.has(c.primary_concept_id)
      ) {
        return "The chip's main code is no longer in the seed list. Pick a new main code.";
      }
    }
    return null;
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
  if (node.kind === "OBSERVATION") {
    const obs = node.observation;
    if (!obs) {
      return "Pick a lab test or reading for the empty lab row.";
    }
    if (!obs.observable_id || !obs.observable_id.trim()) {
      return "Pick a lab test or reading (for example: platelet count).";
    }
    if (!obs.unit || !obs.unit.trim()) {
      return "Pick the unit for this lab test (for example: x10^9/L).";
    }
    if (obs.operator === "between") {
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
    } else if (!Number.isFinite(obs.value as number)) {
      return "Add a number for this lab test (for example: 400).";
    }
    return null;
  }
  const children = node.children ?? [];
  if (children.length === 0) {
    return "One of the groups is empty. Add a symptom or patient detail, or remove the group.";
  }
  if (node.kind === "NOT" && children.length !== 1) {
    return "A 'must NOT have' group needs exactly one symptom or sign inside it.";
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
  for (const child of children) {
    const childError = findValidationError(child);
    if (childError) return childError;
  }
  return null;
}
