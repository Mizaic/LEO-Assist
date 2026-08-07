/**
 * Validation Lab HTTP client -- one production-faithful test patient:
 * demographics -> PMH -> encounters -> referral -> real pipeline run.
 *
 * Atlas: DO-3A70C3DD / DI-724CD8A5 / DI-2289D095 / DI-9138BAC9
 *
 * Atlas trace:
 *   DO: DO-158BE606
 *   DI: DI-2289D095
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-158BE606")
 */
import { triggerReauth } from "@/lib/api/client";

import type { LabRunInspectorSnapshot, LabStageDetail } from "./inspectorTypes";

export type PmhCategory = "condition" | "medication" | "allergy";
export type LabCaseType = "referral" | "ag";
export type LabScenarioType = "generic" | "spo_ag" | "ras_referral";

export interface AgTurnInput {
  category: "REQUESTER" | "RESPONDER";
  note: string;
  sent_datetime?: string;
  attachment_text?: string;
}

export interface PmhItemInput {
  category: PmhCategory;
  concept_id: string;
  term: string;
}

export interface EncounterInput {
  label: string;
  text: string;
  date: string;
}

export interface ObservationInput {
  observable_id: string;
  value: number;
  unit: string;
  term?: string;
}

export interface CreateCasePayload {
  case_id?: string;
  title: string;
  summary?: string;
  tags?: string[];
  case_type?: LabCaseType;
  scenario_type?: LabScenarioType;
  referral_text?: string;
  plan_id?: string;
  patient_age?: number | null;
  patient_sex?: string | null;
  patient_name?: string;
  nhs_number?: string;
  gp_practice_name?: string;
  gp_encounter?: EncounterInput;
  reason_for_submission?: string;
  verbalisation_seed?: string;
  pmh: PmhItemInput[];
  encounters: EncounterInput[];
  gold?: Record<string, unknown>;
  ag_thread?: AgTurnInput[];
  ag_response_text?: string;
  ag_request_attachments?: string[];
  ag_ubrn?: string;
  ethnicity_concept_id?: string | null;
  ethnicity_term?: string | null;
  performance_status_grade?: number | null;
  comorbidity_band?: string | null;
  core20_decile?: number | null;
  plus_group?: string | null;
  observations?: ObservationInput[];
}

export interface BrainstormRecommendation {
  recId: string;
  guidelineCode?: string;
  verbatim?: string;
  recTitle?: string;
  ruleId?: string;
  ruleStatus?: string;
}

export interface BrainstormQuestionOption {
  id: string;
  label: string;
  recommended?: boolean;
}

export interface BrainstormQuestion {
  id: string;
  question: string;
  allowMultiple?: boolean;
  maxSelections?: number;
  options: BrainstormQuestionOption[];
}

export interface BrainstormRequest {
  phase: "understand" | "clarify" | "propose_variants";
  scenario_text?: string;
  recommendations?: BrainstormRecommendation[];
  answers?: Record<string, string | string[]>;
  round?: number;
  include_control?: boolean;
}

export interface BrainstormResponse {
  needs_clarification?: boolean;
  questions?: BrainstormQuestion[];
  guidance_message?: string;
  assistant_message?: string;
  variants?: Array<Record<string, unknown>>;
  recommendations?: BrainstormRecommendation[];
  skipped_recommendations?: BrainstormRecommendation[];
  tool_traces?: Array<Record<string, unknown>>;
}

export interface PhaseOutput {
  phase_id: string;
  status: string;
  headline?: string;
  pipeline_enqueued?: boolean;
  pipeline_error?: string;
}

/** Live durable pipeline stage from :PipelineStageRun (DI-2289D095). */
export interface StageProgress {
  step_id: string;
  event_type?: string;
  status: string;
  /** lease_owner while running, else completed_by after finish. */
  worker_id?: string;
  started_at?: string;
  completed_at?: string;
}

