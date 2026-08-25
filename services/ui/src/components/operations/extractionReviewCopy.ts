/**
 * Plain-English copy for the paused extraction review.
 *
 * Atlas trace: DI-4A012A59 / DO-E7824FED
 */

export const PAUSE_REASON_LABELS: Record<string, string> = {
  low_document_quality: "The letter scored poorly for extraction",
  missing_entities: "No facts were found on the letter",
  few_shot_ood: "This letter layout is unlike the training examples",
  unknown_form_template: "This form is not one we have seen before",
  low_rule_coverage: "Too many form lines could not be read",
  wrapper_admin_only: "The letter looks like a wrapper, not the clinical form",
  manual_pause: "Someone paused this for a check",
};

export function pauseReasonTokens(raw: string): string[] {
  return raw
    .split(",")
    .map((part) => part.trim().replace(/\s+/g, "_").toLowerCase())
    .filter(Boolean);
}

export function pauseReasonLabel(token: string): string {
  const key = token.replace(/\s+/g, "_").toLowerCase();
  return PAUSE_REASON_LABELS[key] ?? token.replace(/_/g, " ");
}

export function pauseReasonLabels(
  raw: string,
  extra: string[] = [],
): string[] {
  const tokens = [
    ...pauseReasonTokens(raw),
    ...extra.map((item) => item.trim().replace(/\s+/g, "_").toLowerCase()),
  ];
  const seen = new Set<string>();
  const labels: string[] = [];
  for (const token of tokens) {
    if (!token || seen.has(token)) continue;
    seen.add(token);
    labels.push(pauseReasonLabel(token));
  }
  return labels;
}

export const EMPTY_LETTER_COPY =
  "We could not load the letter. Check the draft facts on the right, then try again if needed.";

export const QUALITY_SCORE_HINT =
  "This score says how well the letter matched known forms. A low score means check the facts before the run continues.";

export const CANCEL_TASK_TITLE = "Remove this paused extraction?";

export const CANCEL_TASK_BODY =
  "This task leaves your list. We will not teach the system from it. We will not unlock the letter. Use this when the task is a duplicate or was created by mistake.";

export const CANCEL_TASK_REASONS = [
  { value: "duplicate", label: "This is a duplicate" },
  { value: "created_in_error", label: "Created by mistake" },
  { value: "no_longer_needed", label: "No longer needed" },
] as const;
