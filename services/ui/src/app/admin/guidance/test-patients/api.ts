/**
 * Thin client for the /api/guidance/test-patients endpoints.
 *
 * Centralised so component code does not duplicate fetch boilerplate
 * and so the X-Requested-With CSRF header is set consistently.
 */

import type {
  BitmapStatus,
  DiagnoseResponse,
  DryRunResponse,
  GenerateResponse,
  GuidelinePickerEntry,
  PatientPayload,
  ReplayReport,
  SandboxReplayResponse,
  TestPatient,
} from "./types";

const BASE = "/api/guidance/test-patients";

const JSON_HEADERS = {
  "Content-Type": "application/json",
  "X-Requested-With": "XMLHttpRequest",
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(`${BASE}${path}`, init);
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(text || `Request failed (${resp.status})`);
  }
  return (await resp.json()) as T;
}

export interface DryRunBody {
  patient: PatientPayload;
  scope_type?: string;
  scope_id?: string;
  ruleset_version?: string | null;
}

export function dryRun(body: DryRunBody): Promise<DryRunResponse> {
  return request("/dry-run", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify(body),
  });
}

export interface SaveBody extends DryRunBody {
  guideline_id: string;
  expectations: Array<{
    rule_id: string;
    fires: boolean;
    matched_branch_node_ids: string[];
  }>;
  skip_if_exists?: boolean;
}

export function savePatient(
  body: SaveBody
): Promise<{ id: string; created: boolean; expectations_written: number }> {
  return request("", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify(body),
  });
}

export function listPatients(params: {
  guideline_id?: string;
  rule_id?: string;
  node_id?: string;
}): Promise<TestPatient[]> {
  const qs = new URLSearchParams();
  if (params.guideline_id) qs.set("guideline_id", params.guideline_id);
  if (params.rule_id) qs.set("rule_id", params.rule_id);
  if (params.node_id) qs.set("node_id", params.node_id);
  const tail = qs.toString();
  return request(tail ? `?${tail}` : "");
}

export function deletePatient(id: string): Promise<{ deleted: number }> {
  return request(`/${encodeURIComponent(id)}`, {
    method: "DELETE",
    headers: { "X-Requested-With": "XMLHttpRequest" },
  });
}

export interface GenerateBody {
  scope_type: "rule" | "branch" | "guideline" | "all";
  guideline_id?: string;
  rule_id?: string;
  branch_node_id?: string;
  depth?: "minimal_pair" | "boundary_plus_pairs";
  exclude_existing?: boolean;
}

export function generateProposals(body: GenerateBody): Promise<GenerateResponse> {
  return request("/generate", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify(body),
  });
}

export interface ReplayBody {
  patient_ids?: string[];
  guideline_id?: string;
  scope_type?: string;
  scope_id?: string;
  ruleset_version?: string | null;
  persist_report?: boolean;
}

export function replay(body: ReplayBody): Promise<ReplayReport> {
  return request("/replay", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify(body),
  });
}

export interface DiagnoseBody {
  rule_id: string;
  patient: PatientPayload;
  scope_type?: string;
  scope_id?: string;
  ruleset_version?: string | null;
}

/**
 * Per-rule diagnostic evaluation that uses the production bitmap
 * evaluator.  The annotated tree is guaranteed to agree with the
 * live firing decision because the same bitmap operations drive
 * both endpoints.
 */
export function diagnose(body: DiagnoseBody): Promise<DiagnoseResponse> {
  return request("/diagnose", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify(body),
  });
}

export function listGuidelines(): Promise<GuidelinePickerEntry[]> {
  return request("/guidelines");
}

/**
 * Sandbox replay -- compiles UNSAVED draft rules into a custom-scoped
 * bitmap, replays saved patients through it, and drops the sandbox
 * once finished.  Used by the rule editor's "Test against library"
 * button so the reviewer can see how their pending edits would behave
 * before saving.
 */
export interface SandboxReplayBody {
  rules: Array<Record<string, unknown>>;
  patient_ids?: string[];
  guideline_id?: string;
  sandbox_id?: string;
  policy_mode?: "advisory" | "strict";
}

export function sandboxReplay(
  body: SandboxReplayBody,
): Promise<SandboxReplayResponse> {
  return request("/sandbox-replay", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify(body),
  });
}

/**
 * Production bitmap status -- read by the "no ruleset compiled" banner
 * so it can warn the reviewer that ALL evaluations are returning zero
 * matches because the ruleset was never compiled.  Hits the existing
 * terminology proxy at ``/api/terminology/guidelines/bitmap/status``
 * (this endpoint lives in services/terminology_api/app/routers/guidelines.py).
 */
export async function getBitmapStatus(
  scopeType: string = "global",
  scopeId: string = "default",
): Promise<BitmapStatus> {
  const qs = new URLSearchParams({
    scope_type: scopeType,
    scope_id: scopeId,
  });
  const resp = await fetch(
    `/api/terminology/guidelines/bitmap/status?${qs.toString()}`,
  );
  if (!resp.ok) {
    throw new Error(
      (await resp.text()) || `Bitmap status failed (${resp.status})`,
    );
  }
  return (await resp.json()) as BitmapStatus;
}

/**
 * One-click compile of the production bitmap.  Posts to the existing
 * terminology proxy at ``/api/terminology/guidelines/bitmap/compile``
 * with the same default scope production runs use (global / default).
 * The endpoint is async (returns a job_id immediately).
 */
export async function compileProductionBitmap(
  scopeType: string = "global",
  scopeId: string = "default",
  policyMode: "advisory" | "strict" = "advisory",
): Promise<{ job_id: string; version: string }> {
  const resp = await fetch("/api/terminology/guidelines/bitmap/compile", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify({
      scope_type: scopeType,
      scope_id: scopeId,
      policy_mode: policyMode,
    }),
  });
  if (!resp.ok) {
    throw new Error(
      (await resp.text()) || `Compile request failed (${resp.status})`,
    );
  }
  return (await resp.json()) as { job_id: string; version: string };
}
