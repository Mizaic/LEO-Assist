/**
 * API client for Mission Control endpoints.
 *
 * All requests go through the Next.js /api/proxy route so the session
 * cookie is forwarded automatically.
 */

import type { MissionControlFilters } from "@/lib/missionControlFilters";
import { toApiParams } from "@/lib/missionControlFilters";

function resolveBase(): string {
  if (typeof window !== "undefined") return window.location.origin;
  return (process.env.INTERNAL_API_BASE ?? "http://localhost:8001").replace(/\/+$/, "");
}

const PROXY = `${resolveBase()}/api/proxy/analytics`;

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
    const err = await res.json().catch(() => ({}));
    throw new Error(
      (err as { detail?: string }).detail ?? `Request failed (${res.status})`
    );
  }
  return res.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface EpisodeMilestone {
  milestone_type: string;
  encounter_id: string;
  date: string;
}

export interface MissionEpisode {
  episode_id: string;
  cancer_type: string | null;
  condition_type: string | null;
  status: string;
  cancer_stage: string | null;
  referral_date: string | null;
  end_date: string | null;
  specialist_visit_date?: string | null;
  diagnostic_interval_days: number | null;
  primary_care_interval_days: number | null;
  inferred_outcome: string | null;
  auto_close_reason: string | null;
  reviewed_by: string | null;
  reviewed_at: string | null;
  audit_notes: string | null;
  audit_flag: boolean;
  linked_encounter_ids?: string[];
  milestones?: EpisodeMilestone[];
}

export interface MissionPatient {
  patient_id: string;
  gender: string | null;
  age: number | null;
  practice_name: string | null;
  episodes: MissionEpisode[];
}

export interface MissionPatientsResponse {
  total: number;
  page: number;
  page_size: number;
  patients: MissionPatient[];
}

export interface MissionKPIs {
  total_patients: number;
  confirmed_cancer: number;
  pathway_closures: number;
  median_diagnostic_interval_days: number | null;
  safety_netting_rate: number;
  needs_review_count: number;
}

export interface ReviewPayload {
  reviewed_by: string;
  audit_notes?: string;
  audit_flag: boolean;
}

/** One persisted pipeline run (Neo4j AuditEvent, type PipelineRun). */
export interface PipelineAuditEvent {
  // Identity
  id: string | null;
  pipeline_kind: string | null;
  status: string | null;
  created_at: string | null;
  encounter_id: string;
  run_id: string | null;
  event_type: string | null;
  plan_definition_id: string | null;
  // Run outcome (flat scalars)
  step_count: number | null;
  total_duration_ms: number | null;
  entity_count: number | null;
  error_count: number | null;
  first_error: string | null;
  // LLM spend
  llm_input_tokens: number | null;
  llm_output_tokens: number | null;
  llm_cached_tokens: number | null;
  llm_cost_usd: number | null;
  // Extraction step provenance (flat -- displayed in audit trail; used in analytics)
  extraction_prompt_name: string;
  extraction_prompt_version: number | null;
  extraction_prompt_hash: string;
  extraction_provider: string;
  extraction_model_tier: string;
  // Detail blobs (JSON strings for step-level display)
  steps_json: string | null;
  errors_json: string | null;
}

export interface PipelineEventsResponse {
  patient_id: string;
  episode_id: string | null;
  events: PipelineAuditEvent[];
}

// ---------------------------------------------------------------------------
// API calls
// ---------------------------------------------------------------------------

export async function fetchMissionPatients(
  filters: MissionControlFilters,
  page: number,
  pageSize: number
): Promise<MissionPatientsResponse> {
  const p = toApiParams(filters);
  p.set("page", String(page));
  p.set("page_size", String(pageSize));
  return fetchJson<MissionPatientsResponse>(`${PROXY}/mission-control/patients?${p}`);
}

export async function fetchMissionKPIs(
  filters: MissionControlFilters
): Promise<MissionKPIs> {
  const p = toApiParams(filters);
  return fetchJson<MissionKPIs>(`${PROXY}/mission-control/kpis?${p}`);
}

