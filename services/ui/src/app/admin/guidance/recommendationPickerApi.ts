/**
 * Fetch helpers for RecommendationPickerDialog.
 *
 * Atlas: DI-EB716E68
 *
 * Atlas trace:
 *   DO: DO-2C03CA0E
 *   DI: DI-3F771AFB
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-2C03CA0E")
 */
import type { Rule } from "./ruleReviewTypes";
import type { ChapterEntry } from "./RecommendationPickerRows";

export interface SubgraphData {
  guideline_id: string;
  guideline_title: string;
  chapters: ChapterEntry[];
}

export async function fetchSubgraph(
  code: string,
  source: "nice_syndication_api" | "local_guideline",
): Promise<SubgraphData> {
  const base = source === "local_guideline" ? "/api/guidance/local" : "/api/nice";
  const r = await fetch(`${base}/${encodeURIComponent(code)}/subgraph`);
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

export async function fetchCompiledRuleIds(): Promise<Set<string>> {
  try {
    const r = await fetch(
      "/api/terminology/guidelines/bitmap/status?scope_type=global&scope_id=default",
    );
    if (!r.ok) return new Set();
    const j = (await r.json()) as { rule_ids?: string[] };
    return new Set((j.rule_ids || []).filter(Boolean));
  } catch {
    // Bitmap membership is optional for attach UX; keep picker usable.
    return new Set();
  }
}

export async function startGenerateJob(
  guidelineId: string,
  recIds: string[],
): Promise<string> {
  const r = await fetch("/api/guidance/rules/generate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ guideline_id: guidelineId, recommendation_ids: recIds }),
  });
  if (!r.ok) {
    const b = await r.json().catch(() => ({ detail: r.statusText }));
    throw new Error((b as { detail?: string }).detail ?? r.statusText);
  }
  return ((await r.json()) as { job_id: string }).job_id;
}

export async function pollGenerateJob(
  jobId: string,
): Promise<"running" | "done" | "error"> {
  const r = await fetch(`/api/guidance/rules/generate/${jobId}`);
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  const j = (await r.json()) as { status: string };
  return j.status as "running" | "done" | "error";
}

export async function createBlankRule(recId: string): Promise<Rule> {
  const r = await fetch("/api/guidance/rules/create-blank", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ rec_id: recId }),
  });
  if (!r.ok) {
    const b = await r.json().catch(() => ({ detail: r.statusText }));
    throw new Error((b as { detail?: string }).detail ?? r.statusText);
  }
  const data = (await r.json()) as { rule: Rule };
  return data.rule;
}
