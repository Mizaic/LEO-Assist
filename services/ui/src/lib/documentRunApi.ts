/**
 * API client for re-running the referral pipeline on document chunks.
 *
 * Atlas trace:
 *   DO: DO-5D3EA371
 *   DI: DI-357A7468
 */

import { triggerReauth } from "@/lib/api/client";

function resolveApiBase(): string {
  if (typeof window !== "undefined") return window.location.origin;
  return (process.env.INTERNAL_API_BASE || "http://localhost:8000").replace(
    /\/+$/,
    "",
  );
}

const PATIENTS_BASE = `${resolveApiBase()}/api/patients`;

async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...init,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      "X-Requested-With": "XMLHttpRequest",
      ...(init?.headers ?? {}),
    },
  });
  if (!res.ok) {
    if (res.status === 401) await triggerReauth();
    const err = await res.json().catch(() => ({}));
    throw new Error(
      (err as { detail?: string }).detail ||
        `Request failed (${res.status})`,
    );
  }
  return res.json();
}

export interface DocumentRunStage {
  step_id: string;
  status: string;
  error_summary?: string;
}

export interface DocumentRunResponse {
  run_id: string;
  status: string;
  assessment_id: string | null;
  error_message: string | null;
  stage_progress: DocumentRunStage[];
}

export interface StartDocumentRunRequest {
  document_reference_id: string;
  chunk_ids: string[];
  plan_id?: string;
}

export async function startDocumentRun(
  patientId: string,
  body: StartDocumentRunRequest,
): Promise<DocumentRunResponse> {
  return fetchJson<DocumentRunResponse>(
    `${PATIENTS_BASE}/${encodeURIComponent(patientId)}/document-runs`,
    { method: "POST", body: JSON.stringify(body) },
  );
}

export async function getDocumentRun(
  patientId: string,
  runId: string,
): Promise<DocumentRunResponse> {
  return fetchJson<DocumentRunResponse>(
    `${PATIENTS_BASE}/${encodeURIComponent(patientId)}/document-runs/${encodeURIComponent(runId)}`,
  );
}

const TERMINAL = new Set(["completed", "failed"]);
const POLL_MS = 2000;
const POLL_TIMEOUT_MS = 15 * 60 * 1000;

export async function pollDocumentRunUntilTerminal(
  patientId: string,
  runId: string,
  onTick?: (run: DocumentRunResponse) => void,
): Promise<DocumentRunResponse> {
  const deadline = Date.now() + POLL_TIMEOUT_MS;
  for (;;) {
    const run = await getDocumentRun(patientId, runId);
    onTick?.(run);
    if (TERMINAL.has(run.status) || Date.now() > deadline) {
      return run;
    }
    await new Promise((resolve) => setTimeout(resolve, POLL_MS));
  }
}
