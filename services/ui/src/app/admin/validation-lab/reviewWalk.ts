/**
 * Sequential Validation Lab stage walk.
 *
 * Atlas: DI-C953EF73 / DO-4FD76836 / VT-F0A6B9F4
 *
 * Atlas trace:
 *   DO: DO-158BE606
 *   DI: DI-2289D095
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-158BE606")
 */
export function firstStepId(spans: Array<{ step_id: string }>): string {
  return spans[0]?.step_id || "";
}

export function stepIndex(
  spans: Array<{ step_id: string }>,
  stepId: string,
): number {
  return spans.findIndex((row) => row.step_id === stepId);
}

export function unlockedIndex(
  spans: Array<{ step_id: string }>,
  reviewed: Iterable<string>,
): number {
  const done = new Set(reviewed);
  let index = 0;
  while (index < spans.length && done.has(spans[index].step_id)) {
    index += 1;
  }
  return index;
}

export function canOpenStep(
  spans: Array<{ step_id: string }>,
  stepId: string,
  reviewed: Iterable<string>,
): boolean {
  const index = stepIndex(spans, stepId);
  if (index < 0) return false;
  return index <= unlockedIndex(spans, reviewed);
}

export function nextStepId(
  spans: Array<{ step_id: string }>,
  stepId: string,
): string {
  const index = stepIndex(spans, stepId);
  if (index < 0 || index >= spans.length - 1) return "";
  return spans[index + 1].step_id;
}

export function walkComplete(
  spans: Array<{ step_id: string }>,
  reviewed: Iterable<string>,
): boolean {
  return spans.length > 0 && unlockedIndex(spans, reviewed) >= spans.length;
}

export function isCodingStep(stepId: string): boolean {
  const id = stepId.toLowerCase();
  return id.includes("terminology") || id.includes("coding");
}

export function isFirstFactStep(stepId: string): boolean {
  const id = stepId.toLowerCase();
  return id.includes("extract") && !id.includes("check");
}
