/**
 * Detect repeated symptom sets inside a logic tree.
 *
 * Many LLM-extracted NICE rules end up with two AT-LEAST clusters that
 * carry the exact same SNOMED concepts (for example two pathways that
 * both reference the lung-cancer red flags). Surfacing this lets the
 * reviewer either:
 *   - extract the set into a single named symptom-set (Phase 4 work), or
 *   - delete the duplicate.
 *
 * For Phase 3 we just compute the duplicates so the editor can show a
 * banner; the named-set extraction UI lands when the API gains a
 * named-set table in DI-LEO-AI-156.
 */

import type { EditableLogicNode } from "./types";

export interface DuplicateSet {
  /** Sorted SNOMED ids joined with "|" -- the signature key. */
  signature: string;
  /** Friendly preview of the first three concepts in the set. */
  preview: string[];
  /** node_id of every group with this signature. */
  nodeIds: string[];
}

interface ConceptGroup {
  nodeId: string;
  signature: string;
  terms: string[];
}

function collectConceptGroups(
  node: EditableLogicNode,
  out: ConceptGroup[],
): void {
  const isPureConceptCluster =
    (node.kind === "AT_LEAST" || node.kind === "AND" || node.kind === "OR") &&
    (node.children?.length ?? 0) >= 2 &&
    (node.children ?? []).every(
      (c) => c.kind === "CONCEPT" && c.criterion?.snomed_concept_id,
    );

  if (isPureConceptCluster) {
    const ids = (node.children ?? [])
      .map((c) => c.criterion?.snomed_concept_id ?? "")
      .filter(Boolean)
      .sort();
    if (ids.length >= 2) {
      out.push({
        nodeId: node.node_id,
        signature: ids.join("|"),
        terms: (node.children ?? []).map(
          (c) => c.criterion?.preferred_term ?? c.criterion?.snomed_concept_id ?? "",
        ),
      });
    }
  }

  for (const child of node.children ?? []) {
    collectConceptGroups(child, out);
  }
}

/**
 * Return one entry per signature that occurs in two or more concept
 * clusters in the tree. Single-occurrence groups are filtered out so
 * the banner only fires when there is something worth flagging.
 */
export function findDuplicateConceptGroups(
  root: EditableLogicNode | null,
): DuplicateSet[] {
  if (!root) return [];
  const all: ConceptGroup[] = [];
  collectConceptGroups(root, all);
  const bySig = new Map<string, ConceptGroup[]>();
  for (const g of all) {
    const list = bySig.get(g.signature) ?? [];
    list.push(g);
    bySig.set(g.signature, list);
  }
  const dupes: DuplicateSet[] = [];
  for (const [sig, groups] of bySig) {
    if (groups.length < 2) continue;
    dupes.push({
      signature: sig,
      preview: groups[0].terms.slice(0, 3),
      nodeIds: groups.map((g) => g.nodeId),
    });
  }
  return dupes;
}
