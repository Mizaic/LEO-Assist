/**
 * Shared style tokens and grammar helpers for the SentenceEditor
 * (fill-in-the-blank prose canvas). Re-exports the color/label
 * vocabulary already established by LogicTreeEditor/shared.ts so the
 * two canvases agree on what a color or label means, and adds the
 * tint tokens + node-joining grammar unique to the prose layout.
 *
 * Atlas trace: DI-42246DA7 / DO-F8C56339
 */
import type { ReactNode } from "react";

export {
  KIND_COLORS,
  KIND_SECTION_LABELS,
  KIND_CONNECTOR,
} from "../LogicTreeEditor/shared";
export type { TreeCallbacks, NodeProps } from "../LogicTreeEditor/shared";

/**
 * Soft background tint per group kind, used for the nested "chunk"
 * that replaces indentation. Same hues as KIND_COLORS at low alpha
 * so a chunk's color still hints at its kind (OR vs AND vs NOT vs
 * AT_LEAST) without the heavy bordered-box look.
 */
export const KIND_TINTS: Record<string, string> = {
  OR: "rgba(8, 145, 178, 0.08)",
  AND: "rgba(37, 99, 235, 0.08)",
  NOT: "rgba(220, 38, 38, 0.08)",
  AT_LEAST: "rgba(124, 58, 237, 0.08)",
};

/** Border tint (slightly stronger than the fill) for the same chunk. */
export const KIND_TINT_BORDERS: Record<string, string> = {
  OR: "rgba(8, 145, 178, 0.24)",
  AND: "rgba(37, 99, 235, 0.24)",
  NOT: "rgba(220, 38, 38, 0.24)",
  AT_LEAST: "rgba(124, 58, 237, 0.24)",
};

/**
 * Join a list of React nodes into prose using the same grammar as
 * treeToSentence.ts's joinWithLast(): a single item is returned as-is,
 * two items are joined with the separator word, and three or more use
 * a comma list with the separator word before the last item.
 *
 *   joinNodes([a], "or")          -> a
 *   joinNodes([a, b], "or")       -> a "or" b
 *   joinNodes([a, b, c], "or")    -> a, b, "or" c
 *
 * Kept in lock-step with treeToSentence.ts's joinWithLast() so the
 * editable canvas and the read-only preview read identically.
 *
 * Callers must pass already-keyed elements (e.g. `<ConceptPill
 * key={child.node_id} .../>`) -- this helper only interleaves plain
 * separator strings between them and does not add keys itself.
 */
export function joinNodes(items: ReactNode[], lastSep: string): ReactNode[] {
  if (items.length === 0) return [];
  if (items.length === 1) return items;
  if (items.length === 2) {
    return [items[0], ` ${lastSep} `, items[1]];
  }
  const out: ReactNode[] = [];
  items.slice(0, -1).forEach((item, i) => {
    out.push(item);
    out.push(", ");
    void i;
  });
  out.push(`${lastSep} `);
  out.push(items[items.length - 1]);
  return out;
}
