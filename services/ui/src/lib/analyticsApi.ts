/**
 * API client for Analytics API and FHIR API.
 * Uses backend proxy (session cookie auth). Token stays server-side.
 *
 * Atlas trace:
 *   DO: DO-11A2361E
 *   Also implements: DO-A23404E0
 *   DI: DI-23822663, DI-F46D7A68
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-11A2361E")
 */
import type { TimelineEvent } from "@/lib/types";
import { triggerReauth } from "@/lib/api/client";

function resolveApiBase(): string {
  if (typeof window !== "undefined") return window.location.origin;
  return (process.env.INTERNAL_API_BASE || "http://localhost:8000").replace(/\/+$/, "");
}

const API_BASE = resolveApiBase();

const PROXY_BASE = `${API_BASE}/api/proxy`;
const ANALYTICS_BASE = PROXY_BASE;
const FHIR_BASE = PROXY_BASE;

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
    throw new Error((err as { detail?: string }).detail || `Request failed (${res.status})`);
  }
  if (res.status === 204) {
    return undefined as unknown as T;
  }
  return res.json();
}

// ── Analytics: Dashboards ──

export async function fetchEpisodeSummary(orgId?: string, dateFrom?: string, dateTo?: string) {
  const p = new URLSearchParams();
  if (orgId) p.set("org_id", orgId);
  if (dateFrom) p.set("date_from", dateFrom);
  if (dateTo) p.set("date_to", dateTo);
  const qs = p.size ? `?${p}` : "";
  return fetchJson<
    Array<{ condition_type: string; status: string; count: number }>
  >(`${ANALYTICS_BASE}/analytics/episodes/summary${qs}`);
}

export async function fetchDiagnosedSummary(orgId?: string, dateFrom?: string, dateTo?: string) {
  const p = new URLSearchParams();
  if (orgId) p.set("org_id", orgId);
  if (dateFrom) p.set("date_from", dateFrom);
  if (dateTo) p.set("date_to", dateTo);
  const qs = p.size ? `?${p}` : "";
  return fetchJson<
    Array<{ cancer_type: string; count: number }>
  >(`${ANALYTICS_BASE}/analytics/episodes/diagnosed${qs}`);
}

export async function fetchEpisodeTimeline(patientId?: string, orgId?: string, includeMerged?: boolean) {
  const params = new URLSearchParams();
  if (patientId) params.set("patient_id", patientId);
  if (orgId) params.set("org_id", orgId);
  if (includeMerged) params.set("include_merged", "true");
  const qs = params.toString();
  return fetchJson<
    Array<{
      episode_id: string;
      patient_id?: string;
      condition_type: string;
      status: string;
      referral_date?: string;
      confidence?: number;
      agent_reasoning?: string;
      needs_review?: boolean;
      merged_into?: string;
      merged_from?: string[];
      consolidation_reasoning?: string;
      referral_route?: string;
      place_of_presentation?: string;
      safety_netting_recorded?: boolean;
      inferred_outcome?: 'cancer' | 'benign' | null;
      inferred_outcome_date?: string | null;
      inferred_confidence?: number | null;
      inference_signals?: string | null;
      milestones?: Array<{
        encounter_id: string;
        date: string;
        milestone_type: string;
      }>;
    }>
  >(`${ANALYTICS_BASE}/analytics/episodes/timeline${qs ? `?${qs}` : ""}`);
}

export async function closeEpisode(
  episodeId: string,
  status: "closed" | "completed",
  reason: string,
): Promise<{ success: boolean; episode_id: string }> {
  return fetchJson(`${ANALYTICS_BASE}/analytics/episodes/${encodeURIComponent(episodeId)}/status`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status, reason }),
  });
}

export async function mergeEpisodes(
  primaryEpisodeId: string,
  secondaryEpisodeIds: string[],
  reason: string,
): Promise<{ success: boolean; primary_episode_id: string; merged_count: number }> {
  return fetchJson(`${ANALYTICS_BASE}/analytics/episodes/merge`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      primary_episode_id: primaryEpisodeId,
      secondary_episode_ids: secondaryEpisodeIds,
      reason,
    }),
  });
}

