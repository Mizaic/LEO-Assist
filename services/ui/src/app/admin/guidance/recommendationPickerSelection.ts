/**
 * Selection helpers for RecommendationPickerDialog.
 *
 * Atlas: DI-EB716E68 (attach mode for Validation Lab)
 *
 * Atlas trace:
 *   DO: DO-2C03CA0E
 *   DI: DI-3F771AFB
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-2C03CA0E")
 */
import {
  defaultSelectedForTriage,
  triageRecommendation,
} from "@/lib/recommendationTriage";

export interface RecRuleRef {
  rule_id: string;
  status: string;
  /** ISO timestamp from subgraph; used to pick the newest rule version. */
  created_at?: string | null;
}

/** Prefer current review status when timestamps are missing or tied. */
const STATUS_RANK: Record<string, number> = {
  active: 4,
  pending_review: 3,
  rejected: 2,
  superseded: 1,
};

/**
 * Pick the most recent rule for a recommendation.
 * Newest created_at wins; ties / missing timestamps use status rank
 * (active > pending_review > rejected > superseded).
 */
export function pickLatestRule<T extends RecRuleRef>(rules: T[]): T | null {
  if (!rules.length) return null;
  return [...rules].sort((a, b) => {
    const aTs = a.created_at ? Date.parse(a.created_at) : NaN;
    const bTs = b.created_at ? Date.parse(b.created_at) : NaN;
    const aOk = Number.isFinite(aTs);
    const bOk = Number.isFinite(bTs);
    if (aOk && bOk && aTs !== bTs) return bTs - aTs;
    if (aOk !== bOk) return aOk ? -1 : 1;
    return (STATUS_RANK[b.status] ?? 0) - (STATUS_RANK[a.status] ?? 0);
  })[0];
}

/**
 * Rule used when attaching a recommendation for scoring:
 * prefer an approved (active) rule, else the most recent version.
 */
export function pickAttachRule<T extends RecRuleRef>(rules: T[]): T | null {
  const approved = rules.find((r) => r.status === "active");
  return approved ?? pickLatestRule(rules);
}

export interface RecEntryLike {
  rec_id: string;
  is_normative: boolean;
  verbatim?: string;
  title?: string;
  rules: RecRuleRef[];
}

export interface ChapterEntryLike {
  recommendations: RecEntryLike[];
}

export type RecMode = "ai" | "hand";

export interface RecSelection {
  checked: boolean;
  mode: RecMode;
}

export type SelectionMap = Record<string, RecSelection>;

/** Initial checkbox state when opening the picker. */
export function buildInitialSelection(
  chapters: ChapterEntryLike[],
  attachMode = false,
): SelectionMap {
  const map: SelectionMap = {};
  for (const ch of chapters) {
    for (const rec of ch.recommendations) {
      if (!rec.is_normative) continue;
      // Validation Lab attach: start empty so the reviewer chooses
      // test targets deliberately.
      if (attachMode) {
        map[rec.rec_id] = { checked: false, mode: "ai" };
        continue;
      }
      // Rules mode: pre-select ruleable recs that do not yet have a rule.
      const bucket = triageRecommendation(rec.verbatim || rec.title || "");
      const ruleable = defaultSelectedForTriage(bucket);
      map[rec.rec_id] = {
        checked: rec.rules.length === 0 && ruleable,
        mode: "ai",
      };
    }
  }
  return map;
}

export function allNormativeRecs<T extends RecEntryLike>(
  chapters: Array<{ recommendations: T[] }>,
): T[] {
  return chapters.flatMap((ch) =>
    ch.recommendations.filter((r) => r.is_normative),
  );
}