export async function patchEpisodeReview(
  episodeId: string,
  payload: ReviewPayload
): Promise<{ episode_id: string; status: string }> {
  return fetchJson(`${PROXY}/mission-control/episodes/${episodeId}/review`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

/** Pipeline AuditEvent history for Mission Control audit trail. */
export async function fetchPatientPipelineEvents(
  patientId: string,
  options?: { episodeId?: string; orgId?: string; limit?: number }
): Promise<PipelineEventsResponse> {
  const p = new URLSearchParams();
  if (options?.episodeId) p.set("episode_id", options.episodeId);
  if (options?.orgId) p.set("org_id", options.orgId);
  if (options?.limit != null) p.set("limit", String(options.limit));
  const q = p.toString();
  const path = `${PROXY}/mission-control/patients/${encodeURIComponent(patientId)}/pipeline-events`;
  return fetchJson<PipelineEventsResponse>(q ? `${path}?${q}` : path);
}

export async function patchEpisodeStatus(
  episodeId: string,
  status: string,
  reason: string
): Promise<void> {
  await fetchJson(`${PROXY}/episodes/${episodeId}/status`, {
    method: "PATCH",
    body: JSON.stringify({ status, reason }),
  });
}

export async function rerunEpisodeDetector(
  patientId: string,
  _deleteExisting = true
): Promise<{
  run_id: string;
  queued: number;
  patient_ids: string[];
  action: string;
  preview: boolean;
  stream_path: string;
}> {
  // Route all patient rebuild actions through the canonical pipeline worker path.
  return fetchJson(`${resolveBase()}/api/pipeline/run-patient`, {
    method: "POST",
    body: JSON.stringify({
      patient_id: patientId,
      action: "full_pipeline",
      preview: false,
    }),
  });
}

/** Fetch coded concepts for a patient encounter (for Coded Data tab). */
export async function fetchEncounterConcepts(patientId: string): Promise<
  Array<{
    encounter_id: string;
    encounter_date: string;
    concept_id: string;
    concept_name: string;
    semantic_tag: string;
    assertion: string;
    confidence: number | null;
    source: string | null;
  }>
> {
  // NOTE: /patients/{id}/coding-summary returns high-level counters, not an iterable
  // encounter list with coded_links. Build coded concept rows by:
  // 1) listing encounters, then 2) fetching coded-links per coded encounter.
  const encountersUrl = `${resolveBase()}/api/patients/${patientId}/encounters?limit=500`;
  const encounters = await fetchJson<
    Array<{
      encounter_id: string;
      date: string;
      coded_count?: number;
    }>
  >(encountersUrl);

  const codedEncounters = encounters.filter((e) => (e.coded_count ?? 0) > 0);

  const linkResponses = await Promise.all(
    codedEncounters.map(async (enc) => {
      const linksUrl = `${resolveBase()}/api/patients/${patientId}/encounters/${enc.encounter_id}/coded-links`;
      const links = await fetchJson<
        Array<{
          concept_id: string;
          term?: string;
          semantic_tag?: string;
          assertion?: string;
          confidence?: number;
          source?: string;
        }>
      >(linksUrl);
      return { enc, links };
    })
  );

  const rows: Array<{
    encounter_id: string;
    encounter_date: string;
    concept_id: string;
    concept_name: string;
    semantic_tag: string;
    assertion: string;
    confidence: number | null;
    source: string | null;
  }> = [];

  for (const { enc, links } of linkResponses) {
    for (const link of links ?? []) {
      rows.push({
        encounter_id: enc.encounter_id,
        encounter_date: enc.date,
        concept_id: link.concept_id,
        concept_name: link.term ?? link.concept_id,
        semantic_tag: link.semantic_tag ?? "unknown",
        assertion: link.assertion ?? "present",
        confidence: typeof link.confidence === "number" ? link.confidence : null,
        source: link.source ?? null,
      });
    }
  }

  return rows;
}

/** Fetch encounters with raw text for a patient (for Encounter Text tab). */
export async function fetchPatientEncounters(patientId: string): Promise<
  Array<{
    encounter_id: string;
    date: string;
    text: string | null;
    coded_count: number;
  }>
> {
  const url = `${resolveBase()}/api/patients/${patientId}/encounters`;
  return fetchJson(url);
}

export async function resetAndRecodeEncounter(
  patientId: string,
  encounterId: string,
  dryRun = false,
  rerunEpisodeDetector = false
): Promise<{
  patient_id: string;
  encounter_id: string;
  links_deleted: number;
  shortcuts_deleted: number;
  review_queue_deleted: number;
  llm_usage_deleted: number;
  coding_decisions_deleted: number;
  queued: boolean;
  run_id: string;
  mode: string;
  dry_run: boolean;
  rerun_episode_detector: boolean;
}> {
  const url = `${resolveBase()}/api/patients/${patientId}/encounters/${encounterId}/reset-and-recode`;
  return fetchJson(url, {
    method: "POST",
    body: JSON.stringify({
      dry_run: dryRun,
      rerun_episode_detector: rerunEpisodeDetector,
    }),
  });
}
