/**
 * Validation Lab HTTP client -- one production-faithful test patient:
 * demographics -> PMH -> encounters -> referral -> real pipeline run.
 *
 * Atlas: DO-3A70C3DD / DI-724CD8A5 / DI-2289D095 / DI-9138BAC9
 */

export type PmhCategory = "condition" | "medication" | "allergy";

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

export interface CreateCasePayload {
  case_id?: string;
  title: string;
  referral_text: string;
  plan_id?: string;
  patient_age?: number | null;
  patient_sex?: string | null;
  patient_name?: string;
  pmh: PmhItemInput[];
  encounters: EncounterInput[];
  gold?: Record<string, unknown>;
}

export interface PhaseOutput {
  phase_id: string;
  status: string;
  headline?: string;
  pipeline_enqueued?: boolean;
  pipeline_error?: string;
}

export interface RunOutputs {
  snomed_codes?: string[];
  completeness?: Record<string, unknown>;
  matching_rules?: string[];
  sbar_assessment_id?: string;
  sbar_markdown?: string;
  phase_outputs?: PhaseOutput[];
}

export interface LabRun {
  id: string;
  persist_mode: "production" | "dry_run";
  status: string;
  outputs?: RunOutputs;
  error_message?: string;
}

export interface LabCase {
  id: string;
  title: string;
  referral_text?: string;
  patient_id?: string;
  encounter_id?: string;
  referral_id?: string;
  document_reference_id?: string;
  chunk_ids?: string[];
  background_encounter_ids?: string[];
  plan_id?: string;
  pmh?: Array<{ category: PmhCategory; concept_id: string; term: string }>;
  encounters?: EncounterInput[];
  gold?: RunOutputs;
  runs?: LabRun[];
}

async function apiJson<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    credentials: "include",
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    ...init,
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
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

/** Poll GET .../runs/{run_id} until the real pipeline reaches a terminal
 * status, or `timeoutMs` elapses. Never fabricates a result. */
export async function pollRunUntilTerminal(
  caseId: string,
  runId: string,
  opts: { intervalMs?: number; timeoutMs?: number } = {},
): Promise<LabRun> {
  const intervalMs = opts.intervalMs ?? 2000;
  const timeoutMs = opts.timeoutMs ?? 120000;
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
