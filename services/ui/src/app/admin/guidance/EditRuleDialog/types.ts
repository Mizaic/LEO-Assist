/**
 * Shared types for the EditRuleDialog.
 *
 * The shape mirrors the LogicNode contract on the API side
 * (services/api/app/services/guidance_rule_edit.py). Each editable node in the
 * UI carries a stable client-side ``node_id`` so list-style mutations
 * (replace, remove, insert) can target a specific node without relying on
 * object identity through React re-renders.
 *
 * Atlas trace:
 *   DO: DO-2C03CA0E
 *   DI: DI-3F771AFB
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-2C03CA0E")
 *
 * Phase 6 trace (OBSERVATION leaf UI + ingest + backfill):
 *   UN: UN-26E57FA1
 *   DI: DI-4C8A09C3
 *   DO: DO-CB6324A3
 *   Risk: R-555C8691 (shared with Phase 5 backend)
 *   VT: VT-1A7862B9 (execution_status=passed)
 *
 * Sprint 1 trace (MEDICATION / ALLERGY / TREATMENT_HISTORY leaves):
 *   DI: DI-2199E670
 *   DO: DO-0EC3A9CB
 */
export type LogicNodeKind =
  | "AND"
  | "OR"
  | "NOT"
  | "AT_LEAST"
  | "CONCEPT"
  | "DEMOGRAPHIC"
  | "OBSERVATION"
  | "MEDICATION"
  | "ALLERGY"
  | "TREATMENT_HISTORY";

/**
 * One SNOMED code in a CONCEPT criterion's synonym set (UN-LEO-AI-093).
 *
 * Each seed is independently expandable via the bitmap compiler's
 * IS_A descendant closure. ``include_descendants: false`` forces an
 * exact-match-only contribution from this seed.
 */
export interface LogicSeed {
  snomed_concept_id: string;
  preferred_term: string;
  semantic_tag?: string;
  /** Default true; mirrors LogicSeed.include_descendants on the API side. */
  include_descendants?: boolean;
  /** Per-seed override of the rule-level distance_child default (3). */
  distance_child?: number | null;
}

/**
 * Backwards compatible: legacy single-seed callers populate
 * ``snomed_concept_id`` + ``preferred_term`` only. New synonym-set
 * callers populate ``seeds`` (and optionally ``primary_concept_id``
 * and ``excluded_concept_ids``); the legacy fields are auto-derived
 * from the primary seed by the API model_validator.
 */
export interface LogicCriterion {
  snomed_concept_id: string;
  preferred_term: string;
  semantic_tag?: string;
  term?: string;
  /** Optional synonym-set seeds. Empty / absent means legacy single-seed. */
  seeds?: LogicSeed[];
  /** SNOMED ids subtracted from the union of seed closures before bitmap. */
  excluded_concept_ids?: string[];
  /** Names which seed supplies the chip's headline label. */
  primary_concept_id?: string;
}

/**
 * Comparison operators supported on an OBSERVATION leaf. Mirrors the
 * ``ComparisonOperator`` Literal in
 * ``libs/guidance_schema/observation_leaf.py``.
 */
export type ObservationOperator =
  | ">="
  | "<="
  | ">"
  | "<"
  | "="
  | "between";

/**
 * N-consecutive-readings temporal pattern (for example "two PSAs more
 * than six months apart"). Mirrors ``TemporalSpec``.
 */
export interface ObservationTemporalSpec {
  count: number;
  interval_min_days: number;
  interval_max_days?: number | null;
}

/**
 * Reference-range-relative comparison (for example "above ULN").
 * Mirrors ``ReferenceRangeSpec``.
 */
export interface ObservationReferenceRangeSpec {
  bound: "upper" | "lower";
  multiple_of_range?: number;
}

/**
 * Trend / delta over a window (for example "eGFR fell 25% in the last
 * year"). Mirrors ``TrendSpec``.
 */
export interface ObservationTrendSpec {
  delta_kind: "absolute" | "percent";
  window_days: number;
}

/**
 * Mean / median / min / max of the last N readings. Mirrors
 * ``AggregateSpec``.
 */
export interface ObservationAggregateSpec {
  kind: "mean" | "median" | "min" | "max";
  lookback_n: number;
}

/**
 * Flat wire shape for the OBSERVATION leaf payload. Matches
 * ``ObservationLeaf`` in ``libs/guidance_schema/observation_leaf.py``
 * 1-for-1 so the tree can round-trip through the Pydantic validator
 * without field-name translation.
 *
 * Exactly one of ``temporal`` / ``reference_range`` / ``trend`` /
 * ``aggregation`` may be populated. All four absent means "absolute"
 * mode (default).
 */
