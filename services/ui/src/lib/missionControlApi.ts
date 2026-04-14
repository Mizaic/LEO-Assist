/**
 * API client for Mission Control endpoints.
 *
 * All requests go through the Next.js /api/proxy route so the session
 * cookie is forwarded automatically.
 */

import type { MissionControlFilters } from "@/lib/missionControlFilters";
import { toApiParams } from "@/lib/missionControlFilters";
import { triggerReauth } from "@/lib/api/client";

function resolveBase(): string {
  if (typeof window !== "undefined") return window.location.origin;
  return (process.env.INTERNAL_API_BASE ?? "http://localhost:8001").replace(/\/+$/, "");
}

const PROXY = `${resolveBase()}/api/proxy/analytics`;

function detailToString(detail: unknown): string | null {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const rendered = detail
      .map((entry) => {
        if (typeof entry === "string") return entry;
        if (entry && typeof entry === "object") {
          const obj = entry as { msg?: unknown; loc?: unknown; type?: unknown };
          const msg = typeof obj.msg === "string" ? obj.msg : JSON.stringify(entry);
          const loc = Array.isArray(obj.loc) ? obj.loc.join(".") : "";
          return loc ? `${loc}: ${msg}` : msg;
        }
        return String(entry);
      })
      .filter(Boolean)
      .join("; ");
    return rendered || null;
  }
  if (detail && typeof detail === "object") {
    try {
      return JSON.stringify(detail);
    } catch {
      return String(detail);
    }
  }
  return null;
}

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
    const detail = detailToString((err as { detail?: unknown }).detail);
    throw new Error(
      detail ?? `Request failed (${res.status})`
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
  rebuild_status?: RebuildStatus | null;
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

export interface RebuildStatus {
  patient_id: string;
  run_id: string | null;
  status: "idle" | "queued" | "running" | "completed" | "failed";
  message: string | null;
  updated_at: string | null;
  queued_jobs: number | null;
  queue_depth: number | null;
  queue_position_estimate: number | null;
  median_duration_seconds: number | null;
  throughput_per_minute: number | null;
  eta_seconds_estimate: number | null;
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

export async function fetchPatientRebuildStatus(
  patientId: string,
  options?: { orgId?: string }
): Promise<RebuildStatus> {
  const p = new URLSearchParams();
  if (options?.orgId) p.set("org_id", options.orgId);
  const q = p.toString();
  const path = `${PROXY}/mission-control/patients/${encodeURIComponent(patientId)}/rebuild-status`;
  return fetchJson<RebuildStatus>(q ? `${path}?${q}` : path);
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

export interface EncounterListParams {
  orgId?: string;
  dateFrom?: string;
  dateTo?: string;
  patientId?: string;
  query?: string;
  page?: number;
  pageSize?: number;
  maxResults?: number;
  minCombinedScore?: number;
  minVectorScore?: number;
  requireKeywordAnchor?: boolean;
  nearDuplicateThreshold?: number;
  sortBy?: "encounter_date" | "patient_id" | "coded_count";
  sortDir?: "ASC" | "DESC";
}

export interface EncounterListItem {
  encounter_id: string;
  patient_id: string;
  encounter_date: string | null;
  text: string | null;
  flags?: string[] | null;
  coded_count: number;
  match_type: "none" | "keyword" | "semantic" | "hybrid";
  fulltext_score?: number | null;
  vector_score?: number | null;
  score?: number | null;
  rank_features?: {
    fulltext_norm: number;
    vector_norm: number;
    term_coverage: number;
    term_hits: number;
    recency: number;
    coded_norm: number;
  };
  match_rationale?: string[];
}

export interface EncounterListResponse {
  total: number;
  page: number;
  page_size: number;
  items: EncounterListItem[];
  query_diagnostics?: {
    query_audit_id: string;
    original_query: string;
    normalized_query: string;
    rewritten_query: string;
    rewrite_applied: boolean;
    rewrite_source: string;
    rewrite_confidence?: number | null;
    expanded_terms: string[];
    fulltext_query: string;
    reasoning?: string | null;
    near_duplicate_threshold?: number | null;
    near_duplicate_filtered_count?: number;
    near_duplicate_mode?: string;
    min_combined_score?: number | null;
    min_vector_score?: number | null;
    require_keyword_anchor?: boolean;
    relevance_filtered_count?: number;
  };
}

export interface EncounterKPIs {
  total_encounters: number;
  total_patients: number;
  coded_encounters: number;
  median_codes_per_encounter: number;
}

export async function fetchEncounterList(
  params: EncounterListParams
): Promise<EncounterListResponse> {
  const p = new URLSearchParams();
  if (params.orgId) p.set("org_id", params.orgId);
  if (params.dateFrom) p.set("date_from", params.dateFrom);
  if (params.dateTo) p.set("date_to", params.dateTo);
  if (params.patientId) p.set("patient_id", params.patientId);
  if (params.query) p.set("q", params.query);
  p.set("page", String(params.page ?? 1));
  p.set("page_size", String(params.pageSize ?? 25));
  p.set("max_results", String(params.maxResults ?? 2000));
  if (typeof params.minCombinedScore === "number") {
    p.set("min_combined_score", String(params.minCombinedScore));
  }
  if (typeof params.minVectorScore === "number") {
    p.set("min_vector_score", String(params.minVectorScore));
  }
  if (typeof params.requireKeywordAnchor === "boolean") {
    p.set("require_keyword_anchor", String(params.requireKeywordAnchor));
  }
  if (typeof params.nearDuplicateThreshold === "number") {
    p.set("near_duplicate_threshold", String(params.nearDuplicateThreshold));
  }
  p.set("sort_by", params.sortBy ?? "encounter_date");
  p.set("sort_dir", params.sortDir ?? "DESC");
  return fetchJson<EncounterListResponse>(
    `${PROXY}/mission-control/encounters?${p.toString()}`
  );
}

export async function fetchEncounterKPIs(
  params: Omit<EncounterListParams, "page" | "pageSize" | "sortBy" | "sortDir" | "query">
): Promise<EncounterKPIs> {
  const p = new URLSearchParams();
  if (params.orgId) p.set("org_id", params.orgId);
  if (params.dateFrom) p.set("date_from", params.dateFrom);
  if (params.dateTo) p.set("date_to", params.dateTo);
  if (params.patientId) p.set("patient_id", params.patientId);
  return fetchJson<EncounterKPIs>(
    `${PROXY}/mission-control/encounters/kpis?${p.toString()}`
  );
}

export interface BatchResetItem {
  patient_id: string;
  encounter_id: string;
}

export interface EncounterCodedLink {
  concept_id: string;
  term?: string;
  semantic_tag?: string;
  assertion?: string;
  confidence?: number | null;
  source?: string | null;
  evidence?: string | null;
  evidence_sentence?: string | null;
  sentence_index?: number | null;
  evidence_start?: number | null;
  evidence_end?: number | null;
  domain?: string | null;
  model_name?: string | null;
  model_version?: string | null;
  contract_version?: string | null;
  run_id?: string | null;
  coded_at?: string | null;
}

export interface BatchResetResponse {
  batch_id: string;
  requested: number;
  queued_count: number;
  failed_count: number;
  dry_run: boolean;
  trigger_analysis: boolean;
  queued: Array<BatchResetItem & { run_id: string; stream_path: string }>;
  failed: Array<BatchResetItem & { error: string }>;
}

export async function batchResetAndRecodeEncounters(
  items: BatchResetItem[],
  triggerAnalysis = false,
  searchContext?: EncounterListResponse["query_diagnostics"]
): Promise<BatchResetResponse> {
  return fetchJson<BatchResetResponse>(`${resolveBase()}/api/patients/encounters/batch-reset-and-recode`, {
    method: "POST",
    body: JSON.stringify({
      items,
      trigger_analysis: triggerAnalysis,
      dry_run: false,
      search_context: searchContext,
    }),
  });
}

export interface EncounterUniquenessItem {
  encounter_id: string;
  uniqueness_score: number; // 1 = completely unique, 0 = near-duplicate
}

export async function fetchEncounterUniqueness(
  encounterIds: string[]
): Promise<EncounterUniquenessItem[]> {
  return fetchJson<EncounterUniquenessItem[]>(
    `${PROXY}/mission-control/encounters/uniqueness`,
    {
      method: "POST",
      body: JSON.stringify({ encounter_ids: encounterIds }),
    }
  );
}

export async function fetchEncounterCodedLinks(
  patientId: string,
  encounterId: string
): Promise<EncounterCodedLink[]> {
  const url = `${resolveBase()}/api/patients/${encodeURIComponent(
    patientId
  )}/encounters/${encodeURIComponent(encounterId)}/coded-links`;
  return fetchJson<EncounterCodedLink[]>(url);
}
