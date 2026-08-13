/**
 * Atlas trace:
 *   DI: DI-6BD7B681
 */

export function termNeedsFix(term?: string, conceptId?: string): boolean {
  const name = (term || "").trim();
  const code = (conceptId || "").trim();
  if (!code) return false;
  if (!name) return true;
  if (name === code) return true;
  return /^\d{6,}$/.test(name);
}

export function draftNeedsTermFix(row: {
  draft_action?: string;
  draft_concept_id?: string;
  draft_concept_term?: string;
}): boolean {
  if (row.draft_action !== "map") return false;
  return termNeedsFix(row.draft_concept_term, row.draft_concept_id);
}
