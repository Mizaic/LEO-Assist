import { inMsRange, inRange } from "./encounterTextUtils";

// Encounter list filtering helpers used by the Mission Control
// patient detail Encounter text tab. Pulled out so EncounterTextTab
// can stay under the 500 LOC ceiling and so the timeline-driven
// filter has a single source of truth.
//
// Design Controls: UN-LEO-AI-077, DI-LEO-AI-179, DO-LEO-AI-178,
// R-LEO-AI-174, VT-LEO-AI-173.

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

export interface SplitArgs<E> {
  encounters: E[];
  linkedEncounterIds: Set<string>;
  episodeFrom: string | null;
  episodeTo: string | null;
}

export interface EncounterSplit<E> {
  linked: E[];
  windowOnly: E[];
  other: E[];
}

export function splitEncounters<E extends FilterableEncounter>(
  args: SplitArgs<E>
): EncounterSplit<E> {
  const { encounters, linkedEncounterIds, episodeFrom, episodeTo } = args;
  const linked: E[] = [];
  const windowOnly: E[] = [];
  const other: E[] = [];
  for (const e of encounters) {
    const id = String(e.encounter_id);
    if (linkedEncounterIds.has(id)) {
      linked.push(e);
      continue;
    }
    if (inRange(String(e.date).slice(0, 10), episodeFrom, episodeTo)) {
      windowOnly.push(e);
    } else {
      other.push(e);
    }
  }
  return { linked, windowOnly, other };
}
