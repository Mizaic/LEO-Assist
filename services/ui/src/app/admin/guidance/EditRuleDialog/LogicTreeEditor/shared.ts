/**
 * Shared prop interfaces for the LogicTreeEditor sub-component tree.
 *
 * Atlas trace:
 *   DI: DI-42246DA7
 *   DO: DO-F8C56339
 */
import type { EditableLogicNode, NodeUpdate } from "../types";

export interface TreeCallbacks {
  selectedNodeId: string | null;
  onSelect: (nodeId: string, anchor?: HTMLElement | null) => void;
  onUpdate: (update: NodeUpdate) => void;
  onRequestAdd: (parentNodeId: string, anchor?: HTMLElement | null) => void;
  onRequestCoach?: (nodeId: string, anchor: HTMLElement) => void;
  /** Guideline (compileScopeId) for the rule currently being edited.
   *  Passed to RuleFiredRow so the rule picker can scope the list to
   *  sibling rules and exclude the current rule's own ID. */
  guidelineId?: string;
  /** The ID of the rule currently being edited; used to exclude self-reference. */
  currentRuleId?: string;
}

export interface NodeProps extends TreeCallbacks {
  node: EditableLogicNode;
  root: EditableLogicNode;
  depth: number;
}

/** Left-border color per group kind. */
export const KIND_COLORS: Record<string, string> = {
  OR: "#0891b2",
  AND: "#2563EB",
  NOT: "#DC2626",
  AT_LEAST: "#7C3AED",
};

/** UPPERCASE section label per group kind. */
export const KIND_SECTION_LABELS: Record<string, string> = {
  OR: "EITHER OF THESE",
  AND: "ALL OF THESE",
  NOT: "PATIENT SHOULD NOT HAVE",
  AT_LEAST: "AT LEAST N OF THESE",
};

/** Small connector label shown between rows inside a group. */
export const KIND_CONNECTOR: Record<string, string> = {
  OR: "or",
  AND: "and",
  NOT: "and not",
  AT_LEAST: "or",
};
