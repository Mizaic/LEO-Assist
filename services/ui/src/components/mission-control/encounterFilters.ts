import { inMsRange } from "./encounterTextUtils";

// Encounter list filtering helpers used by the Mission Control
// patient detail Encounter text tab. The flat encounter list below
// the histogram is filtered by Coded-only, free-text search, and
// the histogram brush window. The brush is the only spatial filter
// since DI-LEO-AI-213 replaced the scope chips with the histogram
// overlay.
//
// Design Controls: UN-LEO-AI-077, DI-LEO-AI-213, DO-LEO-AI-210,
// R-LEO-AI-174, VT-LEO-AI-205.

export interface FilterableEncounter {
  encounter_id: string;
  date: string;
  text: string | null;
  coded_count: number;
}

export interface CommonFilterArgs {
  codedOnly: boolean;
  search: string;
  timelineRange: { fromMs: number; toMs: number } | null;
}

export function applyCommonFilters<E extends FilterableEncounter>(
  items: E[],
  args: CommonFilterArgs
): E[] {
  const query = args.search.trim().toLowerCase();
  return items.filter((e) => {
    if (args.codedOnly && (e.coded_count ?? 0) <= 0) return false;
    if (query && !(e.text ?? "").toLowerCase().includes(query)) return false;
    if (args.timelineRange) {
      if (!inMsRange(e.date, args.timelineRange.fromMs, args.timelineRange.toMs)) {
        return false;
      }
    }
    return true;
  });
}
