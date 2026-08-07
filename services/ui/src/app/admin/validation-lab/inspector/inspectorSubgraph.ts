/**
 * Map durable step ids to pathway probe subgraph ids.
 *
 * Atlas trace:
 *   DO: DO-158BE606
 *   DI: DI-FE423B8D
 */

import type { LabPlanStep, LabTraceSpan } from "../inspectorTypes";

const STEP_SUFFIX_TO_SUBGRAPH: Record<string, string> = {
  extract: "extraction",
  "post-process": "post_processing",
  "relation-link": "relation_linking",
  "extraction-check": "extraction_check",
  terminology: "terminology",
  "coding-verify": "coding_verifier",
  "persist-facts": "persist",
  compliance: "compliance",
  completeness: "quality_check",
  "referral-reason": "referral_reason",
  sbar: "sbar",
};

export function resolveSubgraphId(
  stepId: string,
  planSteps: LabPlanStep[],
  span?: LabTraceSpan | null,
): string {
  const fromSpan = (span?.subgraph_id || "").trim();
  if (fromSpan) return fromSpan;

  const fromPlan = planSteps.find((step) => step.action_id === stepId)?.subgraph_id;
  if (fromPlan) return fromPlan;

  const suffix = (stepId || "")
    .replace(/^act-ref-/, "")
    .replace(/^durable-ref-/, "")
    .trim()
    .toLowerCase();
  return STEP_SUFFIX_TO_SUBGRAPH[suffix] || suffix.replace(/-/g, "_");
}