export interface LabRunLlmUsage {
  input_tokens?: number;
  output_tokens?: number;
  cached_input_tokens?: number;
  total_tokens?: number;
  llm_calls?: number;
  cost_usd?: number;
  latency_ms?: number;
  model_id?: string;
  model_provider?: string;
}

export interface RunOutputs {
  snomed_codes?: string[];
  completeness?: Record<string, unknown>;
  matching_rules?: string[];
  sbar_assessment_id?: string;
  sbar_markdown?: string;
  phase_outputs?: PhaseOutput[];
  llm_usage?: LabRunLlmUsage;
}

export interface LabRun {
  id: string;
  persist_mode: "production" | "dry_run";
  status: string;
  outputs?: RunOutputs;
  stage_progress?: StageProgress[];
  error_message?: string;
  /** Compiled guideline bitmap version this run evaluated against. */
  ruleset_version?: string | null;
  llm_cost_usd?: number;
  llm_total_tokens?: number;
  llm_calls?: number;
}

export interface LabCase {
  id: string;
  title: string;
  summary?: string;
  tags?: string[];
  referral_preview?: string;
  case_type?: LabCaseType;
  scenario_type?: LabScenarioType;
  referral_text?: string;
  patient_id?: string;
  encounter_id?: string;
  referral_id?: string;
  document_reference_id?: string;
  communication_request_id?: string;
  ubrn?: string;
  chunk_ids?: string[];
  background_encounter_ids?: string[];
  plan_id?: string;
  pmh?: Array<{ category: PmhCategory; concept_id: string; term: string }>;
  encounters?: EncounterInput[];
  ag_thread?: AgTurnInput[];
  ag_response_text?: string;
  gold?: RunOutputs;
  runs?: LabRun[];
  has_gold?: boolean;
  latest_run_id?: string | null;
  latest_run_status?: string | null;
  latest_run_ruleset_version?: string | null;
  latest_llm_cost_usd?: number | null;
  latest_llm_total_tokens?: number | null;
  latest_llm_calls?: number | null;
  created_at?: string;
  updated_at?: string;
}

async function apiJson<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    credentials: "include",
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    ...init,
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    if (res.status === 401) await triggerReauth();
    throw new Error(
      typeof body.detail === "string" ? body.detail : `Request failed (${res.status})`,
    );
  }
  return body as T;
}

export function listCases(): Promise<LabCase[]> {
  return apiJson<LabCase[]>("/api/validation-lab/cases");
}

export function getCase(caseId: string): Promise<LabCase> {
  return apiJson<LabCase>(`/api/validation-lab/cases/${encodeURIComponent(caseId)}`);
}