export async function editMilestone(
  episodeId: string,
  encounterId: string,
  milestoneType: string,
): Promise<{ success: boolean; encounter_id: string; milestone_type: string }> {
  return fetchJson(
    `${ANALYTICS_BASE}/analytics/episodes/${encodeURIComponent(episodeId)}/milestones/${encodeURIComponent(encounterId)}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ milestone_type: milestoneType }),
    },
  );
}

export async function rebuildPatientEpisodes(
  patientId: string,
  deleteExisting = true,
): Promise<{
  success: boolean;
  patient_id: string;
  episodes_created: number;
  episodes_completed: number;
  episodes_merged: number;
  encounters_linked: number;
  episode_ids: string[];
}> {
  return fetchJson(`${ANALYTICS_BASE}/analytics/episodes/rebuild`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ patient_id: patientId, delete_existing: deleteExisting }),
  });
}

export interface SafetyNetAlert {
  id: string;
  type: string;
  rule_name?: string;
  severity: string;
  status?: string;
  guideline?: string;
  description: string;
  suggested_action?: string;
  match_percent?: number;
  actioned?: boolean;
  needs_review?: boolean;
  created_at?: string;
  episode_id?: string;
  condition_type?: string;
  encounter_id?: string;
  encounter_date?: string;
  patient_id?: string;
}

export interface SafetyNetWorklistMilestone {
  encounter_id: string;
  date: string;
  milestone_type: string;
}

export interface SafetyNetWorklistItem {
  patient_id: string;
  gender?: string;
  birth_date?: string;
  episode_id: string;
  condition_type?: string;
  status?: string;
  referral_date?: string;
  referral_route?: string;
  safety_netting_recorded?: boolean;
  needs_review?: boolean;
  confidence?: number;
  agent_reasoning?: string;
  last_encounter_date?: string;
  milestones: SafetyNetWorklistMilestone[];
  alerts: SafetyNetAlert[];
}

export async function fetchSafetyNetAlerts(orgId?: string): Promise<SafetyNetAlert[]> {
  const params = orgId ? `?org_id=${orgId}` : "";
  return fetchJson<SafetyNetAlert[]>(
    `${ANALYTICS_BASE}/analytics/safety-netting/alerts${params}`,
  );
}

export async function fetchSafetyNetWorklist(orgId?: string): Promise<SafetyNetWorklistItem[]> {
  const params = orgId ? `?org_id=${orgId}` : "";
  return fetchJson<SafetyNetWorklistItem[]>(
    `${ANALYTICS_BASE}/analytics/safety-netting/worklist${params}`,
  );
}

export async function actionSafetyNetAlert(
  alertId: string,
  actioned: boolean,
): Promise<{ success: boolean }> {
  return fetchJson<{ success: boolean }>(
    `${ANALYTICS_BASE}/analytics/safety-netting/alerts/${alertId}/action`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ actioned }),
    },
  );
}

// ── Analytics: CCI ──

export async function fetchPatientCCI(patientId: string) {
  return fetchJson<{
    patient_id: string;
    cci_score: number;
    matched_conditions: Array<{
      condition: string;
      weight: number;
      concept_name: string;
      concept_id: string;
    }>;
  }>(`${ANALYTICS_BASE}/analytics/cci/${patientId}`);
}

// ── Analytics: Benchmarks ──

export async function fetchKPIBenchmarks(orgId?: string, dateFrom?: string, dateTo?: string) {
  const p = new URLSearchParams();
  if (orgId) p.set("org_id", orgId);
  if (dateFrom) p.set("date_from", dateFrom);
  if (dateTo) p.set("date_to", dateTo);
  const qs = p.toString();
  return fetchJson<
    Array<{
      avg_days_to_referral: number | null;
      n_days_to_referral?: number | null;
      avg_days_to_diagnosis: number | null;
      n_days_to_diagnosis?: number | null;
      avg_days_to_treatment: number | null;
      n_days_to_treatment?: number | null;
      avg_consultations: number | null;
      episode_count: number;
      inferred_diagnosis_count: number | null;
    }>
  >(`${ANALYTICS_BASE}/analytics/benchmarks/kpis${qs ? `?${qs}` : ""}`);
}

export async function fetchKPITrends(metric?: string, orgId?: string) {
  const params = new URLSearchParams();
  if (metric) params.set("metric", metric);
  if (orgId) params.set("org_id", orgId);
  const qs = params.toString();
  return fetchJson<
    Array<{ month: string; avg_val: number; cnt: number }>
  >(`${ANALYTICS_BASE}/analytics/benchmarks/trends${qs ? `?${qs}` : ""}`);
}

// ── Analytics: IMD ──

export async function fetchIMDData(postcode: string) {
  return fetchJson<Record<string, string>>(
    `${ANALYTICS_BASE}/analytics/imd/${encodeURIComponent(postcode)}`,
  );
}

// ── FHIR: Measures ──

export async function fetchMeasures(name?: string) {
  const params = name ? `?name=${encodeURIComponent(name)}` : "";
  return fetchJson<{
    resourceType: string;
    type: string;
    total: number;
    entry: Array<{ resource: Record<string, unknown> }>;
  }>(`${FHIR_BASE}/fhir/Measure${params}`);
}

export async function evaluateMeasure(measureId: string, orgId?: string) {
  const params = orgId ? `?org_id=${orgId}` : "";
  return fetchJson<Record<string, unknown>>(
    `${FHIR_BASE}/fhir/Measure/${measureId}/$evaluate-measure${params}`,
  );
}

// ── Analytics: Cohorts ──

export interface CohortFilter {
  org_id?: string;
  date_range_start?: string;
  date_range_end?: string;
  condition_codes?: string[];
  episode_status?: string[];
  age_min?: number;
  age_max?: number;
  sex?: "female" | "male" | string;
  smoking_status?: "current_smoker" | "ever_smoker";
  custom_cypher?: string;
  // Patient-finder extensions (DI-LEO-AI-230)
  imd_decile_min?: number;
  imd_decile_max?: number;
  encounter_count_min?: number;
  encounter_count_max?: number;
  encounter_count_window_months?: number;
  episode_domain?: string;
  episode_subdomain?: string;
  episode_outcome?:
    | "confirmed_cancer"
    | "two_week_wait_route"
    | "benign"
    | "in_progress"
    | "any_open";
}

export interface CohortPreviewResponse {
  patient_count: number;
  sample_patient_ids: string[];
}

export interface Cohort {
  cohort_id: string;
  name: string;
  description: string;
  filters: CohortFilter;
  patient_count: number;
  created_at?: string;
}

export interface CohortPatients {
  cohort_id: string;
  patient_ids: string[];
  total: number;
}

export async function createCohort(
  name: string,
  description: string,
  filters: CohortFilter,
): Promise<Cohort> {
  const created = await fetchJson<Cohort>(
    `${ANALYTICS_BASE}/analytics/cohorts`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, description, filters }),
    },
  );
  invalidateCohortCache();
  return created;
}

// In-flight + short-TTL cache for the cohort list. Patient finder dialogs
// call fetchCohorts() on every mount; without caching this becomes one
// extra round-trip every time a clinician opens the picker.
const _COHORT_TTL_MS = 60 * 1000;
let _cohortCache: { fetchedAt: number; rows: Cohort[] } | null = null;
let _cohortInflight: Promise<Cohort[]> | null = null;

export async function fetchCohorts(): Promise<Cohort[]> {
  const now = Date.now();
  if (_cohortCache && now - _cohortCache.fetchedAt < _COHORT_TTL_MS) {
    return _cohortCache.rows;
  }
  if (_cohortInflight) return _cohortInflight;
  _cohortInflight = (async () => {
    try {
      const rows = await fetchJson<Cohort[]>(`${ANALYTICS_BASE}/analytics/cohorts`);
      _cohortCache = { fetchedAt: Date.now(), rows };
      return rows;
    } finally {
      _cohortInflight = null;
    }
  })();
  return _cohortInflight;
}

export function invalidateCohortCache(): void {
  _cohortCache = null;
}

export async function resolveCohort(cohortId: string): Promise<CohortPatients> {
  return fetchJson<CohortPatients>(
    `${ANALYTICS_BASE}/analytics/cohorts/${cohortId}/patients`,
  );
}

export async function deleteCohort(cohortId: string): Promise<{ success: boolean }> {
  const result = await fetchJson<{ success: boolean }>(
    `${ANALYTICS_BASE}/analytics/cohorts/${cohortId}`,
    { method: "DELETE" },
  );
  invalidateCohortCache();
  return result;
}

export async function previewCohort(
  filters: CohortFilter,
): Promise<CohortPreviewResponse> {
  return fetchJson<CohortPreviewResponse>(
    `${ANALYTICS_BASE}/analytics/cohorts/preview`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(filters),
    },
  );
}

// -- Analytics: Patient Finder (DI-LEO-AI-230) -------------------------

export interface PatientFinderRow {
  id: string;
  display_name?: string | null;
  nhs_number?: string | null;
  dob?: string | null;
  gender?: string | null;
  registered_org_id?: string | null;
}

export interface PatientFinderSearchResponse {
  results: PatientFinderRow[];
  total: number;
}

export interface PatientFinderEncounter {
  id: string;
  date?: string | null;
  encounter_type?: string | null;
  top_concept?: string | null;
  coded_count: number;
  /** Short snippet of the encounter narrative used by the picker's
   *  free-text search. Bounded server-side; null if no narrative. */
  text?: string | null;
}

export interface PatientFinderDocumentReference {
  id: string;
  date?: string | null;
  document_type?: string | null;
  source?: string | null;
  chunk_count: number;
  /** Short snippet of the document body (first chunk text or
   *  description) used by the picker's free-text search. */
  text?: string | null;
}

export interface PatientFinderChunk {
  id: string;
  ordinal: number;
  preview: string;
}

export async function searchPatients(
  q: string,
  limit = 20,
): Promise<PatientFinderSearchResponse> {
  const params = new URLSearchParams({ q, limit: String(limit) });
  return fetchJson<PatientFinderSearchResponse>(
    `${ANALYTICS_BASE}/analytics/patient-finder/search?${params}`,
  );
}

export async function patientsByFilter(
  filters: CohortFilter,
  limit = 50,
  offset = 0,
): Promise<PatientFinderSearchResponse> {
  const params = new URLSearchParams({
    filters: JSON.stringify(filters),
    limit: String(limit),
    offset: String(offset),
  });
  return fetchJson<PatientFinderSearchResponse>(
    `${ANALYTICS_BASE}/analytics/patient-finder/by-filter?${params}`,
  );
}

export async function patientsByCohort(
  cohortId: string,
  limit = 50,
  offset = 0,
): Promise<PatientFinderSearchResponse> {
  const params = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
  });
  return fetchJson<PatientFinderSearchResponse>(
    `${ANALYTICS_BASE}/analytics/patient-finder/by-cohort/${encodeURIComponent(
      cohortId,
    )}?${params}`,
  );
}

export async function listPatientEncounters(
  patientId: string,
  limit = 100,
): Promise<PatientFinderEncounter[]> {
  const params = new URLSearchParams({ limit: String(limit) });
  return fetchJson<PatientFinderEncounter[]>(
    `${ANALYTICS_BASE}/analytics/patient-finder/${encodeURIComponent(
      patientId,
    )}/encounters?${params}`,
  );
}

export async function listPatientDocumentReferences(
  patientId: string,
  limit = 100,
): Promise<PatientFinderDocumentReference[]> {
  const params = new URLSearchParams({ limit: String(limit) });
  return fetchJson<PatientFinderDocumentReference[]>(
    `${ANALYTICS_BASE}/analytics/patient-finder/${encodeURIComponent(
      patientId,
    )}/document-references?${params}`,
  );
}

export async function listDocumentReferenceChunks(
  documentReferenceId: string,
  limit = 500,
): Promise<PatientFinderChunk[]> {
  const params = new URLSearchParams({ limit: String(limit) });
  return fetchJson<PatientFinderChunk[]>(
    `${ANALYTICS_BASE}/analytics/document-references/${encodeURIComponent(
      documentReferenceId,
    )}/chunks?${params}`,
  );
}

// ── Analytics: Domains (two-level hierarchy) ──

export interface DomainSummary {
  id: string;
  name: string;
  description: string;
  subdomain_count: number;
  source?: "nice" | "platform" | "tenant";
  episode_detector?: boolean;
}

export interface SubdomainSummary {
  name: string;
  description: string;
  milestone_type?: string;
  time_window_months?: number;
  semantic_tags: string[];
  assertion_filter?: string[];
  constructs?: SubdomainConstruct[];
  construct_count?: number;
  concept_count: number;
  /** Total IS_A descendants across all stored concepts. 0 means all concepts are leaf nodes. */
  descendant_count?: number;
}

export interface DomainDetail extends DomainSummary {
  subdomains: SubdomainSummary[];
}

export interface SubdomainConcept {
  concept_id: number;
  term: string;
  preferred_term: string;
  semantic_tag?: string;
  subdomain: string;
  guideline_synonyms?: string[];
  /** Number of direct IS_A children in SNOMED — 0 means leaf, >0 means broader concept */
  child_count?: number;
  /** Key linking to ncda_2018_benchmarks.json (e.g. comorbidity_hypertension_pct) */
  benchmark_key?: string;
}

export interface SubdomainConstructRole {
  role: string;
  concept_ids: number[];
  required: boolean;
}

export interface SubdomainConstruct {
  id: string;
  display_name: string;
  description?: string;
  logic: "ALL" | "ANY";
  roles: SubdomainConstructRole[];
}

export interface SubdomainDetail extends SubdomainSummary {
  concepts: SubdomainConcept[];
}

export interface SubdomainExportConcept {
  concept_id: number;
  term: string;
  synonyms: string[];
  child_count?: number;
  children?: Array<{ concept_id: number; term: string }>;
}

export interface SubdomainExport {
  domain_id: string;
  subdomain: string;
  include_children: boolean;
  expansion_depth?: number;
  concepts: SubdomainExportConcept[];
}

export interface SubdomainMembershipItem {
  domain_id: string;
  domain_name: string;
  subdomain_name: string;
  subdomain_label: string;
  is_member: boolean;
}

export async function fetchConceptSubdomainMemberships(
  conceptId: string,
): Promise<SubdomainMembershipItem[]> {
  const data = await fetchJson<{ concept_id: string; subdomains: SubdomainMembershipItem[] }>(
    `${ANALYTICS_BASE}/analytics/concepts/${encodeURIComponent(conceptId)}/subdomain-memberships`,
  );
  return data.subdomains;
}

export async function fetchDomains(source?: "nice" | "platform" | "tenant"): Promise<DomainSummary[]> {
  const url = source
    ? `${ANALYTICS_BASE}/analytics/domains?source=${source}`
    : `${ANALYTICS_BASE}/analytics/domains`;
  return fetchJson<DomainSummary[]>(url);
}

export async function fetchDomain(domainId: string): Promise<DomainDetail> {
  return fetchJson<DomainDetail>(
    `${ANALYTICS_BASE}/analytics/domains/${encodeURIComponent(domainId)}`,
  );
}

export async function createDomain(
  name: string,
  description = "",
  episodeDetector = false,
): Promise<DomainSummary> {
  return fetchJson<DomainSummary>(`${ANALYTICS_BASE}/analytics/domains`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, description, episode_detector: episodeDetector }),
  });
}

export async function updateDomain(
  domainId: string,
  update: { name?: string; description?: string; episode_detector?: boolean },
): Promise<DomainSummary> {
  return fetchJson<DomainSummary>(
    `${ANALYTICS_BASE}/analytics/domains/${encodeURIComponent(domainId)}`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(update),
    },
  );
}

export async function deleteDomain(domainId: string): Promise<void> {
  await fetchJson<void>(
    `${ANALYTICS_BASE}/analytics/domains/${encodeURIComponent(domainId)}`,
    { method: "DELETE" },
  );
}

// ── Subdomains ──

export async function createSubdomain(
  domainId: string,
  name: string,
  options?: {
    description?: string;
    milestone_type?: string;
    time_window_months?: number;
    semantic_tags?: string[];
  },
): Promise<SubdomainSummary> {
  return fetchJson<SubdomainSummary>(
    `${ANALYTICS_BASE}/analytics/domains/${encodeURIComponent(domainId)}/subdomains`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name,
        description: options?.description ?? "",
        milestone_type: options?.milestone_type,
        time_window_months: options?.time_window_months,
        semantic_tags: options?.semantic_tags ?? [],
      }),
    },
  );
}

export async function fetchSubdomain(
  domainId: string,
  subdomainName: string,
): Promise<SubdomainDetail> {
  return fetchJson<SubdomainDetail>(
    `${ANALYTICS_BASE}/analytics/domains/${encodeURIComponent(domainId)}/subdomains/${encodeURIComponent(subdomainName)}`,
  );
}

export async function deleteSubdomain(
  domainId: string,
  subdomainName: string,
): Promise<void> {
  await fetchJson<void>(
    `${ANALYTICS_BASE}/analytics/domains/${encodeURIComponent(domainId)}/subdomains/${encodeURIComponent(subdomainName)}`,
    { method: "DELETE" },
  );
}

export async function updateSubdomain(
  domainId: string,
  subdomainName: string,
  update: {
    description?: string;
    milestone_type?: string;
    time_window_months?: number;
    semantic_tags?: string[];
    assertion_filter?: string[];
    constructs?: SubdomainConstruct[];
  },
): Promise<SubdomainSummary> {
  return fetchJson<SubdomainSummary>(
    `${ANALYTICS_BASE}/analytics/domains/${encodeURIComponent(domainId)}/subdomains/${encodeURIComponent(subdomainName)}`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(update),
    },
  );
}

export async function fetchSubdomainConstructs(
  domainId: string,
  subdomainName: string,
): Promise<SubdomainConstruct[]> {
  return fetchJson<SubdomainConstruct[]>(
    `${ANALYTICS_BASE}/analytics/domains/${encodeURIComponent(domainId)}/subdomains/${encodeURIComponent(subdomainName)}/constructs`,
  );
}

export async function replaceSubdomainConstructs(
  domainId: string,
  subdomainName: string,
  constructs: SubdomainConstruct[],
): Promise<SubdomainSummary> {
  return fetchJson<SubdomainSummary>(
    `${ANALYTICS_BASE}/analytics/domains/${encodeURIComponent(domainId)}/subdomains/${encodeURIComponent(subdomainName)}/constructs`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(constructs),
    },
  );
}

export async function addConceptToSubdomain(
  domainId: string,
  subdomainName: string,
  conceptId: number,
  term: string,
  synonyms: string[] = [],
  benchmarkKey?: string,
): Promise<SubdomainDetail> {
  return fetchJson<SubdomainDetail>(
    `${ANALYTICS_BASE}/analytics/domains/${encodeURIComponent(domainId)}/subdomains/${encodeURIComponent(subdomainName)}/concepts`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        concept_id: conceptId,
        term,
        synonyms,
        ...(benchmarkKey ? { benchmark_key: benchmarkKey } : {}),
      }),
    },
  );
}

export async function removeConceptFromSubdomain(
  domainId: string,
  subdomainName: string,
  conceptId: number,
): Promise<SubdomainDetail> {
  return fetchJson<SubdomainDetail>(
    `${ANALYTICS_BASE}/analytics/domains/${encodeURIComponent(domainId)}/subdomains/${encodeURIComponent(subdomainName)}/concepts/${conceptId}`,
    { method: "DELETE" },
  );
}

export async function exportSubdomain(
  domainId: string,
  subdomainName: string,
  includeChildren: boolean,
  depth = 3,
): Promise<SubdomainExport> {
  const params = new URLSearchParams({
    include_children: String(includeChildren),
    depth: String(depth),
  });
  return fetchJson<SubdomainExport>(
    `${ANALYTICS_BASE}/analytics/domains/${encodeURIComponent(domainId)}/subdomains/${encodeURIComponent(subdomainName)}/export?${params}`,
  );
}

// -- Patient coding timeline --

export async function fetchPatientCodingTimeline(patientId: string): Promise<TimelineEvent[]> {
  return fetchJson<TimelineEvent[]>(
    `${API_BASE}/api/patients/${encodeURIComponent(patientId)}/timeline`,
  );
}

// ── Analytics: NCDA Audit ──

/** Benchmark values for a single metric, keyed by comparison level. */
export interface BenchmarkMetricValues {
  practice?: number | null;
  national: number | null;
  alliance: number | null;
}

/** The benchmark overlay returned alongside live data. */
export interface AuditBenchmark {
  set_id: string;
  set_name: string;
  /** metric_id → {national, alliance} */
  metrics: Record<string, BenchmarkMetricValues>;
}

/** Multi-scope envelope wrapping any section's live data and optional benchmark. */
export interface AuditSectionResult<T> {
  scopes: {
    /** Live data for the selected practice (or England when no org is selected). */
    practice: T | null;
    /** Live data aggregated to the Cancer Alliance level (null when no org selected). */
    alliance_live: T | null;
    /** Live data for all patients – England (null when no org selected). */
    england_live: T | null;
  };
  benchmark: AuditBenchmark | null;
}

export interface AuditSummary {
  total_episodes: number;
  active_episodes: number;
  confirmed_cancers: number;
  confirmed_cancers_via_2ww?: number;
  confirmed_cancers_via_2ww_pct?: number | null;
  confirmed_cancers_screening_programme?: number;
  confirmed_cancers_excluding_screening?: number;
  confirmed_cancers_via_2ww_excluding_screening?: number;
  confirmed_cancers_via_2ww_excluding_screening_pct?: number | null;
  // NCDA cohort breakdown from ncda_detector.
  cohort_1a_n?: number;
  cohort_1b_n?: number;
  cohort_3_n?: number;
  // MECE lifecycle decomposition (DI-105A4EC7). Sum of the four
  // *_episodes fields equals total_cohort_episodes by construction.
  total_cohort_episodes?: number;
  active_lifecycle_episodes?: number;
  in_review_episodes?: number;
  cancer_excluded_episodes?: number;
  confirmed_cancer_episodes?: number;
  // All-cohort totals for the dashboard "Cohort" summary card.
  // total_cohort_patients counts every Patient in scope (matches
  // Mission Control's cohort denominator). patients_with_pathway
  // counts those with at least one EpisodeOfCare. The difference is
  // surfaced as patients_without_pathway and clickable to
  // /care/patients?lifecycle_bucket=no_pathway. See DI-CA1B4C6E.
  total_cohort_patients?: number;
  total_cohort_patients_with_pathway?: number;
  patients_without_pathway?: number;
  total_cohort_episodes_all?: number;
  median_pci_days: number | null;
  median_di_days: number | null;
  avg_consultations: number | null;
  // Headline Section 8 rate: confirmed-cancer episodes with a
  // strong (free-text "safety netted" / "safety net advice" OR Y281b
  // Read code) OR medium (PRISM "Advice if worsens" template field)
  // safety-netting record. Denominator is the canonical
  // confirmed-cancer cohort. See libs/oncology/safety_netting.py.
  safety_netting_pct: number | null;
  /** Numerator behind safety_netting_pct (strong + medium hits). */
  safety_netting_recorded_n?: number;
  /** Strict subset: free-text safety-net OR Y281b code only. */
  safety_netting_strong_pct?: number | null;
  safety_netting_strong_n?: number;
  /** Per-signal breakdown for the tooltip ("X strong, Y PRISM-only, Z generic advice, W none"). */
  safety_netting_signal_counts?: {
    strong: number;
    medium: number;
    advice_only: number;
    none: number;
  };
  /** Confirmed-cancer denominator behind every safety_netting_* field. */
  safety_netting_denominator?: number;
  /** Legacy field — referral-gated subset / total_episodes. Do NOT
   * surface as the headline; kept for backwards-compat with older
   * snapshot tests that still assert the old denominator. */
  safety_netting_legacy_pct?: number | null;
  // ---- Care obstructions (rejected referrals, DNAs, cancellations) ----
  // Headline rate of confirmed-cancer episodes whose milestone window
  // contains a rejected referral (XaQgL), DNA (XacSG / XaF81 / Xa1kG),
  // cancellation or softer access barrier. Denominator is the canonical
  // confirmed-cancer cohort (matches safety-netting). See
  // libs/oncology/care_obstruction.py for the signal hierarchy.
  care_obstruction_pct?: number | null;
  /** Numerator behind care_obstruction_pct (any non-none signal). */
  care_obstruction_recorded_n?: number;
  /** Severe subset: rejection + dna only — events that hard-stop the workup. */
  care_obstruction_severe_pct?: number | null;
  care_obstruction_severe_n?: number;
  /** Per-signal breakdown for the tooltip + breakdown dialog. */
  care_obstruction_signal_counts?: {
    rejection: number;
    dna: number;
    cancellation: number;
    access_barrier: number;
    none: number;
  };
  /** Confirmed-cancer denominator behind every care_obstruction_* field. */
  care_obstruction_denominator?: number;
  // ---- Pathway-relatedness telemetry --------------------------------
  // Care obstruction events go through a corpus-driven relatedness
  // classifier (see libs/oncology/care_obstruction.py) that drops
  // clearly-unrelated services (midwife / district nurse / phlebotomy
  // / urgent treatment centre / cardiac rehab / etc.) from the
  // headline.  Episodes are flagged "confirmed" when at least one
  // recorded obstruction matched an explicit cancer-pathway marker
  // (2WW, FTR, oncology, MDT, or the site-specific specialty).
  /** Number of confirmed-cancer episodes with at least one
   *  pathway-confirmed obstruction (subset of recorded_n). */
  care_obstruction_confirmed_n?: number;
  /** care_obstruction_confirmed_n / denominator * 100. */
  care_obstruction_confirmed_pct?: number | null;
  /** Total event count whose text contained an explicit cancer-
   *  pathway marker — informational, not used for the headline. */
  care_obstruction_confirmed_events?: number;
  /** Total event count that tripped an obstruction phrase but was
   *  filtered as clearly non-cancer (midwife, district nurse, UTC,
   *  cardiac rehab, etc.) and so is NOT in the headline.  Surfaced
   *  in the tooltip + dialog footer so the auditor can see how
   *  aggressive the filter is. */
  care_obstruction_unrelated_filtered_events?: number;
}

export interface AuditCancerTypeRow {
  cancer_type: string;
  n: number;
  pct: number;
}

export interface AuditCancerStageRow {
  stage_group: "early" | "late" | "unknown";
  n: number;
  pct: number;
}

export interface AuditCancerStageSummary {
  rows: AuditCancerStageRow[];
  by_stage_group: AuditCancerStageRow[];
  by_system: Array<{ staging_system: string; n: number }>;
  by_source: Array<{ staging_source: string; n: number }>;
  by_stage_group_detail: Array<{
    cancer_stage_group: string;
    staging_value?: string;
    stage_group?: "early" | "late" | "unknown";
    n: number;
  }>;
  by_cancer_type: Array<{
    cancer_type: string;
    stage_group: "early" | "late" | "unknown";
    n: number;
    pct: number;
  }>;
  coverage_pct: number;
  coverage_numerator: number;
  coverage_denominator: number;
}

export interface AuditDemographics {
  sex: Array<{ gender: string; n: number; pct: number }>;
  age_bands: Array<{ age_band: string; n: number; pct: number }>;
  median_age: number | null;
  ethnicity: Array<{ ethnicity: string; n: number; pct: number }>;
  // DI-87D92943: age x sex cross-tab so the demographics evolution view
  // can render a true population pyramid per calendar-year window. `pct`
  // is percentage of the total demographic population for that window
  // (not row-stochastic by gender), so cards stay directly comparable.
  age_band_by_sex: Array<{
    gender: string;
    age_band: string;
    n: number;
    pct: number;
  }>;
  /** Distinct patients per NCDA ethnicity SNOMED (DOCUMENTS domain ethnicity). */
  ethnicity_by_snomed: Array<{
    snomed: string;
    benchmark_key: string;
    preferred_term: string;
    n: number;
    pct: number;
  }>;
  /** Sum of sex-tab rows; cohort size for ethnicity radar denominators. */
  demographics_cohort_n: number;
  /** Distinct patients with at least one coded ethnicity link in the NCDA SNOMED set. */
  patients_with_ethnicity_snomed_n: number;
  /** patients_with_ethnicity_snomed_n as % of demographics_cohort_n; null when cohort is empty. */
  ethnicity_snomed_coverage_pct: number | null;
}

export interface AuditPlaceRow {
  place: string;
  n: number;
  pct: number;
}

/** Per-episode evidence row -- drives the evidence accordion in
 *  MultipleConsultationsSection.  `evidence_quotes` is null until the
 *  detector persists per-factor quotes (see plan "Out of scope"). */
export interface AuditConsultationEpisodeEvidence {
  episode_id: string;
  cancer_type: string;
  n: number | null;
  factors: string[];
  evidence_quotes: null;
}

/** NCDA Section 7 -- Haiku-enriched consultation data.
 *  Powered by ep.prior_consultations_* properties.
 *  NCDA-native polarity: `three_or_more_*` is the headline. */
export interface AuditConsultations {
  /** NCDA-native polarity: % with 3+ cancer-related consultations. */
  three_or_more_pct: number;
  three_or_more_n: number;
  /** Kept for benchmark-overlay compatibility. */
  fewer_than_3_pct: number;
  fewer_than_3_n: number;
  total_episodes: number;
  /** Episodes the Haiku enrichment has classified. */
  enriched_n: number;
  enriched_pct: number;
  /** Median + IQR from the per-episode prior_consultations_n distribution. */
  median_consultations: number | null;
  iqr_low: number | null;
  iqr_high: number | null;
  /** Consultation-count distribution -- drives the breakdown dialog histogram.
   *  Buckets 3-4, 5-7, 8+ are in NCDA "multiple consultations" territory (>= 3). */
  buckets?: {
    "0": number;
    "1": number;
    "2": number;
    "3-4": number;
    "5-7": number;
    "8+": number;
  };
  buckets_pct?: {
    "0": number;
    "1": number;
    "2": number;
    "3-4": number;
    "5-7": number;
    "8+": number;
  };
  /** Mean cancer-related contacts per enriched episode by contact type. */
  mean_per_episode?: {
    total: number;
    f2f: number;
    phone: number;
    nurse: number;
    email: number;
    specialist_clinic: number;
    home_visit: number;
    phlebotomy: number;
    result_review: number;
  };
  total_consultations?: number;
  unrelated_filtered_total?: number;
  /** Top NCDA factor codes ranked by frequency -- drives the "why" bar chart. */
  top_factors?: Array<{ factor: string; n: number }>;
  /** Per-cancer-type factor breakdown -- drives the heatmap.
   *  `{ "Breast": { "different_initial_diagnosis": 3, ... }, ... }` */
  factors_by_cancer_type?: Record<string, Record<string, number>>;
  /** Per-episode evidence list -- drives the evidence drawer. */
  episode_evidence?: AuditConsultationEpisodeEvidence[];
  /** Live breakdown by tumour site -- drives the cancer-type table. */
  by_cancer_type_live?: Array<{
    cancer_type: string;
    n_total: number;
    n_three_or_more: number;
    n_enriched: number;
    three_or_more_pct: number | null;
    mean_consultations: number | null;
  }>;
  /** Aggregated Claude Haiku 4.5 telemetry. */
  llm_cost_usd?: number;
  llm_input_tokens?: number;
  llm_output_tokens?: number;
  llm_calls?: number;
}

export interface AuditInvestigations {
  has_investigation_pct: number;
  no_investigation_pct: number;
  total_episodes: number;
  types: Array<{ type: string; n: number; pct: number }>;
}

export interface AuditReferralRow {
  referral_route: string;
  n: number;
  pct: number;
}

export interface AuditFastTrackReferralRow {
  referral_site: string;
  concept_id: string;
  n: number;
  pct: number;
}

export interface AuditNSSOutcomeItem {
  outcome: string;
  n: number;
}

export interface AuditNSSOutcomes {
  total_nss: number;
  cancer_diagnosed_n: number;
  outcomes: AuditNSSOutcomeItem[];
}

export interface AuditIntervalsPatient {
  episode_id: string;
  patient_id?: string | null;
  cancer_type?: string | null;
  pci_days?: number | null;
  di_days?: number | null;
  diag_is_inferred?: boolean | null;
  is_benign?: boolean | null;
}

export interface AuditIntervalStats {
  n: number | null;
  mean: number | null;
  median: number | null;
  q1: number | null;
  q3: number | null;
}

export interface AuditIntervalSplitStats {
  n: number;
  median: number | null;
  q1: number | null;
  q3: number | null;
}

export interface AuditIntervals {
  pci: AuditIntervalStats;
  pci_cancer: AuditIntervalSplitStats;
  pci_benign: AuditIntervalSplitStats;
  di: AuditIntervalStats;
  di_cancer: AuditIntervalSplitStats;
  di_benign: AuditIntervalSplitStats;
  patients: AuditIntervalsPatient[];
}

export interface AuditSafetyNetting {
  total_episodes: number;
  recorded_n: number;
  recorded_pct: number;
  not_recorded_pct: number;
  /** Per-signal counts (strong > medium > advice_only > none) — see
   * libs/oncology/safety_netting.py for the hierarchy. Drives the
   * Safety Netting "Open detail" dialog. */
  signal_counts?: {
    strong: number;
    medium: number;
    advice_only: number;
    none: number;
  };
  signal_pct?: {
    strong: number;
    medium: number;
    advice_only: number;
    none: number;
  };
  /** Strict subset (strong only): free-text "safety netted" / "safety
   * net advice" or Read code Y281b only — surfaced in the dialog
   * alongside the headline strong+medium rate. */
  strong_n?: number;
  strong_pct?: number;
}

/** Care-obstruction section result — mirrors AuditSafetyNetting shape. */
export interface AuditCareObstruction {
  total_episodes: number;
  recorded_n: number;
  recorded_pct: number;
  not_recorded_pct: number;
  /** Total number of obstruction events across all episodes — sum of
   * `care_obstruction_evidence_count` across the cohort. Useful for
   * the dialog footer ("X obstructions across Y episodes"). */
  total_events?: number;
  /** Per-signal counts (rejection > dna > cancellation > access_barrier
   * > none) — see libs/oncology/care_obstruction.py for the
   * hierarchy. Drives the Care Obstructions "Open detail" dialog. */
  signal_counts?: {
    rejection: number;
    dna: number;
    cancellation: number;
    access_barrier: number;
    none: number;
  };
  signal_pct?: {
    rejection: number;
    dna: number;
    cancellation: number;
    access_barrier: number;
    none: number;
  };
  /** Severe subset (rejection + dna): events that hard-stop the
   * workup. Surfaced in the dialog header alongside the headline. */
  severe_n?: number;
  severe_pct?: number;
  // ---- Pathway-relatedness telemetry --------------------------------
  // Same definition as the AuditSummary fields above — see
  // libs/oncology/care_obstruction.py.
  /** Episodes with at least one pathway-confirmed obstruction. */
  confirmed_n?: number;
  confirmed_pct?: number;
  /** Total event count whose text contained an explicit cancer-pathway
   *  marker (informational; not used for the headline). */
  confirmed_events?: number;
  /** Total events filtered as clearly non-cancer (midwife / district
   *  nurse / phlebotomy / UTC / cardiac rehab / etc.) and so are
   *  NOT in the headline.  Surfaced in the dialog footer. */
  unrelated_filtered_events?: number;
}


export interface AuditComorbidityRow {
  condition: string;
  n: number;
  pct: number;
  /** Key linking to ncda_2018_benchmarks.json (e.g. comorbidity_hypertension_pct) */
  benchmark_key?: string;
}

/** Registry order radar axes (same SNOMED rollup as bar chart). */
export interface AuditComorbidityRadarRow {
  condition: string;
  n: number;
  pct: number | null;
  benchmark_key?: string | null;
}

export interface AuditComorbidities {
  comorbidities: AuditComorbidityRow[];
  /** Stable-order axes for multimorbidity radar (may be omitted by older APIs). */
  radar?: AuditComorbidityRadarRow[];
  total_patients: number;
}

export interface AuditComorbidityBreakdownSlice {
  slice_key: string;
  slice_label: string;
  cohort_n: number;
  rows: AuditComorbidityRow[];
}

export interface AuditComorbiditiesDrilldown {
  total_patients: number;
  by_age_band: AuditComorbidityBreakdownSlice[];
  by_gender: AuditComorbidityBreakdownSlice[];
  by_referral_outcome: AuditComorbidityBreakdownSlice[];
}

// ---------------------------------------------------------------------------
// Symptoms (DO-D5B9FE5F / DI-6E1B71A4)
// ---------------------------------------------------------------------------

/** Stable axis entry for the symptoms heatmap and tables. */
export interface AuditSymptomAxisEntry {
  key: string;
  symptom: string;
}

/** Overall row for the leading bar/heatmap visualisation. */
export interface AuditSymptomRow {
  symptom: string;
  n: number;
  pct: number;
}

/**
 * Long-format heatmap cell. ``cohort_n`` is the denominator of patients
 * inside ``bucket_label`` (e.g. cancer-type bucket). ``pct`` is the
 * symptom prevalence within that bucket.
 */
export interface AuditSymptomHeatmapCell {
  bucket_key: string;
  bucket_label: string;
  cohort_n: number;
  symptom: string;
  n: number;
  pct: number;
}

/**
 * Clinical PPV row: for a given (suspected cancer type, symptom) pair,
 * how many patients had the feature and how many of those got diagnosed.
 *
 * PPV = patients_with_cancer / patients_with_feature.
 */
export interface AuditSymptomPpvRow {
  cancer_type: string;
  symptom: string;
  patients_with_feature: number;
  patients_with_cancer: number;
  ppv_pct: number;
}

/**
 * Referral-cohort PPV row by suspected cancer type. ``provisional`` is
 * true when the cohort still contains unresolved or following-year
 * diagnoses.
 */
export interface AuditPpvByCancerTypeRow {
  cancer_type: string;
  referrals_n: number;
  diagnosed_in_year_n: number;
  no_cancer_in_year_n: number;
  diagnosed_following_year_n: number;
  unresolved_n: number;
  ppv_pct: number | null;
  provisional: boolean;
}

export interface AuditSymptoms {
  total_referrals: number;
  cohort_n: number;
  /**
   * Clinical PPV table: cancer_type × symptom, sorted by cancer type then
   * patients_with_feature descending. Only rows where
   * patients_with_feature > 0 are included.
   */
  rows: AuditSymptomPpvRow[];
  /** Referral-cohort PPV per suspected cancer type (for hero cards). */
  ppv_by_suspected_cancer_type: AuditPpvByCancerTypeRow[];
}

export interface AuditSymptomBreakdownSlice {
  slice_key: string;
  slice_label: string;
  cohort_n: number;
  rows: AuditSymptomRow[];
}

export interface AuditSymptomsDrilldown {
  total_patients: number;
  symptom_axis: AuditSymptomAxisEntry[];
  by_age_band: AuditSymptomBreakdownSlice[];
  by_gender: AuditSymptomBreakdownSlice[];
  by_suspected_cancer_type: AuditSymptomBreakdownSlice[];
  by_diagnosed_cancer_type: AuditSymptomBreakdownSlice[];
}

export interface AuditAvoidableDelays {
  total_episodes: number;
  avoidable_delay_n: number;
  avoidable_delay_pct: number;
  delay_before_presentation_pct: number | null;
  delay_pres_to_referral_pct: number | null;
  delay_after_referral_pct: number | null;
}

export interface BenchmarkSetSummary {
  id: string;
  name: string;
  source: string;
  audit_year: string | null;
  effective_from: string | null;
  effective_to: string | null;
}

function _auditParams(
  orgId?: string,
  dateFrom?: string,
  dateTo?: string,
  benchmarkSetId?: string,
): string {
  const p = new URLSearchParams();
  if (orgId) p.set("org_id", orgId);
  if (dateFrom) p.set("date_from", dateFrom);
  if (dateTo) p.set("date_to", dateTo);
  if (benchmarkSetId) p.set("benchmark_set_id", benchmarkSetId);
  return p.size ? `?${p}` : "";
}

export async function fetchBenchmarkSets(): Promise<BenchmarkSetSummary[]> {
  return fetchJson<BenchmarkSetSummary[]>(`${FHIR_BASE}/benchmarks/sets`);
}

export async function fetchAuditSummary(orgId?: string, dateFrom?: string, dateTo?: string): Promise<AuditSummary> {
  return fetchJson<AuditSummary>(`${ANALYTICS_BASE}/analytics/audit/summary${_auditParams(orgId, dateFrom, dateTo)}`);
}

export async function fetchAuditCancerType(
  orgId?: string, dateFrom?: string, dateTo?: string, benchmarkSetId?: string,
): Promise<AuditSectionResult<AuditCancerTypeRow[]>> {
  return fetchJson(`${ANALYTICS_BASE}/analytics/audit/cancer-type${_auditParams(orgId, dateFrom, dateTo, benchmarkSetId)}`);
}

export async function fetchAuditCancerStage(
  orgId?: string, dateFrom?: string, dateTo?: string, benchmarkSetId?: string,
): Promise<AuditSectionResult<AuditCancerStageSummary>> {
  return fetchJson(`${ANALYTICS_BASE}/analytics/audit/cancer-stage${_auditParams(orgId, dateFrom, dateTo, benchmarkSetId)}`);
}

export async function fetchAuditDemographics(
  orgId?: string, dateFrom?: string, dateTo?: string, benchmarkSetId?: string,
): Promise<AuditSectionResult<AuditDemographics>> {
  return fetchJson(`${ANALYTICS_BASE}/analytics/audit/demographics${_auditParams(orgId, dateFrom, dateTo, benchmarkSetId)}`);
}

export async function fetchAuditPlaceOfPresentation(
  orgId?: string, dateFrom?: string, dateTo?: string, benchmarkSetId?: string,
): Promise<AuditSectionResult<AuditPlaceRow[]>> {
  return fetchJson(`${ANALYTICS_BASE}/analytics/audit/place-of-presentation${_auditParams(orgId, dateFrom, dateTo, benchmarkSetId)}`);
}

export async function fetchAuditConsultations(
  orgId?: string, dateFrom?: string, dateTo?: string, benchmarkSetId?: string,
): Promise<AuditSectionResult<AuditConsultations>> {
  return fetchJson(`${ANALYTICS_BASE}/analytics/audit/consultations${_auditParams(orgId, dateFrom, dateTo, benchmarkSetId)}`);
}

export async function fetchAuditInvestigations(
  orgId?: string, dateFrom?: string, dateTo?: string, benchmarkSetId?: string,
): Promise<AuditSectionResult<AuditInvestigations>> {
  return fetchJson(`${ANALYTICS_BASE}/analytics/audit/investigations${_auditParams(orgId, dateFrom, dateTo, benchmarkSetId)}`);
}

export async function fetchAuditReferrals(
  orgId?: string, dateFrom?: string, dateTo?: string, benchmarkSetId?: string,
): Promise<AuditSectionResult<AuditReferralRow[]>> {
  return fetchJson(`${ANALYTICS_BASE}/analytics/audit/referrals${_auditParams(orgId, dateFrom, dateTo, benchmarkSetId)}`);
}

export async function fetchAuditFastTrackReferrals(
  orgId?: string, dateFrom?: string, dateTo?: string, benchmarkSetId?: string,
): Promise<AuditSectionResult<AuditFastTrackReferralRow[]>> {
  return fetchJson(`${ANALYTICS_BASE}/analytics/audit/fast-track-referrals${_auditParams(orgId, dateFrom, dateTo, benchmarkSetId)}`);
}

export async function fetchAuditNSSOutcomes(
  orgId?: string, dateFrom?: string, dateTo?: string,
): Promise<AuditNSSOutcomes> {
  return fetchJson(`${ANALYTICS_BASE}/analytics/audit/fast-track-referrals/nss-outcomes${_auditParams(orgId, dateFrom, dateTo)}`);
}

export async function fetchAuditIntervals(
  orgId?: string, dateFrom?: string, dateTo?: string, benchmarkSetId?: string,
): Promise<AuditSectionResult<AuditIntervals>> {
  return fetchJson(`${ANALYTICS_BASE}/analytics/audit/intervals${_auditParams(orgId, dateFrom, dateTo, benchmarkSetId)}`);
}

export async function fetchAuditSafetyNetting(
  orgId?: string, dateFrom?: string, dateTo?: string, benchmarkSetId?: string,
): Promise<AuditSectionResult<AuditSafetyNetting>> {
  return fetchJson(`${ANALYTICS_BASE}/analytics/audit/safety-netting${_auditParams(orgId, dateFrom, dateTo, benchmarkSetId)}`);
}

export async function fetchAuditCareObstructions(
  orgId?: string, dateFrom?: string, dateTo?: string, benchmarkSetId?: string,
): Promise<AuditSectionResult<AuditCareObstruction>> {
  return fetchJson(`${ANALYTICS_BASE}/analytics/audit/care-obstructions${_auditParams(orgId, dateFrom, dateTo, benchmarkSetId)}`);
}


export async function fetchAuditAvoidableDelays(
  orgId?: string, dateFrom?: string, dateTo?: string, benchmarkSetId?: string,
): Promise<AuditSectionResult<AuditAvoidableDelays>> {
  return fetchJson(`${ANALYTICS_BASE}/analytics/audit/avoidable-delays${_auditParams(orgId, dateFrom, dateTo, benchmarkSetId)}`);
}

export async function fetchAuditComorbidities(
  orgId?: string, dateFrom?: string, dateTo?: string, benchmarkSetId?: string,
): Promise<AuditSectionResult<AuditComorbidities>> {
  return fetchJson(`${ANALYTICS_BASE}/analytics/audit/comorbidities${_auditParams(orgId, dateFrom, dateTo, benchmarkSetId)}`);
}

export async function fetchAuditComorbiditiesDrilldown(
  orgId?: string,
  dateFrom?: string,
  dateTo?: string,
): Promise<AuditComorbiditiesDrilldown> {
  return fetchJson(
    `${ANALYTICS_BASE}/analytics/audit/comorbidities/drilldown${_auditParams(orgId, dateFrom, dateTo)}`,
  );
}

export async function fetchAuditSymptoms(
  orgId?: string,
  dateFrom?: string,
  dateTo?: string,
): Promise<AuditSymptoms> {
  return fetchJson(
    `${ANALYTICS_BASE}/analytics/audit/symptoms${_auditParams(orgId, dateFrom, dateTo)}`,
  );
}

export async function fetchAuditSymptomsDrilldown(
  orgId?: string,
  dateFrom?: string,
  dateTo?: string,
): Promise<AuditSymptomsDrilldown> {
  return fetchJson(
    `${ANALYTICS_BASE}/analytics/audit/symptoms/drilldown${_auditParams(orgId, dateFrom, dateTo)}`,
  );
}

export async function batchAddConceptsToSubdomain(
  domainId: string,
  subdomainName: string,
  concepts: Array<{ concept_id: number; term: string }>,
): Promise<SubdomainDetail> {
  return fetchJson<SubdomainDetail>(
    `${ANALYTICS_BASE}/analytics/domains/${encodeURIComponent(domainId)}/subdomains/${encodeURIComponent(subdomainName)}/concepts/batch`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(concepts),
    },
  );
}

// ---------------------------------------------------------------------------
// Manual EpisodeOfCare CRUD - DI-3A19BE12, DI-F4C06C92, DI-B35DCA0F,
// DI-41B71BF8 / DOs DO-0792E2CB, DO-BDBEDA43, DO-13EA9B93, DO-CFB91205.
// Re-exported from missionControlApi.ts so the patient drawer can import
// the manual-CRUD helpers from the same module as closeEpisode /
// mergeEpisodes / editMilestone.
// ---------------------------------------------------------------------------

export {
  createEpisode,
  updateEpisode,
  deleteEpisode,
  attachEncounterToEpisode,
  detachEncounterFromEpisode,
} from "@/lib/missionControlApi";

export type {
  EpisodeEncounterAttachment,
  EpisodeCreateBody,
  EpisodeUpdateBody,
  EpisodeDeleteBody,
  EpisodeDerivedDates,
  EpisodeCreateResponse,
  EpisodeUpdateResponse,
  EpisodeDeleteResponse,
  EpisodeAttachResponse,
  EpisodeDetachResponse,
} from "@/lib/missionControlApi";
