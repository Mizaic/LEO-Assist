/**
 * Validation Lab findings and clinical PipelineRun client.
 *
 * Atlas: DI-562F2C9E / DO-4FD76836
 */

import { formatLabApiError } from "./labApi";
import type { LabRunInspectorSnapshot, LabStageDetail } from "./inspectorTypes";
import type {
  FindingCategory,
  FindingStage,
  FindingStatus,
  ValidationFinding,
} from "./findingTypes";
import { triggerReauth } from "@/lib/api/client";

async function apiJson<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    credentials: "include",
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    ...init,
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    if (res.status === 401) await triggerReauth();
    throw new Error(formatLabApiError(body, res.status));
  }
  return body as T;
}

export interface CreateFindingPayload {
  stage_id: FindingStage;
  category: FindingCategory;
  target?: string;
  note?: string;
  status?: FindingStatus;
}

export function createFinding(
  runId: string,
  payload: CreateFindingPayload,
): Promise<ValidationFinding> {
  return apiJson(
    `/api/validation-lab/runs/${encodeURIComponent(runId)}/findings`,
    { method: "POST", body: JSON.stringify(payload) },
  );
}

export function listRunFindings(runId: string): Promise<ValidationFinding[]> {
  return apiJson(
    `/api/validation-lab/runs/${encodeURIComponent(runId)}/findings`,
  );
}

export function listOpenFindings(): Promise<ValidationFinding[]> {
  return apiJson("/api/validation-lab/findings");
}

export type ClinicalSearchMode = "patient" | "letters";

export interface ClinicalPipelineRun {
  run_id: string;
  status: string;
  created_at: string;
  plan_id: string;
  patient_id: string;
  patient_name: string;
  nhs_number?: string;
  ubrn?: string;
  run_count?: number;
  matched_on?: string;
  snippet?: string;
}

export function listClinicalPipelineRuns(opts?: {
  q?: string;
  mode?: ClinicalSearchMode;
}): Promise<ClinicalPipelineRun[]> {
  const q = (opts?.q || "").trim();
  const mode = opts?.mode === "letters" ? "letters" : "patient";
  if (!q) return apiJson("/api/validation-lab/pipeline-runs");
  return apiJson(
    `/api/validation-lab/pipeline-runs?q=${encodeURIComponent(q)}&mode=${mode}`,
  );
}

export function listClinicalPatients(opts?: {
  q?: string;
}): Promise<ClinicalPipelineRun[]> {
  const q = (opts?.q || "").trim();
  const path = q
    ? `/api/validation-lab/clinical-patients?q=${encodeURIComponent(q)}`
    : "/api/validation-lab/clinical-patients";
  return apiJson(path);
}

export function getPipelineRunInspector(
  runId: string,
): Promise<LabRunInspectorSnapshot> {
  return apiJson(
    `/api/validation-lab/pipeline-runs/${encodeURIComponent(runId)}/inspector`,
  );
}

export function getPipelineRunInspectorStage(
  runId: string,
  stepId: string,
): Promise<LabStageDetail> {
  return apiJson(
    `/api/validation-lab/pipeline-runs/${encodeURIComponent(runId)}/inspector/stages/${encodeURIComponent(stepId)}`,
  );
}

export interface GuidanceRulePickerRow {
  rule_id: string;
  name?: string;
  status?: string;
  recommendation_text?: string;
  chapter_title?: string;
  guideline_title?: string;
  trigger_terms?: string[];
}

export function listGuidanceRules(): Promise<GuidanceRulePickerRow[]> {
  return apiJson("/api/guidance/rule-picker");
}