export interface EditableObservationPayload {
  kind?: "OBSERVATION";
  observable_id: string;
  observable_term?: string;
  operator: ObservationOperator;
  value: number | [number, number];
  unit: string;
  within_days?: number;
  temporal?: ObservationTemporalSpec | null;
  reference_range?: ObservationReferenceRangeSpec | null;
  trend?: ObservationTrendSpec | null;
  aggregation?: ObservationAggregateSpec | null;
}

export interface EditableLogicNode {
  node_id: string;
  kind: LogicNodeKind;
  children?: EditableLogicNode[];
  min?: number;
  criterion?: LogicCriterion;
  field?: string;
  operator?: string;
  value?: number | string | null;
  unit?: string | null;
  /**
   * Optional plain-English name for a group node (Phase 2 of the
   * edit-rule wizard redesign). Rendered as the pathway card title
   * in the editor and the read-only review view; falls back to a
   * positional "Pathway A/B/C" label when absent so legacy data
   * still renders sensibly.
   *
   * Stored as ``node.name`` in the saved JSON tree. The compiler and
   * evaluator ignore unknown fields, so this round-trips through
   * ``logic_tree`` without a Cypher schema change.
   */
  name?: string;
  /**
   * OBSERVATION leaf payload (Phase 6a). Present only on nodes with
   * ``kind === "OBSERVATION"``. Authoring in the sentence canvas is
   * limited to absolute-mode scalars in v1; ingest may populate the
   * advanced modes (temporal / reference_range / trend / aggregation)
   * which the canvas then renders read-only with a hint that the
   * Advanced view is needed for structural edits.
   */
  observation?: EditableObservationPayload;
}

/** Server response shape from /api/terminology/search. */
export interface ConceptSearchHit {
  snomed_concept_id: string;
  term: string;
  semantic_tag: string;
  score?: number;
}

/** Patches the dialog can apply to a node. */
export type NodeUpdate =
  | { kind: "replace_concept"; nodeId: string; criterion: LogicCriterion }
  | { kind: "set_min"; nodeId: string; min: number }
  | { kind: "set_demographic"; nodeId: string; field: string; operator: string; value: string; unit: string | null }
  | { kind: "change_kind"; nodeId: string; newKind: LogicNodeKind }
  | { kind: "remove"; nodeId: string }
  | { kind: "add_concept"; parentNodeId: string; criterion: LogicCriterion }
  | { kind: "add_group"; parentNodeId: string; groupKind: "AND" | "OR" | "NOT" | "AT_LEAST" }
  | { kind: "add_demographic"; parentNodeId: string }
  // -- Phase 2: optional pathway name --
  | { kind: "set_name"; nodeId: string; name: string }
  // -- Phase 6a: OBSERVATION leaf --
  | {
      kind: "add_observation";
      parentNodeId: string;
      /**
       * Phase 6b: optional seed for the new OBSERVATION leaf. When a
       * reviewer picks an observable concept in the search panel we
       * preload the observable_id / observable_term / unit so the
       * reviewer only has to fill in the operator and threshold.
       */
      seed?: Partial<EditableObservationPayload>;
    }
  | {
      kind: "set_observation";
      nodeId: string;
      observation: EditableObservationPayload;
    }
  // -- Synonym chip ops (UN-LEO-AI-093) --
  | { kind: "add_seed"; nodeId: string; seed: LogicSeed }
  | { kind: "remove_seed"; nodeId: string; conceptId: string }
  | { kind: "set_primary_seed"; nodeId: string; conceptId: string }
  | { kind: "toggle_include_descendants"; nodeId: string; conceptId: string }
  | { kind: "set_seed_distance"; nodeId: string; conceptId: string; distance: number | null }
  | { kind: "add_excluded"; nodeId: string; conceptId: string }
  | { kind: "remove_excluded"; nodeId: string; conceptId: string }
  | { kind: "replace_root"; node: EditableLogicNode };

export const GROUP_KINDS: ReadonlyArray<LogicNodeKind> = ["AND", "OR", "NOT", "AT_LEAST"];

/**
 * Sandbox impact badge data surfaced to Step 1 after a test run.
 * Produced by TestPatientsPanel, consumed by the tree editor header.
 */
export interface SandboxImpactBadge {
  status: "fresh" | "stale" | "running" | "empty";
  firingPatients: number;
  totalPatients: number;
}
export const LEAF_KINDS: ReadonlyArray<LogicNodeKind> = [
  "CONCEPT",
  "DEMOGRAPHIC",
  "OBSERVATION",
];

/** Demographic field/operator vocabularies must match the backend allow-list. */
export const DEMOGRAPHIC_FIELDS = ["age", "sex"] as const;
export const DEMOGRAPHIC_OPERATORS = [">=", "<=", ">", "<", "=", "between"] as const;
