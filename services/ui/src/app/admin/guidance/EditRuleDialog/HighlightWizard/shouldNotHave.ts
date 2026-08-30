/**
 * Helpers for guided-editor "Patient should not have" exclusions.
 *
 * Atlas trace:
 *   DO: DO-4EA3C153
 *   DI: DI-0F0B27D3, DI-42246DA7
 *   Risks: R-4E4F22EF
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-4EA3C153")
 */

import type { EditableLogicNode, NodeUpdate } from "../types";

const EXCLUSION_LEAF_KINDS = new Set([
  "CONCEPT",
  "DEMOGRAPHIC",
  "OBSERVATION",
  "MEDICATION",
  "ALLERGY",
  "TREATMENT_HISTORY",
  "RULE_FIRED",
]);

export function findDirectNotGroup(
  parent: EditableLogicNode,
): EditableLogicNode | null {
  return (parent.children ?? []).find((child) => child.kind === "NOT") ?? null;
}

export function collectShouldNotHaveLeaves(
  nodes: EditableLogicNode[],
): EditableLogicNode[] {
  const leaves: EditableLogicNode[] = [];
  const walkInsideNot = (n: EditableLogicNode): void => {
    if (EXCLUSION_LEAF_KINDS.has(n.kind)) {
      leaves.push(n);
      return;
    }
    for (const child of n.children ?? []) walkInsideNot(child);
  };
  const walk = (n: EditableLogicNode): void => {
    if (n.kind === "NOT") {
      for (const child of n.children ?? []) walkInsideNot(child);
      return;
    }
    if (EXCLUSION_LEAF_KINDS.has(n.kind)) return;
    for (const child of n.children ?? []) walk(child);
  };
  for (const node of nodes) walk(node);
  return leaves;
}

export function shouldNotHaveLabel(node: EditableLogicNode): string {
  const term = node.criterion?.preferred_term
    ?? node.observation?.observable_term
    ?? "";
  return term
    ? `Patient must not have ${term}`
    : "Patient must not have this finding";
}

export function beginShouldNotHaveAdd(args: {
  parent: EditableLogicNode | null | undefined;
  onUpdate: (update: NodeUpdate) => void;
  onRequestAdd: (
    parentNodeId: string,
    anchor?: HTMLElement | null,
    initialQuery?: string,
    multiPick?: boolean,
  ) => void;
  markPending: () => void;
  anchor?: HTMLElement;
}): void {
  const { parent, onUpdate, onRequestAdd, markPending, anchor } = args;
  if (!parent) return;
  const existing = findDirectNotGroup(parent);
  if (existing) {
    onRequestAdd(existing.node_id, anchor, undefined, true);
    return;
  }
  onUpdate({
    kind: "add_group",
    parentNodeId: parent.node_id,
    groupKind: "NOT",
  });
  markPending();
}
