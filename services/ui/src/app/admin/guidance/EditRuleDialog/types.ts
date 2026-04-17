/**
 * Shared types for the EditRuleDialog.
 *
 * The shape mirrors the LogicNode contract on the API side
 * (services/api/app/services/guidance_rule_edit.py). Each editable node in the
 * UI carries a stable client-side ``node_id`` so list-style mutations
 * (replace, remove, insert) can target a specific node without relying on
 * object identity through React re-renders.
 */

export type LogicNodeKind =
  | "AND"
  | "OR"
  | "NOT"
  | "AT_LEAST"
  | "CONCEPT"
  | "DEMOGRAPHIC";

export interface LogicCriterion {
  snomed_concept_id: string;
  preferred_term: string;
  semantic_tag?: string;
  term?: string;
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
  | { kind: "add_demographic"; parentNodeId: string };

export const GROUP_KINDS: ReadonlyArray<LogicNodeKind> = ["AND", "OR", "NOT", "AT_LEAST"];
export const LEAF_KINDS: ReadonlyArray<LogicNodeKind> = ["CONCEPT", "DEMOGRAPHIC"];

/** Demographic field/operator vocabularies must match the backend allow-list. */
export const DEMOGRAPHIC_FIELDS = ["age", "sex"] as const;
export const DEMOGRAPHIC_OPERATORS = [">=", "<=", ">", "<", "=", "between"] as const;
