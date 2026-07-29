/**
 * Helpers for asserting saved guideline rule logic trees in Playwright
 * walkthroughs (e.g. NG12 1.3.1 situation E lead + either/or shape).
 */

export type TreeNode = {
  kind?: string;
  min?: number;
  field?: string;
  operator?: string;
  value?: string | number;
  unit?: string | null;
  criterion?: {
    snomed_concept_id?: string;
    preferred_term?: string;
    term?: string;
  };
  source_row_text?: string;
  children?: TreeNode[];
};

function nodeMentions(node: TreeNode | undefined, needle: string): boolean {
  if (!node) return false;
  const n = needle.toLowerCase();
  const hay = [
    node.criterion?.preferred_term,
    node.criterion?.term,
    node.source_row_text,
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
  if (hay.includes(n)) return true;
  return (node.children ?? []).some((c) => nodeMentions(c, needle));
}

/** Pathway AND that contains the needle (prefer deepest OR-child pathway). */
export function findSituationWithTerm(
  root: TreeNode | undefined,
  needle: string,
): TreeNode | undefined {
  if (!root) return undefined;
  if (root.kind === "OR") {
    for (const child of root.children ?? []) {
      const hit = findSituationWithTerm(child, needle);
      if (hit) return hit;
    }
  }
  if (root.kind === "AND" && nodeMentions(root, needle)) {
    for (const child of root.children ?? []) {
      if (child.kind === "OR") {
        const hit = findSituationWithTerm(child, needle);
        if (hit) return hit;
      }
      if (child.kind === "AND" && nodeMentions(child, needle)) return child;
    }
    return root;
  }
  for (const child of root.children ?? []) {
    const hit = findSituationWithTerm(child, needle);
    if (hit) return hit;
  }
  return undefined;
}

/**
 * Pathway where `leadSnomedId` is a direct CONCEPT sibling and an
 * AT_LEAST subgroup exists that does NOT contain that lead (NG12 1.3.1 E).
 */
export function findLeadPlusEitherOrSituation(
  root: TreeNode | undefined,
  leadSnomedId: string,
): TreeNode | undefined {
  if (!root) return undefined;
  if (root.kind === "OR") {
    for (const child of root.children ?? []) {
      const hit = findLeadPlusEitherOrSituation(child, leadSnomedId);
      if (hit) return hit;
    }
    return undefined;
  }
  if (root.kind === "AND") {
    const directLead = findDirectConcept(root, leadSnomedId);
    const eitherOf = findAtLeastGroup(root);
    const leadInsideEither = (eitherOf?.children ?? []).some(
      (c) => c.criterion?.snomed_concept_id === leadSnomedId,
    );
    if (directLead && eitherOf && !leadInsideEither) return root;
    for (const child of root.children ?? []) {
      const hit = findLeadPlusEitherOrSituation(child, leadSnomedId);
      if (hit) return hit;
    }
  }
  return undefined;
}

export function findDemographic(
  node: TreeNode | undefined,
  field: string,
  operator: string,
): TreeNode | undefined {
  if (!node) return undefined;
  if (
    node.kind === "DEMOGRAPHIC" &&
    node.field === field &&
    node.operator === operator
  ) {
    return node;
  }
  for (const child of node.children ?? []) {
    const hit = findDemographic(child, field, operator);
    if (hit) return hit;
  }
  return undefined;
}

export function findDirectConcept(
  node: TreeNode | undefined,
  snomedId: string,
): TreeNode | undefined {
  if (!node) return undefined;
  return (node.children ?? []).find(
    (c) => c.kind === "CONCEPT" && c.criterion?.snomed_concept_id === snomedId,
  );
}

export function findAtLeastGroup(
  node: TreeNode | undefined,
): TreeNode | undefined {
  if (!node) return undefined;
  if (node.kind === "AT_LEAST") return node;
  for (const child of node.children ?? []) {
    const hit = findAtLeastGroup(child);
    if (hit) return hit;
  }
  return undefined;
}
