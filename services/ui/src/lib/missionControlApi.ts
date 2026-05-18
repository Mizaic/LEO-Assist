/**
 * API client for Mission Control endpoints.
 *
 * All requests go through the Next.js /api/proxy route so the session
 * cookie is forwarded automatically.
 *
 * Atlas trace:
 *   DO: DO-9530152E
 *   Also implements: DO-EE78E305
 *   DI: DI-6EA84931, DI-DD67ACFF
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-9530152E")
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
  /** Who linked this encounter to the episode. "episode_engine" means the AI
   *  wrote it; anything else (or absent) is a manual curator action. */
  linked_by?: string | null;
  /** Literal text snippet from the source encounter that justifies this
   *  milestone. Populated by the AI engine; may be empty for manual links. */
  evidence_quote?: string | null;
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
  benign_interval_days: number | null;
  primary_care_interval_days: number | null;
  inferred_outcome: string | null;
  auto_close_reason: string | null;
  reviewed_by: string | null;
  reviewed_at: string | null;
  review_verdict?: string | null;
  audit_notes: string | null;
  audit_flag: boolean;
  variation_flag?: boolean;
  variation_score?: number | null;
  variation_first_divergence?: string | null;
  variation_attributed_node_type?: string | null;
  variation_attributed_node_name?: string | null;
  variation_community_id?: number | null;
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

export interface MissionKPICohort {
  total_patients: number;
  excluded_total: number;
  excluded_no_pathway: number;
  excluded_missing_referral_date: number;
  excluded_outside_window: number;
}

export interface MissionKPIs {
  total_patients: number;
  confirmed_cancer: number;
  confirmed_cancer_patients: number;
  pathway_closures: number;
  pathway_closure_patients: number;
  median_diagnostic_interval_days: number | null;
  safety_netting_rate: number;
  needs_review_count: number;
  cancer_type_counts?: Record<string, number>;
  cohort?: MissionKPICohort;
}

export interface ReviewPayload {
  reviewed_by: string;
  audit_notes?: string;
  audit_flag: boolean;
}

/**
 * Curator sign-off payload (DI-E2498DF6).
 *
 * The `verdict` MUST be a member of `REVIEW_VERDICT_VALUES` from
 * `@/lib/episodeStatus`. The server maps the verdict to the canonical
 * EpisodeStatus and writes the whole thing in one Cypher transaction.
 */
export interface SignOffPayload {
  verdict: string;
  reviewed_by: string;
  audit_notes?: string;
  audit_flag?: boolean;
}

