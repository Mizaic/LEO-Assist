/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-2C03CA0E
 *   DI: DI-3F771AFB
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-2C03CA0E")
 */
import type {
  ExtractionScenarioRow,
  ScenarioListResponse,
} from "@/app/admin/extraction-scenarios/types";

export interface ScenarioRunChildStage {
  step_id: string;
  event_type: string;
  status: string;
  errors: string[];
  output?: Record<string, unknown>;
  completed_at?: string | null;
}

export interface ReferralAssessmentCompletedEvent {
  event_type: "referral_assessment_completed" | string;
  run_id: string;
  ubrn?: string;
  assessment_id?: string;
}

export interface ScenarioRunChild {
  case_id: string;
  run_id: string;
  status: string;
  patient_id?: string | null;
  encounter_id?: string | null;
  assessment_id?: string | null;
  completed_at?: string | null;
  completion_event?: ReferralAssessmentCompletedEvent | null;
  stages?: ScenarioRunChildStage[];
  assessment?: {
    id?: string;
    status?: string;
    situation?: string;
    background?: string;
    background_parts?: Array<Record<string, unknown>>;
    assessment?: string;
    recommendation?: string;
    content?: string;
    completeness_result_json?: string | null;
  } | null;
}

export interface ScenarioRunSummary {
  run_id: string;
  status: "queued" | "running" | "completed" | "failed" | string;
  case_ids: string[];
  child_runs: Record<string, string>;
  guideline_id: string;
  completeness_domain: string;
  completeness_subdomain: string;
  triggered_by?: string | null;
  triggered_at?: string | null;
  completed_at?: string | null;
  completed_count: number;
  failed_count: number;
  running_count: number;
  case_count: number;
  children?: ScenarioRunChild[];
}

export interface ScenarioRunRequest {
  case_ids: string[];
  guideline_id: string;
  completeness_domain: string;
  completeness_subdomain: string;
}

function headers(): HeadersInit {
  return {
    "Content-Type": "application/json",
    "X-Requested-With": "XMLHttpRequest",
  };
}

export async function listScenarioOptions(params?: {
  status?: string;
  search?: string;
}): Promise<ScenarioListResponse> {
  const qs = new URLSearchParams();
  if (params?.status && params.status !== "all") qs.set("status", params.status);
  if (params?.search) qs.set("search", params.search);
  const res = await fetch(`/api/sbar/scenario-runs/scenarios?${qs}`, {
    headers: headers(),
  });
  if (!res.ok) throw new Error(await res.text());
  const data = await res.json();
  return {
    pass_threshold: 0,
    ...data,
    cases: (data.cases || []) as ExtractionScenarioRow[],
  };
}

export async function startScenarioRun(
  payload: ScenarioRunRequest,
): Promise<{ run_id: string; child_runs: Record<string, string> }> {
  const res = await fetch("/api/sbar/scenario-runs", {
    method: "POST",
    headers: headers(),
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function listScenarioRuns(): Promise<{ runs: ScenarioRunSummary[] }> {
  const res = await fetch("/api/sbar/scenario-runs", { headers: headers() });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getScenarioRun(runId: string): Promise<ScenarioRunSummary> {
  const res = await fetch(`/api/sbar/scenario-runs/${encodeURIComponent(runId)}`, {
    headers: headers(),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}
