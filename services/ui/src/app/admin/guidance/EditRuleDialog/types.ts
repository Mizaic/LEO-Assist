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
 */
export type LogicNodeKind =
  | "AND"
  | "OR"
  | "NOT"
  | "AT_LEAST"
  | "CONCEPT"
  | "DEMOGRAPHIC";

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
  | { kind: "set_name"; nodeId: string; name: string }
  // -- Synonym chip ops (UN-LEO-AI-093) --
  | { kind: "add_seed"; nodeId: string; seed: LogicSeed }
  | { kind: "remove_seed"; nodeId: string; conceptId: string }
  | { kind: "set_primary_seed"; nodeId: string; conceptId: string }
  | { kind: "toggle_include_descendants"; nodeId: string; conceptId: string }
  | { kind: "set_seed_distance"; nodeId: string; conceptId: string; distance: number | null }
  | { kind: "add_excluded"; nodeId: string; conceptId: string }
  | { kind: "remove_excluded"; nodeId: string; conceptId: string };

export const GROUP_KINDS: ReadonlyArray<LogicNodeKind> = ["AND", "OR", "NOT", "AT_LEAST"];
export const LEAF_KINDS: ReadonlyArray<LogicNodeKind> = ["CONCEPT", "DEMOGRAPHIC"];

/** Demographic field/operator vocabularies must match the backend allow-list. */
export const DEMOGRAPHIC_FIELDS = ["age", "sex"] as const;
export const DEMOGRAPHIC_OPERATORS = [">=", "<=", ">", "<", "=", "between"] as const;