export function createCase(payload: CreateCasePayload): Promise<LabCase> {
  return apiJson<LabCase>("/api/validation-lab/cases", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateCase(
  caseId: string,
  patch: {
    title?: string;
    referral_text?: string;
    plan_id?: string;
    gold?: Record<string, unknown>;
  },
): Promise<LabCase> {
  return apiJson<LabCase>(
    `/api/validation-lab/cases/${encodeURIComponent(caseId)}`,
    {
      method: "PATCH",
      body: JSON.stringify(patch),
    },
  );
}

export function deleteCase(
  caseId: string,
): Promise<{ deleted: boolean; case_id: string; patient_id?: string | null }> {
  return apiJson(
    `/api/validation-lab/cases/${encodeURIComponent(caseId)}`,
    { method: "DELETE" },
  );
}

export interface StartRunPayload {
  plan_id: string;
  phase_ids: string[];
  persist_mode: "production" | "dry_run";
  ruleset_version?: string | null;
}

export function startRun(
  caseId: string,
  payload: StartRunPayload,
): Promise<{ run: LabRun; case: LabCase }> {
  return apiJson(`/api/validation-lab/cases/${encodeURIComponent(caseId)}/runs`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getRun(
  caseId: string,
  runId: string,
): Promise<{ run: LabRun; case: LabCase }> {
  return apiJson(
    `/api/validation-lab/cases/${encodeURIComponent(caseId)}/runs/${encodeURIComponent(runId)}`,
  );
}

const TERMINAL_RUN_STATUSES = new Set(["completed", "failed"]);

/** Scale multi-case poll window with batch size (min 10m, max 45m). */
export function batchPollTimeoutMs(caseCount: number): number {
  const perCaseMs = 90_000;
  const floorMs = 600_000;
  const ceilingMs = 2_700_000;
  return Math.min(ceilingMs, Math.max(floorMs, caseCount * perCaseMs));
}

/** Single durable referral runs can take 20-40 minutes; do not stop polling at 2m. */
export const SINGLE_LAB_RUN_POLL_TIMEOUT_MS = 2_700_000;

/** Poll GET .../runs/{run_id} until the real pipeline reaches a terminal
 * status, or `timeoutMs` elapses. Never fabricates a result. */
export async function pollRunUntilTerminal(
  caseId: string,
  runId: string,
  opts: { intervalMs?: number; timeoutMs?: number } = {},
): Promise<LabRun> {
  const intervalMs = opts.intervalMs ?? 2000;
  const timeoutMs = opts.timeoutMs ?? SINGLE_LAB_RUN_POLL_TIMEOUT_MS;
  const deadline = Date.now() + timeoutMs;
  for (;;) {
    const packed = await getRun(caseId, runId);
    if (TERMINAL_RUN_STATUSES.has(packed.run.status) || Date.now() > deadline) {
      return packed.run;
    }
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }
}

export function promoteGold(
  caseId: string,
  runId: string,
): Promise<Record<string, unknown>> {
  return apiJson(
    `/api/validation-lab/cases/${encodeURIComponent(caseId)}/runs/${encodeURIComponent(runId)}/promote-gold`,
    { method: "POST" },
  );
}

export function scoreRun(caseId: string, runId: string): Promise<Record<string, unknown>> {
  return apiJson(
    `/api/validation-lab/cases/${encodeURIComponent(caseId)}/runs/${encodeURIComponent(runId)}/score`,
  );
}

export function getRunInspector(
  caseId: string,
  runId: string,
): Promise<LabRunInspectorSnapshot> {
  return apiJson(
    `/api/validation-lab/cases/${encodeURIComponent(caseId)}/runs/${encodeURIComponent(runId)}/inspector`,
  );
}

export function getRunInspectorStage(
  caseId: string,
  runId: string,
  stepId: string,
): Promise<LabStageDetail> {
  return apiJson(
    `/api/validation-lab/cases/${encodeURIComponent(caseId)}/runs/${encodeURIComponent(runId)}/inspector/stages/${encodeURIComponent(stepId)}`,
  );
}

export interface StartAgRunPayload {
  ubrn: string;
  plan_id: string;
  phase_ids?: string[];
  persist_mode?: "production" | "dry_run";
  ruleset_version?: string | null;
  guideline_id?: string | null;
  completeness_domain?: string | null;
  completeness_subdomain?: string | null;
}

export function startAgRun(payload: StartAgRunPayload): Promise<Record<string, unknown>> {
  return apiJson("/api/validation-lab/ag-runs", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export interface PreviewPmhNarrativePayload {
  pmh: PmhItemInput[];
  seed?: string;
}

export interface PreviewPmhNarrativeResult {
  narrative: string;
  terms_used: Array<{ concept_id: string; term: string; source?: string }>;
}

export function previewPmhNarrative(
  payload: PreviewPmhNarrativePayload,
): Promise<PreviewPmhNarrativeResult> {
  return apiJson("/api/validation-lab/preview-pmh-narrative", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function brainstorm(
  payload: BrainstormRequest,
): Promise<BrainstormResponse> {
  return apiJson("/api/validation-lab/brainstorm", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
