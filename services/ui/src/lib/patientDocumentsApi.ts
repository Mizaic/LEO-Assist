/**
 * Patient document CRUD API for journey testing.
 *
 * Atlas trace:
 *   DI: DI-DD1989E6, DI-9DD9E548
 */

export interface PatientDocumentPayload {
  title: string;
  markdown_body: string;
  category?: string;
  document_date?: string;
  episode_id?: string;
  milestone_type?: string;
  referral_id?: string;
  run_pipeline?: boolean;
}

export interface PatientDocumentResult {
  document_id: string;
  referral_id: string;
  encounter_id: string;
  chunk_ids: string[];
  run_id?: string | null;
}

export interface MilestoneSbarPayload {
  milestone_type: string;
  include_rollup?: boolean;
}

export interface MilestoneSbarResult {
  run_id: string;
  status: string;
  episode_assessment_id: string;
  rollup_assessment_id?: string | null;
  error_message?: string | null;
}

async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    credentials: "include",
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Request failed (${res.status})`);
  }
  return res.json() as Promise<T>;
}

export async function createPatientDocument(
  patientId: string,
  body: PatientDocumentPayload,
): Promise<PatientDocumentResult> {
  return fetchJson<PatientDocumentResult>(
    `/api/patients/${encodeURIComponent(patientId)}/documents`,
    { method: "POST", body: JSON.stringify(body) },
  );
}

export async function updatePatientDocument(
  patientId: string,
  documentId: string,
  body: Partial<PatientDocumentPayload>,
): Promise<PatientDocumentResult> {
  return fetchJson<PatientDocumentResult>(
    `/api/patients/${encodeURIComponent(patientId)}/documents/${encodeURIComponent(documentId)}`,
    { method: "PATCH", body: JSON.stringify(body) },
  );
}

export async function deletePatientDocument(
  patientId: string,
  documentId: string,
): Promise<{ document_id: string; status: string }> {
  return fetchJson<{ document_id: string; status: string }>(
    `/api/patients/${encodeURIComponent(patientId)}/documents/${encodeURIComponent(documentId)}`,
    { method: "DELETE" },
  );
}

export async function startMilestoneSbar(
  patientId: string,
  episodeId: string,
  body: MilestoneSbarPayload,
): Promise<MilestoneSbarResult> {
  return fetchJson<MilestoneSbarResult>(
    `/api/patients/${encodeURIComponent(patientId)}/episodes/${encodeURIComponent(episodeId)}/milestone-sbar`,
    { method: "POST", body: JSON.stringify(body) },
  );
}

export async function getMilestoneSbarRun(
  patientId: string,
  episodeId: string,
  runId: string,
): Promise<MilestoneSbarResult> {
  return fetchJson<MilestoneSbarResult>(
    `/api/patients/${encodeURIComponent(patientId)}/episodes/${encodeURIComponent(episodeId)}/milestone-sbar/${encodeURIComponent(runId)}`,
  );
}

export async function pollMilestoneSbarUntilTerminal(
  patientId: string,
  episodeId: string,
  runId: string,
  opts?: { intervalMs?: number; timeoutMs?: number },
): Promise<MilestoneSbarResult> {
  const intervalMs = opts?.intervalMs ?? 2000;
  const timeoutMs = opts?.timeoutMs ?? 120000;
  const started = Date.now();
  for (;;) {
    const result = await getMilestoneSbarRun(patientId, episodeId, runId);
    if (result.status === "completed" || result.status === "failed") {
      return result;
    }
    if (Date.now() - started > timeoutMs) {
      throw new Error("Timed out waiting for milestone SBAR.");
    }
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }
}

export const JOURNEY_MILESTONES = [
  { id: "first_presentation", label: "First presentation" },
  { id: "referral", label: "Referral" },
  { id: "first_seen", label: "First seen" },
  { id: "diagnosis_confirmed", label: "Diagnosis confirmed" },
  { id: "treatment_started", label: "Treatment started" },
  { id: "treatment_completed", label: "Treatment completed" },
] as const;
