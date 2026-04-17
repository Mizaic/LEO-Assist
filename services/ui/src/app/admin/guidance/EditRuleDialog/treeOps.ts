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
 */

import type {
  EditableLogicNode,
  LogicCriterion,
  LogicNodeKind,
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
};

function normaliseKind(raw: string | undefined): LogicNodeKind {
  if (!raw) return "AND";
  const upper = raw.toUpperCase();
  return KIND_MAP[upper] ?? "AND";
}

/** Strip node_id from the tree before sending to the API. */
export function stripNodeIds(node: EditableLogicNode): Record<string, unknown> {
  const out: Record<string, unknown> = { kind: node.kind };
  if (node.criterion) out.criterion = node.criterion;
  if (node.field !== undefined) out.field = node.field;
  if (node.operator !== undefined) out.operator = node.operator;
  if (node.value !== undefined && node.value !== null) out.value = node.value;
  if (node.unit !== undefined && node.unit !== null) out.unit = node.unit;
  if (node.min !== undefined) out.min = node.min;
  if (node.children?.length) out.children = node.children.map(stripNodeIds);
  return out;
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
    default:
      return root;
  }
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
    if (!node.criterion?.snomed_concept_id) {
      return "Pick a symptom or sign for the empty pill. Use the search box on the right.";
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
