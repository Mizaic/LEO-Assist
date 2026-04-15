/**
 * API client for Pathway Explorer research endpoints.
 * Uses the backend proxy (session cookie auth).
 */
import { triggerReauth } from "@/lib/api/client";

function resolveApiBase(): string {
  if (typeof window !== "undefined") return window.location.origin;
  return (
    process.env.INTERNAL_API_BASE || "http://localhost:8000"
  ).replace(/\/+$/, "");
}

const RESEARCH_BASE = `${resolveApiBase()}/api/proxy/analytics/research`;

async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...init,
    credentials: "include" as RequestCredentials,
    headers: {
      "X-Requested-With": "XMLHttpRequest",
      ...(init?.headers ?? {}),
    },
  });
  if (!res.ok) {
    if (res.status === 401) await triggerReauth();
    const err = await res.json().catch(() => ({}));
    throw new Error(
      (err as { detail?: string }).detail || `Request failed (${res.status})`
    );
  }
  return res.json();
}

// -- Types ------------------------------------------------------------------

export type DetailLevel = "summary" | "detailed" | "everything";
export type PersonaLens = "patients" | "pathways" | "capacity";

export interface RunRequest {
  area: string;
  period: string;
  detail: DetailLevel;
  patient_id?: string;
  confidence_min?: number;
  context_filter?: "current" | "all";
}

export interface CoverageInfo {
  patient_count: number;
  practice_count: number;
  confidence: "low" | "moderate" | "high";
  confidence_note: string;
}

export interface NextStep {
  label: string;
  target: string;
}

export interface RunResult {
  mission_id: string;
  headline: string;
  items: Record<string, unknown>[];
  total_count: number;
  coverage: CoverageInfo;
  method_plain: string;
  method_technical: string;
  next_steps: NextStep[];
  detail_level: DetailLevel;
  data_available: boolean;
  unavailable_reason?: string;
  error?: string;
}

export interface MissionRun {
  run_id: string;
  mission_id: string;
  status: "queued" | "running" | "done" | "failed";
  created_at: string;
  result?: RunResult;
}

export interface MissionDescription {
  id: string;
  group: string;
  group_title: string;
  group_subtitle: string;
  tier: 1 | 2 | 3;
  layer: "A" | "B";
  data_gated: boolean;
  data_available: boolean;
  titles: Record<PersonaLens, string>;
  descriptions: Record<PersonaLens, string>;
}

export interface MissionCatalogueResponse {
  missions: MissionDescription[];
  referral_data_available: boolean;
}

export interface ProjectionStatus {
  name: string;
  exists: boolean;
  node_count: number;
  relationship_count: number;
  layer: "A" | "B";
  data_available: boolean;
  unavailable_reason?: string;
  error?: string;
}

export interface ProjectionSummary {
  projections: ProjectionStatus[];
  referral_data_available: boolean;
  referral_count: number;
}

// -- Mission catalogue -------------------------------------------------------

export async function fetchMissions(): Promise<MissionCatalogueResponse> {
  return fetchJson<MissionCatalogueResponse>(`${RESEARCH_BASE}/missions`);
}

// -- Mission runs ------------------------------------------------------------

export async function startMissionRun(
  missionId: string,
  body: RunRequest
): Promise<MissionRun> {
  return fetchJson<MissionRun>(`${RESEARCH_BASE}/missions/${missionId}/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export async function pollMissionRun(
  missionId: string,
  runId: string
): Promise<MissionRun> {
  return fetchJson<MissionRun>(
    `${RESEARCH_BASE}/missions/${missionId}/runs/${runId}`
  );
}

export function exportRunUrl(runId: string): string {
  return `${RESEARCH_BASE}/runs/${runId}/export`;
}

// -- Projections -------------------------------------------------------------

export async function fetchProjections(): Promise<ProjectionSummary> {
  return fetchJson<ProjectionSummary>(`${RESEARCH_BASE}/projections`);
}

export async function refreshProjection(
  name: string
): Promise<ProjectionStatus> {
  return fetchJson<ProjectionStatus>(
    `${RESEARCH_BASE}/projections/${name}/refresh`,
    { method: "POST" }
  );
}

export async function deleteProjection(
  name: string
): Promise<{ name: string; dropped: boolean }> {
  return fetchJson<{ name: string; dropped: boolean }>(
    `${RESEARCH_BASE}/projections/${name}`,
    { method: "DELETE" }
  );
}
