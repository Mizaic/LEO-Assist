/**
 * Pure helpers that turn an EditableLogicNode tree into the
 * SentenceCanvas's flat card model.
 *
 * Phase 3 of the edit-rule wizard redesign moves the primary editing
 * surface from a visible operator tree to a stack of plain-English
 * "sentence cards":
 *
 *   WhoCard       -- one "Patient must have ..." block of leaf rows
 *   PathwayCard[] -- one card per OR branch of "match any of these"
 *   NoneOfCard    -- optional "Patient must NOT have any of these"
 *
 * The compiler / evaluator contract is unchanged; this module only
 * recognises the tree shapes the canvas can render and falls back to
 * "unsupported" when it sees something the canvas would silently
 * mangle. Unsupported shapes are still fully editable through the
 * Advanced view (LogicTreeEditor) so we never drop information.
 *
 * Shapes recognised today:
 *
 *   AND[ DEMOGRAPHIC*, CONCEPT*, AT_LEAST(CONCEPT*)*, NOT(CONCEPT|AND/OR(CONCEPT*)), OR(...)? ]
 *   OR[ AND(...) | CONCEPT | DEMOGRAPHIC | AT_LEAST | NOT ... ]
 *   single CONCEPT | DEMOGRAPHIC | AT_LEAST(CONCEPT*) at the root
 *
 * Anything else returns ``{ kind: "unsupported", reason }`` and the
 * canvas surface renders a "use Advanced view" prompt.
 *
 * The functions in this file are pure and have no React dependency
 * so they are exhaustively unit-testable.
 *
 * Atlas trace:
 *   UN: UN-26E57FA1
 *   DI: DI-C46DDFA3
 *   DO: DO-D4D4CAA8
 *   Risk: R-5F11517C
 *   VT: VT-123BDE46
 */
import type { EditableLogicNode } from "./types";

/** A single editable row inside a sentence card. */
export interface SentenceRowModel {
  /** node_id of the EditableLogicNode this row represents. */
  nodeId: string;
  /**
   * Visual variant. ``unsupported`` is the safety hatch for tree
   * shapes the canvas cannot yet render in-place; the Advanced view
   * (LogicTreeEditor) still handles them.
   *
   * ``observation`` is reserved for Phase 6 -- the dispatch case
   * already exists so adding the OBSERVATION leaf later is purely
   * additive.
   */
  variant:
    | "concept"
    | "demographic"
    | "at_least"
    | "observation"
    | "not_concept"
    | "unsupported";
  /** The original node, for renderers that need full access. */
  node: EditableLogicNode;
}

export interface WhoCard {
  /** node_id of the wrapping AND group (or the root leaf). */
  parentNodeId: string;
  rows: SentenceRowModel[];
}

export interface PathwayCard {
  /** node_id of the OR child this card represents. */
  nodeId: string;
  /** node_id of the parent OR group, used by "remove pathway". */
  parentNodeId: string;
  /** Optional plain-English name; trimmed empty strings drop. */
  name?: string;
  /** Positional fallback letter ("A", "B", ...). */
  positional: string;
  /**
   * Where to attach new rows added inside this pathway. For an AND
   * pathway this is the AND's node_id; for a bare leaf pathway we
   * promote-to-AND on first add (the canvas handles that by emitting
   * an ``add_group`` with kind "AND" before the row).
   */
  bodyParentNodeId: string;
  /** True when ``bodyParentNodeId === nodeId`` (proper AND wrapper). */
  hasAndWrapper: boolean;
  rows: SentenceRowModel[];
}

export interface NoneOfCard {
  /** node_id of the NOT group. */
  nodeId: string;
  /**
   * node_id of the inner group whose children are forbidden -- equal
   * to ``nodeId`` when the NOT wraps a single CONCEPT, otherwise the
   * inner OR/AND/AT_LEAST group's id.
   */
  bodyParentNodeId: string;
  rows: SentenceRowModel[];
}

export interface SupportedCanvas {
  kind: "canvas";
  rootNodeId: string;
  whoCard?: WhoCard;
  /** node_id of the OR group, used by "Add another pathway". */
  pathwayParentNodeId?: string;
  pathways?: PathwayCard[];
  noneOf?: NoneOfCard;
}

