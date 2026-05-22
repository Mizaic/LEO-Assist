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
  workflow_id: string;
  plan_definition_id: string;
  patient_id: string;
  encounter_id: string;
  assessment_id: string | null;
  guideline_id: string | null;
  completeness_domain: string | null;
  completeness_subdomain: string | null;
  status: "completed" | "completed_with_errors" | string;
  errors: string[];
  context: Record<string, unknown>;
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
