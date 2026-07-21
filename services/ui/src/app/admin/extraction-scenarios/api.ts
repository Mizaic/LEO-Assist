/**
 * API helpers for the Extraction Scenarios admin surface.
 *
 * Atlas trace:
 *   DO: DO-2C03CA0E
 *   DI: DI-3F771AFB
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-2C03CA0E")
 */
import type {
  ExtractionScenarioDetail,
  QuickRunRequest,
  QuickRunResult,
  ScenarioListResponse,
  ScenarioWritePayload,
  ValidationRunStatus,
} from "./types";

const BASE = "/api/extraction-scenarios";

function headers(): HeadersInit {
  return { "X-Requested-With": "XMLHttpRequest", "Content-Type": "application/json" };
}

export async function listScenarios(params?: {
  status?: string;
  site?: string;
  search?: string;
}): Promise<ScenarioListResponse> {
  const qs = new URLSearchParams();
  if (params?.status && params.status !== "all") qs.set("status", params.status);
  if (params?.site) qs.set("site", params.site);
  if (params?.search) qs.set("search", params.search);
  const url = qs.toString() ? `${BASE}?${qs}` : BASE;
  const res = await fetch(url, { headers: headers() });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getScenario(caseId: string): Promise<ExtractionScenarioDetail> {
  const res = await fetch(`${BASE}/${caseId}`, { headers: headers() });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function approveScenario(caseId: string): Promise<void> {
  const res = await fetch(`${BASE}/${caseId}`, {
    method: "PATCH",
    headers: headers(),
    body: JSON.stringify({ review_status: "approved" }),
  });
  if (!res.ok) throw new Error(await res.text());
}

export async function createScenario(payload: ScenarioWritePayload): Promise<{ case_id: string }> {
  const res = await fetch(BASE, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function updateScenario(
  caseId: string,
  payload: Omit<ScenarioWritePayload, "case_id">,
): Promise<{ case_id: string }> {
  const res = await fetch(`${BASE}/${caseId}`, {
    method: "PUT",
    headers: headers(),
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function deleteScenario(caseId: string): Promise<void> {
  const res = await fetch(`${BASE}/${caseId}`, {
    method: "DELETE",
    headers: headers(),
  });
  if (!res.ok) throw new Error(await res.text());
}

export async function triggerRun(scope: string): Promise<{ run_id: string }> {
  const res = await fetch(`${BASE}/runs`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({ scope }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getRunStatus(runId: string): Promise<ValidationRunStatus> {
  const res = await fetch(`${BASE}/runs/${runId}`, { headers: headers() });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function startQuickRun(
  req: QuickRunRequest,
): Promise<{ run_id: string; patient_id: string }> {
  const res = await fetch(`${BASE}/quick-run`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify(req),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function pollQuickRun(runId: string): Promise<QuickRunResult> {
  const res = await fetch(`${BASE}/runs/${runId}`, { headers: headers() });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function deleteQuickRun(runId: string): Promise<void> {
  const res = await fetch(`${BASE}/quick-run/${runId}`, {
    method: "DELETE",
    headers: headers(),
  });
  if (!res.ok) throw new Error(await res.text());
}