export interface UnsupportedCanvas {
  kind: "unsupported";
  reason: string;
}

export type CanvasModel = SupportedCanvas | UnsupportedCanvas;

const UNSUPPORTED_REASON_MULTIPLE_OR =
  "More than one alternative pathway group at the top of the rule.";
const UNSUPPORTED_REASON_NESTED_OR =
  "A pathway has nested OR groups inside it.";
const UNSUPPORTED_REASON_NESTED_GROUP =
  "Nested groups outside the pathway split.";
const UNSUPPORTED_REASON_COMPLEX_NOT =
  "A 'must NOT have' group has a complex inner shape.";

/**
 * Convert one node into a SentenceRowModel.
 *
 * For AT_LEAST and NOT we only emit a friendly variant when the
 * inner shape is itself simple enough to render as a single row;
 * otherwise the variant is ``unsupported`` so the parent can decide
 * to fall back.
 */
export function rowFor(node: EditableLogicNode): SentenceRowModel {
  if (node.kind === "CONCEPT") {
    return { nodeId: node.node_id, variant: "concept", node };
  }
  if (node.kind === "DEMOGRAPHIC") {
    return { nodeId: node.node_id, variant: "demographic", node };
  }
  if (node.kind === "AT_LEAST") {
    const kids = node.children ?? [];
    const allConcepts = kids.length > 0 && kids.every((c) => c.kind === "CONCEPT");
    return {
      nodeId: node.node_id,
      variant: allConcepts ? "at_least" : "unsupported",
      node,
    };
  }
  if (node.kind === "NOT") {
    const inner = (node.children ?? [])[0];
    if (inner && inner.kind === "CONCEPT") {
      return { nodeId: node.node_id, variant: "not_concept", node };
    }
    return { nodeId: node.node_id, variant: "unsupported", node };
  }
  return { nodeId: node.node_id, variant: "unsupported", node };
}

function pathwayCardFor(
  child: EditableLogicNode,
  parentNodeId: string,
  index: number,
): PathwayCard | { unsupported: true } {
  const positional = `Pathway ${String.fromCharCode(65 + index)}`;
  const trimmedName =
    typeof child.name === "string" && child.name.trim()
      ? child.name.trim()
      : undefined;

  if (child.kind === "AND") {
    const rows = (child.children ?? []).map(rowFor);
    if (rows.some((r) => r.variant === "unsupported")) {
      return { unsupported: true };
    }
    return {
      nodeId: child.node_id,
      parentNodeId,
      name: trimmedName,
      positional,
      bodyParentNodeId: child.node_id,
      hasAndWrapper: true,
      rows,
    };
  }

  if (
    child.kind === "CONCEPT" ||
    child.kind === "DEMOGRAPHIC" ||
    child.kind === "AT_LEAST" ||
    child.kind === "NOT"
  ) {
    const r = rowFor(child);
    if (r.variant === "unsupported") return { unsupported: true };
    return {
      nodeId: child.node_id,
      parentNodeId,
      name: trimmedName,
      positional,
      // No AND wrapper yet; the canvas's "add row" CTA will need to
      // promote the bare leaf into an AND before appending. The
      // renderer treats ``hasAndWrapper=false`` as "Add row" disabled
      // for now; users who want extra constraints in this pathway can
      // open the Advanced view.
      bodyParentNodeId: child.node_id,
      hasAndWrapper: false,
      rows: [r],
    };
  }

  return { unsupported: true };
}

/**
 * Map an EditableLogicNode tree into a CanvasModel.
 *
 * Returns ``{ kind: "unsupported", reason }`` when the tree shape is
 * outside the canvas vocabulary. The returned ``reason`` is shown to
 * the user verbatim in the canvas's "Open Advanced view" empty state.
 */
