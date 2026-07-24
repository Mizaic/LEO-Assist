/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DI: DI-42246DA7
 *   DO: DO-F8C56339
 *   Look up via: get_design_control(dc_type="design-input", dc_id="DI-42246DA7")
 */

/**
 * Shared fetch for "what codes does depth N include under this seed?"
 * Used by SeedDescendantsList (expanded panel) and DepthInclusionTooltip
 * (hover preview) so both stay on the same terminology endpoint.
 */
import { useEffect, useState } from "react";

export interface ConceptDescendantRow {
  snomed_concept_id: string;
  term?: string;
  preferred_term?: string;
  semantic_tag?: string;
}

export function descendantDisplayTerm(row: ConceptDescendantRow): string {
  return row.preferred_term || row.term || `code ${row.snomed_concept_id}`;
}

const HARD_PREVIEW_LIMIT = 200;

export function useConceptDescendants(
  conceptId: string,
  depth: number,
  enabled: boolean,
): {
  loading: boolean;
  error: string | null;
  rows: ConceptDescendantRow[] | null;
} {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [rows, setRows] = useState<ConceptDescendantRow[] | null>(null);

  const clampedDepth = Math.min(5, Math.max(1, Math.floor(depth) || 1));

  useEffect(() => {
    if (!enabled || !conceptId) {
      return;
    }
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const res = await fetch(
          `/api/terminology/concepts/${encodeURIComponent(conceptId)}/descendants?depth=${clampedDepth}&limit=${HARD_PREVIEW_LIMIT}`,
        );
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const body = (await res.json()) as ConceptDescendantRow[];
        if (!cancelled) setRows(Array.isArray(body) ? body : []);
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : "Could not load codes");
          setRows([]);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [enabled, conceptId, clampedDepth]);

  return { loading, error, rows };
}

export const DESCENDANTS_PREVIEW_LIMIT = HARD_PREVIEW_LIMIT;