export interface SignOffResponse {
  episode_id: string;
  review_verdict: string;
  status: string;
  reviewed_at: string;
  reviewed_by: string;
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

/**
 * One human-curator action recorded by write_episode_audit_event.
 * The pipeline-events endpoint does NOT return these; use
 * fetchPatientManualEvents(). DI-3A19BE12, R-A737EE12.
 */
export interface ManualAuditEvent {
  id: string | null;
  /** EpisodeManualCreate / EpisodeManualUpdate / EpisodeManualDelete /
   *  EpisodeManualAttach / EpisodeManualDetach / EpisodeManualReplace. */
  event_type: string | null;
  subtype: string | null;
  created_at: string | null;
  actor_email: string;
  actor_role: string;
  episode_id: string;
  patient_id: string;
  notes: string;
  before_json: string | null;
  after_json: string | null;
}

export interface ManualEventsResponse {
  patient_id: string;
  episode_id: string | null;
  events: ManualAuditEvent[];
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

/**
 * Atomic curator sign-off: records the reviewer's verdict and the
 * mapped EpisodeStatus together (DI-E2498DF6). Prefer this over
 * patchEpisodeReview + patchEpisodeStatus for any new UI so the
 * episode cannot end up in a half-reviewed state.
 */
export async function patchEpisodeSignOff(
  episodeId: string,
  payload: SignOffPayload
): Promise<SignOffResponse> {
  return fetchJson(
    `${PROXY}/mission-control/episodes/${episodeId}/sign-off`,
    {
      method: "PATCH",
      body: JSON.stringify(payload),
    },
  );
}

export interface MissionPatientEpisodesResponse {
  patient_id: string;
  episodes: MissionEpisode[];
}

/**
 * Full EpisodeOfCare list for a single patient, NOT filtered by the
 * Mission Control cohort filter (DI-5E47FA5D). The patient drawer uses
 * this as the source of truth so that newly-created in_review episodes
 * are visible immediately on a confirmed_cancer cohort view.
 */
export async function fetchMissionPatientEpisodes(
  patientId: string,
  options?: { orgId?: string },
): Promise<MissionPatientEpisodesResponse> {
  const p = new URLSearchParams();
  if (options?.orgId) p.set("org_id", options.orgId);
  const q = p.toString();
  const base = `${PROXY}/mission-control/patients/${encodeURIComponent(
    patientId,
  )}/episodes`;
  return fetchJson<MissionPatientEpisodesResponse>(q ? `${base}?${q}` : base);
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

/**
 * Manual EpisodeManual* AuditEvent history for the audit trail tab.
 * Returns the curator-driven mutations (create / update / delete /
 * attach / detach / replace) that the pipeline-events endpoint
 * deliberately filters out.
 */
export async function fetchPatientManualEvents(
  patientId: string,
  options?: { episodeId?: string; orgId?: string; limit?: number }
): Promise<ManualEventsResponse> {
  const p = new URLSearchParams();
  if (options?.episodeId) p.set("episode_id", options.episodeId);
  if (options?.orgId) p.set("org_id", options.orgId);
  if (options?.limit != null) p.set("limit", String(options.limit));
  const q = p.toString();
  const path = `${PROXY}/mission-control/patients/${encodeURIComponent(patientId)}/manual-events`;
  return fetchJson<ManualEventsResponse>(q ? `${path}?${q}` : path);
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
    value: number | string | null;
    unit: string | null;
    reference_range: string | null;
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
          value?: number | string | null;
          unit?: string | null;
          reference_range?: string | null;
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
    value: number | string | null;
    unit: string | null;
    reference_range: string | null;
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
        value: link.value ?? null,
        unit: link.unit ?? null,
        reference_range: link.reference_range ?? null,
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
  value?: number | string | null;
  unit?: string | null;
  reference_range?: string | null;
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

// ---------------------------------------------------------------------------
// Reconcile pathway and VerificationLock client
//
// Atlas trace:
//   DI: DI-C424BB44 (VerificationLock cross-entity primitive)
//   DI: DI-9DCC9F84 (Reconcile pathway)
//   DO: this client (UI surface for the reconcile drawer)
//   VT: VT-96455BC1 (lock service), VT-CABCEC8B (reconcile router)
// ---------------------------------------------------------------------------

export type ReconcileActionType =
  | "confirm"
  | "replace"
  | "detach"
  | "not_applicable";

export type ReviewerRole = "clinician" | "qa_ra_lead";

export type LockEntityType =
  | "episode"
  | "encounter"
  | "is_part_of_edge"
  | "coded_link"
  | "assertion";

export interface ReconcileAction {
  slot: string;
  action: ReconcileActionType;
  encounter_id?: string | null;
  milestone_type?: string | null;
}

export interface ReconcileRequestBody {
  actions: ReconcileAction[];
  reviewed_by: string;
  reviewer_role: ReviewerRole;
  reason: string;
  confirm_bucket_flip?: boolean;
}

export interface ReconcileLockResult {
  slot: string;
  lock_id: string;
  entity_type: LockEntityType;
  entity_id: string;
}

export interface ReconcileResponse {
  episode_id: string;
  bucket: string;
  flipped: boolean;
  current_bucket: string;
  proposed_bucket: string;
  locks: ReconcileLockResult[];
}

export interface VerificationLockSummary {
  lock_id: string;
  entity_type: LockEntityType;
  entity_id: string;
  locked_by: string;
  locked_by_role: ReviewerRole;
  locked_at: string;
  lock_reason: string;
  source: string;
}

export interface EpisodeLocksResponse {
  episode_id: string;
  locks: VerificationLockSummary[];
}

/**
 * PATCH /mission-control/episodes/{episodeId}/reconcile
 *
 * Applies one or more milestone-slot actions in a single transaction.
 * The server refuses with HTTP 412 when the proposed actions would
 * silently flip the lifecycle bucket and `confirm_bucket_flip` is
 * not set to `true`.
 */
export async function patchEpisodeReconcile(
  episodeId: string,
  body: ReconcileRequestBody
): Promise<ReconcileResponse> {
  return fetchJson<ReconcileResponse>(
    `${PROXY}/mission-control/episodes/${encodeURIComponent(episodeId)}/reconcile`,
    {
      method: "PATCH",
      body: JSON.stringify(body),
    }
  );
}

/**
 * GET /mission-control/episodes/{episodeId}/locks
 *
 * Returns every VerificationLock attached to an episode and the
 * encounters / coded links / assertions that hang off it. Used by the
 * Reconcile Pathway drawer to render lock chips next to milestones
 * and encounter cards.
 */
export async function listLocksForEpisode(
  episodeId: string
): Promise<EpisodeLocksResponse> {
  return fetchJson<EpisodeLocksResponse>(
    `${PROXY}/mission-control/episodes/${encodeURIComponent(episodeId)}/locks`
  );
}

export interface CodedLinkLockBody {
  decision: "accept" | "reject";
  reviewer_role: ReviewerRole;
  reason: string;
}

export interface CodedLinkLockResponse {
  decision: "accept" | "reject";
  encounter_id: string;
  concept_id: string;
  lock?: {
    lock_id: string;
    entity_type: LockEntityType;
    entity_id: string;
  } | null;
  released?: boolean;
}

/**
 * POST /api/patients/{patientId}/encounters/{encounterId}/coded-links/{conceptId}/lock
 *
 * Reviewer accept/reject for a single coded link. `accept` writes a
 * VerificationLock so the recode pipeline can no longer overwrite this
 * link; `reject` releases an existing lock so the next recode pass can
 * re-evaluate it.
 *
 * `lockEntity` and `unlockEntity` are thin wrappers that pin the
 * decision and provide a single call site for the drawer.
 */
export async function lockEntity(
  patientId: string,
  encounterId: string,
  conceptId: string,
  body: Omit<CodedLinkLockBody, "decision">
): Promise<CodedLinkLockResponse> {
  return fetchJson<CodedLinkLockResponse>(
    `${resolveBase()}/api/patients/${encodeURIComponent(
      patientId
    )}/encounters/${encodeURIComponent(
      encounterId
    )}/coded-links/${encodeURIComponent(conceptId)}/lock`,
    {
      method: "POST",
      body: JSON.stringify({ ...body, decision: "accept" }),
    }
  );
}

export async function unlockEntity(
  patientId: string,
  encounterId: string,
  conceptId: string,
  body: Omit<CodedLinkLockBody, "decision">
): Promise<CodedLinkLockResponse> {
  return fetchJson<CodedLinkLockResponse>(
    `${resolveBase()}/api/patients/${encodeURIComponent(
      patientId
    )}/encounters/${encodeURIComponent(
      encounterId
    )}/coded-links/${encodeURIComponent(conceptId)}/lock`,
    {
      method: "POST",
      body: JSON.stringify({ ...body, decision: "reject" }),
    }
  );
}

// ---------------------------------------------------------------------------
// Manual EpisodeOfCare CRUD - DI-3A19BE12, DI-F4C06C92, DI-B35DCA0F,
// DI-41B71BF8 / DOs DO-0792E2CB, DO-BDBEDA43, DO-13EA9B93, DO-CFB91205.
// ---------------------------------------------------------------------------

export interface EpisodeEncounterAttachment {
  encounter_id: string;
  milestone_type: string;
}

export interface EpisodeCreateBody {
  patient_id: string;
  cancer_type?: string | null;
  condition_type?: string | null;
  cancer_stage?: string | null;
  referral_date?: string | null;
  end_date?: string | null;
  status?: string;
  audit_notes?: string | null;
  audit_flag?: string | null;
  initial_encounter_links?: EpisodeEncounterAttachment[];
}

export interface EpisodeUpdateBody {
  cancer_type?: string | null;
  condition_type?: string | null;
  cancer_stage?: string | null;
  referral_date?: string | null;
  end_date?: string | null;
  inferred_outcome?: string | null;
  audit_notes?: string | null;
  audit_flag?: string | null;
}

export interface EpisodeDeleteBody {
  confirm_episode_id: string;
  reason?: string | null;
}

export interface EpisodeDerivedDates {
  referral_date: string | null;
  end_date: string | null;
  diagnostic_interval_days: number | null;
  benign_interval_days: number | null;
  primary_care_interval_days: number | null;
}

export interface EpisodeCreateResponse {
  success: true;
  episode_id: string;
  patient_id: string;
  derived_dates: EpisodeDerivedDates | null;
}

export interface EpisodeUpdateResponse {
  success: true;
  episode_id: string;
  updated_fields: string[];
}

export interface EpisodeDeleteResponse {
  success: true;
  episode_id: string;
  patient_id: string;
}

export interface EpisodeAttachResponse {
  success: true;
  episode_id: string;
  encounter_id: string;
  milestone_type: string;
  // True when the (encounter, episode, milestone_type) edge already
  // existed -- backend short-circuits via DI-F5E030ED. derived_dates
  // is null in this no-op case (no re-derive runs).
  already_linked?: boolean;
  derived_dates: EpisodeDerivedDates | null;
}

export interface EpisodeDetachResponse {
  success: true;
  episode_id: string;
  encounter_id: string;
  derived_dates: EpisodeDerivedDates;
}

/**
 * POST /analytics/episodes - manually create an EpisodeOfCare from
 * the patient drawer. The server enforces role gating
 * (clinician / qa_ra_lead / platform_admin) and org-scope on
 * `patient_id`. Optional `initial_encounter_links` are attached as
 * IS_PART_OF edges and the episode dates are re-derived from them.
 */
export async function createEpisode(
  body: EpisodeCreateBody
): Promise<EpisodeCreateResponse> {
  return fetchJson<EpisodeCreateResponse>(`${PROXY}/episodes`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/**
 * PATCH /analytics/episodes/{episodeId} - sparse patch on
 * EpisodeOfCare properties. Only fields present in `body` are
 * written; the server stamps `updated_by` / `updated_at` and writes
 * an EpisodeManualUpdate AuditEvent with before / after snapshots.
 */
export async function updateEpisode(
  episodeId: string,
  body: EpisodeUpdateBody
): Promise<EpisodeUpdateResponse> {
  return fetchJson<EpisodeUpdateResponse>(
    `${PROXY}/episodes/${encodeURIComponent(episodeId)}`,
    {
      method: "PATCH",
      body: JSON.stringify(body),
    }
  );
}

/**
 * DELETE /analytics/episodes/{episodeId} - hard delete with a
 * type-the-id confirm gate. `confirm_episode_id` MUST equal
 * `episodeId`; the server returns 400 before any graph write
 * otherwise. Encounters survive the deletion (DETACH DELETE on the
 * episode only). Writes an EpisodeManualDelete AuditEvent
 * containing the full property snapshot of the deleted node.
 */
export async function deleteEpisode(
  episodeId: string,
  body: EpisodeDeleteBody
): Promise<EpisodeDeleteResponse> {
  return fetchJson<EpisodeDeleteResponse>(
    `${PROXY}/episodes/${encodeURIComponent(episodeId)}`,
    {
      method: "DELETE",
      body: JSON.stringify(body),
    }
  );
}

/**
 * POST /analytics/episodes/{episodeId}/encounters - attach an
 * Encounter to an EpisodeOfCare with a milestone slot. The server
 * tags the IS_PART_OF edge with `linked_by="manual_attach"` and
 * re-derives the episode dates from the resulting attachments.
 */
export async function attachEncounterToEpisode(
  episodeId: string,
  body: EpisodeEncounterAttachment
): Promise<EpisodeAttachResponse> {
  return fetchJson<EpisodeAttachResponse>(
    `${PROXY}/episodes/${encodeURIComponent(episodeId)}/encounters`,
    {
      method: "POST",
      body: JSON.stringify(body),
    }
  );
}

/**
 * DELETE /analytics/episodes/{episodeId}/encounters/{encounterId} -
 * detach an Encounter from an EpisodeOfCare. Both nodes survive;
 * only the IS_PART_OF edge is removed. Episode dates are re-derived
 * afterwards.
 */
export async function detachEncounterFromEpisode(
  episodeId: string,
  encounterId: string,
  opts?: { milestoneType?: string | null }
): Promise<EpisodeDetachResponse> {
  const mt = opts?.milestoneType ?? null;
  // When milestoneType is supplied we pass it as a query param so
  // the backend removes only that one :IS_PART_OF edge and leaves
  // any other slots this encounter fills on the same episode in
  // place -- DI-F5E030ED.
  const qs = mt ? `?milestone_type=${encodeURIComponent(mt)}` : "";
  return fetchJson<EpisodeDetachResponse>(
    `${PROXY}/episodes/${encodeURIComponent(
      episodeId
    )}/encounters/${encodeURIComponent(encounterId)}${qs}`,
    {
      method: "DELETE",
    }
  );
}

// ---------------------------------------------------------------------------
// Inline milestone curation (DI-4B99678C / DO-7986A957). Wraps the
// per-encounter attach/detach endpoints with same-day grouping so a
// single milestone slot represents a "clinical day" rather than a
// single encounter row. The server still records one EpisodeMilestone
// per attached encounter; the orchestrator below loops over the
// per-day encounter group and aggregates the per-call results so the
// UI can report a single outcome to the reviewer.
//
// The helpers stay client-side for v1 (server endpoints are
// unchanged) so the existing role gate, audit trail, and date
// re-derive logic in the FastAPI handler are reused as-is.
// ---------------------------------------------------------------------------

export interface MilestoneAttachFailure {
  encounter_id: string;
  error: string;
}

export interface MilestoneDayResult {
  success: boolean;
  episode_id: string;
  milestone_type: string;
  date: string;
  attempted: string[];
  succeeded: string[];
  // Subset of `succeeded` whose edge already existed before the
  // attach, surfaced by the backend's already_linked short-circuit
  // (DI-F5E030ED). Useful so the multi-slot UI can say "1 added,
  // 2 already linked" without falsely claiming new writes.
  alreadyLinked: string[];
  failed: MilestoneAttachFailure[];
  derived_dates: EpisodeDerivedDates | null;
}

export interface MilestoneAttachDayBody {
  episodeId: string;
  milestoneType: string;
  date: string;
  encounterIds: string[];
}

export interface MilestoneDetachDayBody {
  episodeId: string;
  encounterIds: string[];
  // When set, only the :IS_PART_OF edge whose milestone_type matches
  // is removed. Leaves any other slots the encounter fills intact
  // -- DI-F5E030ED.
  milestoneType?: string | null;
}

/**
 * Attach every encounter from the same calendar day to one milestone
 * slot. Calls the per-encounter attach endpoint sequentially so a
 * partial failure leaves the graph in a coherent state and we can
 * return a precise list of which encounters did and did not attach.
 *
 * Per DI-4B99678C the milestone slot is (milestone_type, date), so
 * the caller MUST hand in the full set of encounters on that
 * calendar day. The orchestrator does NOT re-query the encounter
 * list -- it trusts the day group built by the UI component.
 */
export async function attachEncounterDayToMilestone(
  body: MilestoneAttachDayBody
): Promise<MilestoneDayResult> {
  const succeeded: string[] = [];
  const alreadyLinked: string[] = [];
  const failed: MilestoneAttachFailure[] = [];
  let derived: EpisodeDerivedDates | null = null;
  for (const encounterId of body.encounterIds) {
    try {
      const res = await attachEncounterToEpisode(body.episodeId, {
        encounter_id: encounterId,
        milestone_type: body.milestoneType,
      });
      succeeded.push(encounterId);
      if (res.already_linked) alreadyLinked.push(encounterId);
      if (res.derived_dates) derived = res.derived_dates;
    } catch (e) {
      failed.push({
        encounter_id: encounterId,
        error: e instanceof Error ? e.message : "Could not attach encounter.",
      });
    }
  }
  return {
    success: failed.length === 0 && succeeded.length > 0,
    episode_id: body.episodeId,
    milestone_type: body.milestoneType,
    date: body.date,
    attempted: body.encounterIds,
    succeeded,
    alreadyLinked,
    failed,
    derived_dates: derived,
  };
}

/**
 * Detach every encounter from the same calendar day. Used by the
 * Replace branch of the conflict flow (DI-4B99678C R-56B52B64) and
 * by the per-card "Remove from milestone" affordance.
 */
export async function detachEncounterDayFromMilestone(
  body: MilestoneDetachDayBody
): Promise<MilestoneDayResult> {
  const succeeded: string[] = [];
  const failed: MilestoneAttachFailure[] = [];
  let derived: EpisodeDerivedDates | null = null;
  for (const encounterId of body.encounterIds) {
    try {
      const res = await detachEncounterFromEpisode(
        body.episodeId,
        encounterId,
        { milestoneType: body.milestoneType ?? null }
      );
      succeeded.push(encounterId);
      derived = res.derived_dates;
    } catch (e) {
      failed.push({
        encounter_id: encounterId,
        error: e instanceof Error ? e.message : "Could not detach encounter.",
      });
    }
  }
  return {
    success: failed.length === 0,
    episode_id: body.episodeId,
    milestone_type: "",
    date: "",
    attempted: body.encounterIds,
    succeeded,
    alreadyLinked: [],
    failed,
    derived_dates: derived,
  };
}

// ---------------------------------------------------------------------------
// Multi-slot day attach (DI-F5E030ED). One encounter day can fill
// several milestone slots on the same EpisodeOfCare in a single
// reviewer action -- this helper loops over the slot list, calls
// the per-slot day-attach helper above, and returns one aggregated
// result per slot so the UI can render a clean summary banner.
// ---------------------------------------------------------------------------

export interface MilestoneAttachMultiSlotBody {
  episodeId: string;
  milestoneTypes: string[];
  date: string;
  encounterIds: string[];
}

export interface MilestoneMultiSlotResult {
  episodeId: string;
  date: string;
  perSlot: MilestoneDayResult[];
  // Number of (slot, encounter) pairs that resulted in a *new*
  // :IS_PART_OF edge being written.
  newlyLinked: number;
  // Number of (slot, encounter) pairs the backend short-circuited
  // because the edge already existed.
  alreadyLinked: number;
  // Number of (slot, encounter) pairs that errored out.
  failed: number;
  // Convenience: true iff every slot reported success.
  allSucceeded: boolean;
}

export interface CohortPercentile {
  from_step: string;
  to_step: string;
  p25: number;
  p50: number;
  p75: number;
  sample_size: number;
}

export interface EpisodeVariationDetail {
  episode_id: string;
  variation_flag: boolean | null;
  variation_score: number | null;
  variation_first_divergence: string | null;
  variation_outlier_steps: string[];
  variation_community_id: number | null;
  variation_compared_pairs: number | null;
  variation_observed_pairs: number | null;
  variation_attributed_node_type: string | null;
  variation_attributed_node_id: string | null;
  variation_attributed_node_name: string | null;
  variation_updated: string | null;
  cohort_percentiles: CohortPercentile[];
  cohort_size: number;
}

export async function fetchEpisodeVariation(
  episodeId: string
): Promise<EpisodeVariationDetail> {
  return fetchJson<EpisodeVariationDetail>(
    `${PROXY}/variation/episodes/${encodeURIComponent(episodeId)}`
  );
}

export interface VariationSiteSummary {
  total_episodes: number;
  flagged_episodes: number;
  by_first_divergence: { step: string; flagged_episodes: number }[];
  by_attributed_node: {
    node_type: string;
    node_id: string;
    node_name: string;
    flagged_episodes: number;
  }[];
}

export async function fetchVariationSummary(): Promise<VariationSiteSummary> {
  return fetchJson<VariationSiteSummary>(`${PROXY}/variation/summary`);
}

export interface VariationRunRequest {
  months?: number;
  min_sample_size?: number;
}

export interface VariationRunResult {
  episodes_considered: number;
  episodes_scored: number;
  episodes_flagged: number;
  episodes_attributed: number;
}

export async function runVariationForSite(
  body: VariationRunRequest = {}
): Promise<VariationRunResult> {
  return fetchJson<VariationRunResult>(`${PROXY}/variation/run-site`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export async function attachEncounterDayToMultipleMilestones(
  body: MilestoneAttachMultiSlotBody
): Promise<MilestoneMultiSlotResult> {
  const perSlot: MilestoneDayResult[] = [];
  for (const milestoneType of body.milestoneTypes) {
    const res = await attachEncounterDayToMilestone({
      episodeId: body.episodeId,
      milestoneType,
      date: body.date,
      encounterIds: body.encounterIds,
    });
    perSlot.push(res);
  }
  let newlyLinked = 0;
  let alreadyLinked = 0;
  let failed = 0;
  let allSucceeded = perSlot.length > 0;
  for (const r of perSlot) {
    newlyLinked += r.succeeded.length - r.alreadyLinked.length;
    alreadyLinked += r.alreadyLinked.length;
    failed += r.failed.length;
    if (!r.success) allSucceeded = false;
  }
  return {
    episodeId: body.episodeId,
    date: body.date,
    perSlot,
    newlyLinked,
    alreadyLinked,
    failed,
    allSucceeded,
  };
}