export function treeToCanvas(root: EditableLogicNode): CanvasModel {
  if (root.kind === "AND") {
    const kids = root.children ?? [];
    const ors = kids.filter((c) => c.kind === "OR");
    const nots = kids.filter((c) => c.kind === "NOT");
    const others = kids.filter((c) => c.kind !== "OR" && c.kind !== "NOT");

    if (ors.length > 1) {
      return { kind: "unsupported", reason: UNSUPPORTED_REASON_MULTIPLE_OR };
    }
    if (nots.length > 1) {
      return { kind: "unsupported", reason: UNSUPPORTED_REASON_COMPLEX_NOT };
    }

    const whoRows = others.map(rowFor);
    if (whoRows.some((r) => r.variant === "unsupported")) {
      return { kind: "unsupported", reason: UNSUPPORTED_REASON_NESTED_GROUP };
    }

    let pathways: PathwayCard[] | undefined;
    let pathwayParentNodeId: string | undefined;
    if (ors.length === 1) {
      const orGroup = ors[0];
      pathwayParentNodeId = orGroup.node_id;
      const out: PathwayCard[] = [];
      const orChildren = orGroup.children ?? [];
      for (let i = 0; i < orChildren.length; i++) {
        const result = pathwayCardFor(orChildren[i], orGroup.node_id, i);
        if ("unsupported" in result) {
          return { kind: "unsupported", reason: UNSUPPORTED_REASON_NESTED_OR };
        }
        out.push(result);
      }
      pathways = out;
    }

    let noneOf: NoneOfCard | undefined;
    if (nots.length === 1) {
      const notGroup = nots[0];
      const inner = (notGroup.children ?? [])[0];
      if (inner && inner.kind === "CONCEPT") {
        noneOf = {
          nodeId: notGroup.node_id,
          bodyParentNodeId: notGroup.node_id,
          rows: [rowFor(inner)],
        };
      } else if (
        inner &&
        (inner.kind === "OR" || inner.kind === "AND") &&
        (inner.children ?? []).every((c) => c.kind === "CONCEPT")
      ) {
        noneOf = {
          nodeId: notGroup.node_id,
          bodyParentNodeId: inner.node_id,
          rows: (inner.children ?? []).map(rowFor),
        };
      } else {
        return { kind: "unsupported", reason: UNSUPPORTED_REASON_COMPLEX_NOT };
      }
    }

    const whoCard: WhoCard | undefined = whoRows.length
      ? { parentNodeId: root.node_id, rows: whoRows }
      : undefined;

    return {
      kind: "canvas",
      rootNodeId: root.node_id,
      whoCard,
      pathwayParentNodeId,
      pathways,
      noneOf,
    };
  }

  if (root.kind === "OR") {
    const kids = root.children ?? [];
    const out: PathwayCard[] = [];
    for (let i = 0; i < kids.length; i++) {
      const result = pathwayCardFor(kids[i], root.node_id, i);
      if ("unsupported" in result) {
        return { kind: "unsupported", reason: UNSUPPORTED_REASON_NESTED_OR };
      }
      out.push(result);
    }
    return {
      kind: "canvas",
      rootNodeId: root.node_id,
      pathwayParentNodeId: root.node_id,
      pathways: out,
    };
  }

  if (
    root.kind === "CONCEPT" ||
    root.kind === "DEMOGRAPHIC" ||
    root.kind === "AT_LEAST"
  ) {
    const r = rowFor(root);
    if (r.variant === "unsupported") {
      return {
        kind: "unsupported",
        reason: "Top-level node has a complex shape.",
      };
    }
    return {
      kind: "canvas",
      rootNodeId: root.node_id,
      whoCard: { parentNodeId: root.node_id, rows: [r] },
    };
  }

  if (root.kind === "NOT") {
    const inner = (root.children ?? [])[0];
    if (inner && inner.kind === "CONCEPT") {
      return {
        kind: "canvas",
        rootNodeId: root.node_id,
        noneOf: {
          nodeId: root.node_id,
          bodyParentNodeId: root.node_id,
          rows: [rowFor(inner)],
        },
      };
    }
    return { kind: "unsupported", reason: UNSUPPORTED_REASON_COMPLEX_NOT };
  }

  return {
    kind: "unsupported",
    reason: `Top-level kind ${root.kind} not yet supported.`,
  };
}
