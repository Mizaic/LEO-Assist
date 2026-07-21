/**
 * Selection helpers for RecommendationPickerDialog.
 *
 * Atlas: DI-EB716E68 (attach mode for Validation Lab)
 */

import {
  defaultSelectedForTriage,
  triageRecommendation,
} from "@/lib/recommendationTriage";

export interface RecRuleRef {
  rule_id: string;
  status: string;
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
