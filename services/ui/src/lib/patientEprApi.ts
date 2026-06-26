/**
 * API client for the domain-agnostic patient EPR endpoints.
 *
 * Atlas trace:
 *   DO: DO-EBF0B124, DO-5D3EA371
 *   DI: DI-0ADA35BF, DI-357A7468
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-EBF0B124")
 *
 * All patients are returned regardless of episode type. No cancer filter.
 */

import { triggerReauth } from "@/lib/api/client";

function resolveApiBase(): string {
  if (typeof window !== "undefined") return window.location.origin;
  return (process.env.INTERNAL_API_BASE || "http://localhost:8000").replace(
    /\/+$/,
    ""
  );
}

const ANALYTICS_BASE = `${resolveApiBase()}/api/proxy/analytics`;

async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...init,
    credentials: "include",
    headers: {
      "X-Requested-With": "XMLHttpRequest",
      ...(init?.headers ?? {}),
    },
  });
  if (!res.ok) {
    if (res.status === 401) await triggerReauth();
    const err = await res.json().catch(() => ({}));
    throw new Error(
      (err as { detail?: string }).detail ||
        `Request failed (${res.status})`
    );
  }
  return res.json();
}

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface PatientSummary {
  patient_id: string;
  gender: string | null;
  birth_date: string | null;
  practice_name: string | null;
  episode_count: number;
  encounter_count: number;
  last_activity: string | null;
  active_alert_count: number;
  condition_types: string[];
}

export interface EpisodeSummaryEpr {
  episode_id: string | null;
  condition_type: string | null;
  status: string | null;
  referral_date: string | null;
  end_date: string | null;
  inferred_outcome: string | null;
}

export interface PatientDetail {
  patient_id: string;
  gender: string | null;
  birth_date: string | null;
  practice_name: string | null;
  active_alert_count: number;
  episodes: EpisodeSummaryEpr[];
}

export interface TimelineItem {
  item_type: "encounter" | "episode" | "alert" | string;
  item_id: string;
  item_date: string;
  label: string;
  extra: string | null;
}

export interface PatientsListResponse {
  total: number;
  page: number;
  page_size: number;
  patients: PatientSummary[];
}

export interface PatientFacetsResponse {
  condition_types: string[];
}

// ---------------------------------------------------------------------------
// API functions
// ---------------------------------------------------------------------------

/** List all patients in the caller's org scope, optionally filtered. */
export async function fetchEprPatients(
  page = 1,
  pageSize = 20,
  search?: string,
  conditionType?: string,
  hasAlerts?: boolean
): Promise<PatientsListResponse> {
  const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
  if (search) params.set("search", search);
  if (conditionType) params.set("condition_type", conditionType);
  if (hasAlerts === true) params.set("has_alerts", "true");
  return fetchJson<PatientsListResponse>(
    `${ANALYTICS_BASE}/patients?${params}`
  );
}

/** Return distinct condition types present in the caller's patient cohort. */
export async function fetchEprPatientFacets(): Promise<PatientFacetsResponse> {
  return fetchJson<PatientFacetsResponse>(`${ANALYTICS_BASE}/patients/facets`);
}

/** Return full patient detail including all episodes (no domain filter). */
export async function fetchEprPatientDetail(
  patientId: string
): Promise<PatientDetail> {
  return fetchJson<PatientDetail>(
    `${ANALYTICS_BASE}/patients/${encodeURIComponent(patientId)}`
  );
}

/** Return the activity timeline for a patient in reverse-chronological order. */
export async function fetchEprPatientTimeline(
  patientId: string
): Promise<TimelineItem[]> {
  return fetchJson<TimelineItem[]>(
    `${ANALYTICS_BASE}/patients/${encodeURIComponent(patientId)}/timeline`
  );
}
