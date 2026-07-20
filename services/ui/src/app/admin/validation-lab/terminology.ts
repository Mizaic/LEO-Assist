/**
 * Shared SNOMED search helper for the Validation Lab wizard.
 *
 * Atlas: DI-724CD8A5
 */

export interface TerminologyHit {
  snomed_concept_id: string;
  term: string;
  read_code?: string;
  semantic_tag?: string;
  module_id?: string;
  score?: number;
  from_surface_form?: boolean;
}

export async function searchTerminology(
  q: string,
  limit = 15,
): Promise<TerminologyHit[]> {
  const trimmed = q.trim();
  if (trimmed.length < 2) return [];
  const params = new URLSearchParams({ q: trimmed, limit: String(limit) });
  const resp = await fetch(`/api/terminology/search?${params}`, {
    headers: { "X-Requested-With": "XMLHttpRequest" },
  });
  if (!resp.ok) {
    throw new Error(`Terminology search failed (${resp.status})`);
  }
  const rows = (await resp.json()) as TerminologyHit[];
  return Array.isArray(rows) ? rows : [];
}
