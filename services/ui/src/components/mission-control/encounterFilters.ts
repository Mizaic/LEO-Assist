/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-5312F884  (Mission Control UI implementation)
 *   DO: DO-90004103  (Multi-term chip search in EncounterTextTab)
 *   DI: DI-AA1F5F5B
 *   DI: DI-B12A48EA  (Multi-term chip search with AND logic)
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-90004103")
 */
import { inMsRange } from "./encounterTextUtils";
import { expandSearchTerms, hasAnyExpandedHit } from "./encounterRelevance";

// Encounter list filtering helpers used by the Mission Control
// patient detail Encounter text tab. The flat encounter list below
// the histogram is filtered by Coded-only, free-text search, and
// the histogram brush window. The brush is the only spatial filter
// since DI-LEO-AI-213 replaced the scope chips with the histogram
// overlay.
//
// As of DI-LEO-AI-520 the free-text search delegates to
// `expandSearchTerms` so the drawer matches the same typo and
// synonym vocabulary as the host /care/encounters search (a query
// for "lump" also surfaces "mass", "swelling", "nodule", etc).
//
// Design Controls: UN-LEO-AI-077, UN-LEO-AI-096, DI-LEO-AI-213,
// DI-LEO-AI-520, DO-LEO-AI-210, R-LEO-AI-174, VT-LEO-AI-205,
// VT-LEO-AI-519.

export interface FilterableEncounter {
  encounter_id: string;
  date: string;
  text: string | null;
  coded_count: number;
}

export interface CommonFilterArgs {
  codedOnly: boolean;
  linkedOnly?: boolean;
  linkedEncounterIds?: Set<string>;
  /** Legacy single-string search path (BackgroundSourcePicker). */
  search?: string;
  /**
   * Multi-term chip path (EncounterTextTab -- DI-B12A48EA).
   * When present and non-empty, takes precedence over `search`.
   * Encounter must match ALL chips (AND logic); each chip is
   * independently expanded via the typo/synonym vocabulary.
   */
  searchTerms?: string[];
  timelineRange: { fromMs: number; toMs: number } | null;
}

export function applyCommonFilters<E extends FilterableEncounter>(
  items: E[],
  args: CommonFilterArgs
): E[] {
  // Multi-chip path takes precedence; fall back to the legacy
  // single-string path so BackgroundSourcePicker is unaffected.
  const chips: string[] =
    args.searchTerms && args.searchTerms.length > 0
      ? args.searchTerms
      : args.search
      ? [args.search]
      : [];

  return items.filter((e) => {
    if (args.codedOnly && (e.coded_count ?? 0) <= 0) return false;
    if (
      args.linkedOnly &&
      !args.linkedEncounterIds?.has(String(e.encounter_id))
    ) {
      return false;
    }
    for (const chip of chips) {
      const expandedTerms = expandSearchTerms(chip);
      if (expandedTerms.length && !hasAnyExpandedHit(e.text, expandedTerms)) {
        return false;
      }
    }
    if (args.timelineRange) {
      if (!inMsRange(e.date, args.timelineRange.fromMs, args.timelineRange.toMs)) {
        return false;
      }
    }
    return true;
  });
}
