/**
 * Pure algorithm: analyse candidate encounter rows and recommend the
 * filter settings that produce the clearest case-finding set.
 *
 * No side-effects, no React imports -- safe to unit-test in isolation.
 */
import type { EncounterListItem } from "@/lib/missionControlApi";

export type MatchType = "keyword" | "hybrid" | "semantic" | "none";

export interface TrainingRecommendation {
  minCombinedScore: number;
  enableDedup: boolean;
  dedupThreshold: number;
  expectedCount: number;
  keptCount: number;
  removedCount: number;
  byMatchType: Record<MatchType, number>;
  qualityScore: number;
  coverageScore: number;
  overallScore: number;
  bullets: string[];
  warnings: string[];
}

// Thresholds to evaluate, ordered from permissive to strict.
// Starts at 0.10 so the advisor can recommend a very open cut if quality
// is already high across the board.
const THRESHOLDS = [
  0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8,
] as const;

const MIN_EXAMPLES = 10;
const IDEAL_MIN = 30;
const IDEAL_MAX = 200;
const RESULT_CAP = 1200;
const DEDUP_THRESHOLD = 0.99;

function volumeMultiplier(n: number): number {
  if (n < MIN_EXAMPLES) return 0;
  if (n < IDEAL_MIN) return 0.6 + 0.4 * (n / IDEAL_MIN);
  if (n <= IDEAL_MAX) return 1.0;
  return 0.85;
}

function selectRows(rows: EncounterListItem[], threshold: number) {
  return rows.filter((r) => (r.score ?? 0) >= threshold);
}

function coverage(selected: EncounterListItem[]): number {
  if (selected.length === 0) return 0;
  const nonKeyword = selected.filter(
    (r) => r.match_type !== "keyword" && r.match_type !== "none"
  ).length;
  return nonKeyword / selected.length;
}

function meanQuality(selected: EncounterListItem[]): number {
  if (selected.length === 0) return 0;
  return selected.reduce((s, r) => s + (r.score ?? 0), 0) / selected.length;
}

function byType(selected: EncounterListItem[]): Record<MatchType, number> {
  const counts: Record<MatchType, number> = {
    keyword: 0,
    hybrid: 0,
    semantic: 0,
    none: 0,
  };
  for (const r of selected) counts[r.match_type ?? "none"]++;
  return counts;
}

function makeBullets(
  threshold: number,
  coverageRatio: number,
  n: number,
  types: Record<MatchType, number>
): string[] {
  const pct = Math.round(threshold * 100);
  const bullets: string[] = [
    `Set quality to ${pct}%. This keeps clear matches.`,
  ];
  const varied = (types.semantic ?? 0) + (types.hybrid ?? 0);
  if (varied > 0) {
    bullets.push(
      `${varied} results match by meaning (for example: SOB and breathlessness).`
    );
  }
  if (coverageRatio < 0.15 && n > 0) {
    bullets.push("Most results are exact word matches, so coverage is narrow.");
  } else if (coverageRatio >= 0.4) {
    bullets.push("You have a good mix of exact words and similar meaning words.");
  }
  bullets.push(
    "Duplicate clean-up is set to strict. It removes only near-identical copies."
  );
  if (n >= IDEAL_MIN && n <= IDEAL_MAX) {
    bullets.push(`${n} results is a good number to review.`);
  }
  return bullets;
}

function makeWarnings(
  n: number,
  coverageRatio: number,
  expectedCount: number
): string[] {
  const warnings: string[] = [];
  if (n < MIN_EXAMPLES) {
    warnings.push(
      `Only ${n} results found. Lower quality or widen the date range.`
    );
  }
  if (n > 0 && coverageRatio === 0) {
    warnings.push("All results are exact word hits. Add more meaning matches for better coverage.");
  }
  if (expectedCount >= RESULT_CAP) {
    warnings.push(
      "Result cap reached (1,200). Narrow the date range to see all results."
    );
  }
  return warnings;
}

export function computeRecommendation(
  rows: EncounterListItem[]
): TrainingRecommendation {
  let bestThreshold = 0.4;
  let bestCombined = -1;

  for (const t of THRESHOLDS) {
    const sel = selectRows(rows, t);
    const n = sel.length;
    if (n < MIN_EXAMPLES) continue;

    const q = meanQuality(sel);
    const v = coverage(sel);
    const volScore = Math.min(n, IDEAL_MAX) / IDEAL_MAX;
    const combined = (0.45 * q + 0.30 * v + 0.25 * volScore) * volumeMultiplier(n);

    if (combined > bestCombined) {
      bestCombined = combined;
      bestThreshold = t;
    }
  }

  const kept = selectRows(rows, bestThreshold);
  const n = kept.length;
  const v = coverage(kept);
  const q = meanQuality(kept);
  const types = byType(kept);

  return {
    minCombinedScore: bestThreshold,
    enableDedup: true,
    dedupThreshold: DEDUP_THRESHOLD,
    expectedCount: rows.length,
    keptCount: n,
    removedCount: rows.length - n,
    byMatchType: types,
    qualityScore: Math.round(q * 10 * 10) / 10,
    coverageScore: Math.round(v * 10 * 10) / 10,
    overallScore: Math.round(Math.min(bestCombined, 1) * 10 * 10) / 10,
    bullets: makeBullets(bestThreshold, v, n, types),
    warnings: makeWarnings(n, v, rows.length),
  };
}
