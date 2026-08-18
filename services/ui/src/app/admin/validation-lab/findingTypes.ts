/**
 * Validation Lab finding categories and stages.
 *
 * Atlas: DI-C953EF73 / DI-562F2C9E / DO-4FD76836
 *
 * Atlas trace:
 *   DO: DO-158BE606
 *   DI: DI-2289D095
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-158BE606")
 */
export const FINDING_CATEGORIES = [
  {
    id: "extraction",
    label: "Words missed",
    hint: "LEO did not pick this up from the letter.",
  },
  {
    id: "context",
    label: "Present, past, or family",
    hint: "LEO treated this as present, past, or family history wrongly.",
  },
  {
    id: "semantic_tag",
    label: "Wrong kind of fact",
    hint: "LEO tagged this as the wrong kind, for example Other instead of a procedure.",
  },
  {
    id: "guard",
    label: "Cleaning rule",
    hint: "A cleaning rule dropped or kept this wrongly.",
  },
  {
    id: "phrase_mapping",
    label: "Medical code",
    hint: "The matched code is wrong.",
  },
  {
    id: "guideline_rule",
    label: "Guideline rule",
    hint: "The wrong care rule fired, or the right one did not.",
  },
] as const;

export type FindingCategory = (typeof FINDING_CATEGORIES)[number]["id"];

export const FINDING_STAGES = [
  "extract",
  "post",
  "terminology",
  "persist",
  "compliance",
  "sbar",
] as const;

export type FindingStage = (typeof FINDING_STAGES)[number];

export const FINDING_STATUSES = ["open", "routed", "retested", "closed"] as const;
export type FindingStatus = (typeof FINDING_STATUSES)[number];

export interface ValidationFinding {
  id: string;
  run_id: string;
  stage_id: FindingStage | string;
  category: FindingCategory | string;
  target: string;
  note: string;
  status: FindingStatus | string;
  created_at?: string;
}

const STAGE_ALIASES: Record<string, FindingStage> = {
  extract: "extract",
  extraction: "extract",
  "extraction-check": "extract",
  post: "post",
  post_process: "post",
  terminology: "terminology",
  coding: "terminology",
  "coding-verify": "terminology",
  persist: "persist",
  "relation-link": "persist",
  compliance: "compliance",
  completeness: "compliance",
  "referral-reason": "compliance",
  sbar: "sbar",
};

export function stageFromStepId(stepId: string): FindingStage {
  const key = (stepId || "").toLowerCase();
  if (key in STAGE_ALIASES) return STAGE_ALIASES[key];
  for (const [alias, stage] of Object.entries(STAGE_ALIASES)) {
    if (key.includes(alias)) return stage;
  }
  return "extract";
}

export function categoryLabel(id: string): string {
  return FINDING_CATEGORIES.find((c) => c.id === id)?.label || id;
}
