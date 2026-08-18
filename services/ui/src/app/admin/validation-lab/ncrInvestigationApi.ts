/**
 * Local NCR investigation store. NHS numbers stay in LEO.
 *
 * Atlas: DI-ED5A9AC3
 *
 * Atlas trace:
 *   DO: DO-158BE606
 *   DI: DI-2289D095
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-158BE606")
 */
import { formatLabApiError } from "./labApi";
import type { ClinicalPipelineRun } from "./labFindingsApi";
import { triggerReauth } from "@/lib/api/client";

export interface InvestigationEvent {
  event_id?: string;
  kind?: string;
  local_text?: string;
  atlas_text?: string;
  atlas_ok?: boolean;
  created_at?: string;
}

export interface InvestigationRecord {
  nc_id: string;
  title?: string;
  cases: ClinicalPipelineRun[];
  events?: InvestigationEvent[];
}

export function getInvestigation(ncId: string): Promise<InvestigationRecord> {
  return apiJson(
    `/api/validation-lab/ncrs/${encodeURIComponent(ncId)}/investigation`,
  );
}

export function saveInvestigationCases(
  ncId: string,
  cases: ClinicalPipelineRun[],
  title = "",
): Promise<InvestigationRecord> {
  return apiJson(
    `/api/validation-lab/ncrs/${encodeURIComponent(ncId)}/investigation/cases`,
    {
      method: "PUT",
      body: JSON.stringify({
        title,
        cases: cases.map((row) => ({
          run_id: row.run_id || "",
          patient_id: row.patient_id || "",
          patient_name: row.patient_name || "",
          nhs_number: row.nhs_number || "",
          ubrn: row.ubrn || "",
          status: row.status || "",
        })),
      }),
    },
  );
}

export function logInvestigationEvent(
  ncId: string,
  kind: string,
  text: string,
): Promise<{ atlas_ok?: boolean; atlas_text?: string }> {
  return apiJson(
    `/api/validation-lab/ncrs/${encodeURIComponent(ncId)}/investigation/events`,
    {
      method: "POST",
      body: JSON.stringify({ kind, text }),
    },
  );
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
    throw new Error(formatLabApiError(body, res.status));
  }
  return body as T;
}
