/**
 * Collapse live pipeline subgraphs into four clinician phases.
 *
 * Atlas: DI-49BA8E04 / VT-592D30E9
 *
 * Atlas trace:
 *   DO: DO-7B63A6BE
 *   DI: DI-49BA8E04
 *   Risks: R-823853D7
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-7B63A6BE")
 */

import { stepCopyKey } from "./plainStageCopy";

export const CLINICAL_PHASES = ["read", "clean", "code", "decide"] as const;

export type ClinicalPhaseId = (typeof CLINICAL_PHASES)[number];

export const CLINICAL_PHASE_LABEL: Record<ClinicalPhaseId, string> = {
  read: "Read",
  clean: "Clean",
  code: "Code",
  decide: "Decide",
};

const PHASE_BY_COPY_KEY: Record<string, ClinicalPhaseId> = {
  extract: "read",
  extraction: "read",
  post: "clean",
  post_process: "clean",
  "extraction-check": "clean",
  "relation-link": "clean",
  terminology: "code",
  "coding-verify": "code",
  coding: "code",
  snomed_enrichment: "code",
  "snomed-enrich": "code",
  persist: "code",
  "snomed-relation-judge": "code",
  "referral-reason": "decide",
  compliance: "decide",
  completeness: "decide",
  sbar: "decide",
};

export interface PhaseSpan {
  step_id: string;
  status?: string;
}

export function phaseForStepId(
  stepId: string,
  orderedStepIds: string[] = [],
): ClinicalPhaseId | null {
  const key = stepCopyKey(stepId);
  const mapped = phaseFromKey(key, stepId);
  if (mapped !== "clean" || key !== "relation-link") return mapped;
  if (priorPhaseReached(orderedStepIds, stepId, "code")) return "code";
  return "clean";
}

export function stepsInPhase(
  spans: PhaseSpan[],
  phase: ClinicalPhaseId,
): string[] {
  const order = spans.map((span) => span.step_id);
  return spans
    .filter((span) => phaseForStepId(span.step_id, order) === phase)
    .map((span) => span.step_id);
}

const CODE_FACT_KEYS = new Set(["terminology", "coding-verify", "coding"]);

export function phaseSnapshotStepId(
  spans: PhaseSpan[],
  phase: ClinicalPhaseId,
): string | null {
  const order = spans.map((span) => span.step_id);
  const inPhase = spans.filter(
    (span) => phaseForStepId(span.step_id, order) === phase,
  );
  if (!inPhase.length) return null;
  const pool =
    phase === "code" ? codeFactSpans(inPhase) : inPhase;
  const done = pool.filter((span) => span.status === "completed");
  const pick = done.length ? done : pool;
  return pick[pick.length - 1].step_id;
}

function codeFactSpans(spans: PhaseSpan[]): PhaseSpan[] {
  const preferred = spans.filter((span) =>
    CODE_FACT_KEYS.has(stepCopyKey(span.step_id)),
  );
  return preferred.length ? preferred : spans;
}

export function defaultOpenStepId(spans: PhaseSpan[]): string | null {
  return (
    phaseSnapshotStepId(spans, "decide") ||
    spans[spans.length - 1]?.step_id ||
    null
  );
}

export function applyPhaseClick(
  spans: PhaseSpan[],
  phase: ClinicalPhaseId,
): { selectedPhase: ClinicalPhaseId; selectedStepId: string | null } {
  return {
    selectedPhase: phase,
    selectedStepId: phaseSnapshotStepId(spans, phase),
  };
}

export function phaseIndex(phase: ClinicalPhaseId): number {
  return CLINICAL_PHASES.indexOf(phase) + 1;
}

function phaseFromKey(key: string, stepId: string): ClinicalPhaseId | null {
  if (PHASE_BY_COPY_KEY[key]) return PHASE_BY_COPY_KEY[key];
  if (stepId.toLowerCase().includes("quality")) return "decide";
  return null;
}

function priorPhaseReached(
  orderedStepIds: string[],
  stepId: string,
  phase: ClinicalPhaseId,
): boolean {
  const end = orderedStepIds.indexOf(stepId);
  const prior = end === -1 ? orderedStepIds : orderedStepIds.slice(0, end);
  return prior.some((id) => phaseFromKey(stepCopyKey(id), id) === phase);
}
