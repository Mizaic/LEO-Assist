/**
 * Guideline, completeness, and draft facts for the Decide phase.
 *
 * Atlas: DI-49BA8E04 / VT-592D30E9
 *
 * Atlas trace:
 *   DO: DO-7B63A6BE
 *   DI: DI-49BA8E04
 *   Risks: R-823853D7
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-7B63A6BE")
 */

import { phaseForStepId, type PhaseSpan } from "./clinicalPhases";
import { stepCopyKey } from "./plainStageCopy";

const SBAR_KEYS = [
  "situation",
  "background",
  "assessment",
  "recommendation",
] as const;

export interface DecideOutcomeStepIds {
  guideline: string | null;
  completeness: string | null;
  sbar: string | null;
}

export function decideOutcomeStepIds(
  spans: PhaseSpan[],
): DecideOutcomeStepIds {
  const order = spans.map((span) => span.step_id);
  const decide = spans.filter(
    (span) => phaseForStepId(span.step_id, order) === "decide",
  );
  return {
    guideline: lastStepWithKeys(decide, ["compliance"]),
    completeness: lastStepWithKeys(decide, ["completeness", "quality"]),
    sbar: lastStepWithKeys(decide, ["sbar"]),
  };
}

export function sbarIdFromStage(
  output: Record<string, unknown> | null | undefined,
): string | null {
  const rec = asRecord(output);
  const report = asRecord(rec.sbar_report);
  const id = firstStr([
    rec.sbar_assessment_id,
    rec.assessment_id,
    rec.sbar_id,
    report.sbar_assessment_id,
    report.assessment_id,
  ]);
  return id || null;
}

export function sbarMarkdownFromStage(
  output: Record<string, unknown> | null | undefined,
): string {
  const rec = asRecord(output);
  const direct = firstStr([rec.sbar_markdown, rec.markdown]);
  if (direct) return direct;
  const sections = asRecord(rec.sbar_report || rec.sbar_sections);
  const parts: string[] = [];
  for (const key of SBAR_KEYS) {
    const text = String(sections[key] || "").trim();
    if (!text) continue;
    parts.push(`## ${cap(key)}\n\n${text}`);
  }
  return parts.join("\n\n");
}

function lastStepWithKeys(spans: PhaseSpan[], keys: string[]): string | null {
  const match = spans.filter((span) => {
    const copy = stepCopyKey(span.step_id);
    const raw = span.step_id.toLowerCase();
    return keys.some((key) => copy === key || raw.includes(key));
  });
  return match.length ? match[match.length - 1].step_id : null;
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object"
    ? (value as Record<string, unknown>)
    : {};
}

function firstStr(values: unknown[]): string {
  for (const value of values) {
    const text = String(value || "").trim();
    if (text) return text;
  }
  return "";
}

function cap(value: string): string {
  return value ? value[0].toUpperCase() + value.slice(1) : value;
}
