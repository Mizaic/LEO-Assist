/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-5312F884
 *   DI: DI-AA1F5F5B
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-5312F884")
 */
// Pure binning helpers for the encounter timeline scrubber histogram.
//
// Design Controls: UN-LEO-AI-077, DI-LEO-AI-179, DO-LEO-AI-178,
// R-LEO-AI-174, VT-LEO-AI-173.

export type Granularity = "day" | "week" | "month" | "quarter" | "year";

// The scrubber was originally encounter-only. The SBAR background-source
// picker (DI-LEO-AI-232) reuses the same primitive but with a mixed
// encounter + DocumentReference feed, so we keep the original
// ScrubberEncounter / DatedEncounter aliases for back-compat with the
// Mission Control encounter-text drawer (DI-LEO-AI-179, DI-LEO-AI-213).
export interface ScrubberEncounter {
  encounter_id: string;
  date: string;
  text: string | null;
  coded_count: number;
}

export type ScrubberRecord = ScrubberEncounter;

export interface DatedEncounter {
  enc: ScrubberEncounter;
  ts: number;
  isLinked: boolean;
}

export type DatedRecord = DatedEncounter;

export interface TimelineBin {
  startMs: number;
  endMs: number;
  label: string;
  total: number;
  linked: number;
  other: number;
  encounters: DatedEncounter[];
}

const DAY_MS = 86_400_000;

export function pickGranularity(rangeMs: number): Granularity {
  const days = rangeMs / DAY_MS;
  if (days <= 60) return "day";
  if (days <= 180) return "week";
  if (days <= 730) return "month";
  if (days <= 1825) return "quarter";
  return "year";
}

export function toTimestamp(iso: string | null | undefined): number {
  if (!iso) return Number.NaN;
  const t = Date.parse(iso);
  return Number.isFinite(t) ? t : Number.NaN;
}

function startOfWeek(d: Date): Date {
  const out = new Date(d);
  const dow = out.getUTCDay();
  const offset = (dow + 6) % 7;
  out.setUTCDate(out.getUTCDate() - offset);
  out.setUTCHours(0, 0, 0, 0);
  return out;
}

export function binStart(date: Date, gran: Granularity): Date {
  const d = new Date(date);
  d.setUTCHours(0, 0, 0, 0);
  if (gran === "day") return d;
  if (gran === "week") return startOfWeek(d);
  if (gran === "month") return new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), 1));
  if (gran === "quarter") {
    const q = Math.floor(d.getUTCMonth() / 3) * 3;
    return new Date(Date.UTC(d.getUTCFullYear(), q, 1));
  }
  return new Date(Date.UTC(d.getUTCFullYear(), 0, 1));
}

export function binNext(date: Date, gran: Granularity): Date {
  const d = new Date(date);
  if (gran === "day") {
    d.setUTCDate(d.getUTCDate() + 1);
    return d;
  }
  if (gran === "week") {
    d.setUTCDate(d.getUTCDate() + 7);
    return d;
  }
  if (gran === "month") {
    d.setUTCMonth(d.getUTCMonth() + 1);
    return d;
  }
  if (gran === "quarter") {
    d.setUTCMonth(d.getUTCMonth() + 3);
    return d;
  }
  d.setUTCFullYear(d.getUTCFullYear() + 1);
  return d;
}

const MONTHS = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

export function binLabel(date: Date, gran: Granularity): string {
  const yy = String(date.getUTCFullYear()).slice(2);
  const yyyy = String(date.getUTCFullYear());
  if (gran === "day") {
    return `${String(date.getUTCDate()).padStart(2, "0")} ${MONTHS[date.getUTCMonth()]} ${yy}`;
  }
  if (gran === "week") {
    return `Wk ${MONTHS[date.getUTCMonth()]} ${String(date.getUTCDate()).padStart(2, "0")}`;
  }
  if (gran === "month") return `${MONTHS[date.getUTCMonth()]} ${yy}`;
  if (gran === "quarter") {
    const q = Math.floor(date.getUTCMonth() / 3) + 1;
    return `Q${q} ${yyyy}`;
  }
  return yyyy;
}

export function buildBins(
  encounters: DatedEncounter[],
  fromMs: number,
  toMs: number,
  gran: Granularity
): TimelineBin[] {
  if (!Number.isFinite(fromMs) || !Number.isFinite(toMs) || toMs < fromMs) return [];
  const bins: TimelineBin[] = [];
  let cursor = binStart(new Date(fromMs), gran);
  const end = new Date(toMs);
  let safety = 0;
  while (cursor.getTime() <= end.getTime() && safety < 5000) {
    const next = binNext(cursor, gran);
    bins.push({
      startMs: cursor.getTime(),
      endMs: next.getTime(),
      label: binLabel(cursor, gran),
      total: 0,
      linked: 0,
      other: 0,
      encounters: [],
    });
    cursor = next;
    safety += 1;
  }
  if (bins.length === 0) return [];
  for (const row of encounters) {
    if (row.ts < bins[0].startMs || row.ts >= bins[bins.length - 1].endMs) continue;
    const offset = row.ts - bins[0].startMs;
    const span = bins[0].endMs - bins[0].startMs;
    let idx = Math.floor(offset / span);
    if (idx < 0) idx = 0;
    if (idx >= bins.length) idx = bins.length - 1;
    while (idx < bins.length - 1 && row.ts >= bins[idx].endMs) idx += 1;
    while (idx > 0 && row.ts < bins[idx].startMs) idx -= 1;
    const bin = bins[idx];
    bin.total += 1;
    if (row.isLinked) bin.linked += 1;
    else bin.other += 1;
    bin.encounters.push(row);
  }
  for (const bin of bins) {
    bin.encounters.sort((a, b) => a.ts - b.ts);
  }
  return bins;
}

export function buildDated(
  encounters: ScrubberEncounter[],
  linkedEncounterIds: Set<string>
): DatedEncounter[] {
  return encounters
    .map((enc) => ({
      enc,
      ts: toTimestamp(enc.date),
      isLinked: linkedEncounterIds.has(String(enc.encounter_id)),
    }))
    .filter((row) => Number.isFinite(row.ts))
    .sort((a, b) => a.ts - b.ts);
}

export function clampRange(
  fromMs: number,
  toMs: number,
  minMs: number,
  maxMs: number
): { fromMs: number; toMs: number } {
  const lo = Math.max(minMs, Math.min(fromMs, maxMs));
  const hi = Math.max(minMs, Math.min(toMs, maxMs));
  if (hi <= lo) {
    const span = Math.max(DAY_MS, (maxMs - minMs) * 0.05);
    return { fromMs: lo, toMs: Math.min(maxMs, lo + span) };
  }
  return { fromMs: lo, toMs: hi };
}

export function pctBetween(value: number, min: number, max: number): number {
  if (!Number.isFinite(value) || !Number.isFinite(min) || !Number.isFinite(max)) return 50;
  if (max <= min) return 50;
  const raw = ((value - min) / (max - min)) * 100;
  return Math.max(0, Math.min(100, raw));
}
