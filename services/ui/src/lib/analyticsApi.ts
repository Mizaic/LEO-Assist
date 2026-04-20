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
  return fetchJson<Cohort>(`${ANALYTICS_BASE}/analytics/cohorts`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, description, filters }),
  });
}

export async function fetchCohorts(): Promise<Cohort[]> {
  return fetchJson<Cohort[]>(`${ANALYTICS_BASE}/analytics/cohorts`);
}

export async function resolveCohort(cohortId: string): Promise<CohortPatients> {
  return fetchJson<CohortPatients>(
    `${ANALYTICS_BASE}/analytics/cohorts/${cohortId}/patients`,
  );
}

export async function deleteCohort(cohortId: string): Promise<{ success: boolean }> {
  return fetchJson<{ success: boolean }>(
    `${ANALYTICS_BASE}/analytics/cohorts/${cohortId}`,
    { method: "DELETE" },
  );
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
  median_pci_days: number | null;
  median_di_days: number | null;
  avg_consultations: number | null;
  safety_netting_pct: number | null;
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
  by_stage_group_detail: Array<{ cancer_stage_group: string; n: number }>;
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
}

export interface AuditPlaceRow {
  place: string;
  n: number;
  pct: number;
}

export interface AuditConsultations {
  fewer_than_3_pct: number;
  three_or_more_pct: number;
  fewer_than_3_n: number;
  three_or_more_n: number;
  total_episodes: number;
  median_consultations: number | null;
  iqr_low: number | null;
  iqr_high: number | null;
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

export interface AuditIntervalsPatient {
  episode_id: string;
  cancer_type?: string | null;
  pci_days?: number | null;
  di_days?: number | null;
  diag_is_inferred?: boolean | null;
}

export interface AuditIntervalStats {
  n: number | null;
  mean: number | null;
  median: number | null;
  q1: number | null;
  q3: number | null;
}

export interface AuditIntervals {
  pci: AuditIntervalStats;
  di: AuditIntervalStats;
  patients: AuditIntervalsPatient[];
}

export interface AuditSafetyNetting {
  total_episodes: number;
  recorded_n: number;
  recorded_pct: number;
  not_recorded_pct: number;
}

export interface AuditComorbidityRow {
  condition: string;
  n: number;
  pct: number;
  /** Key linking to ncda_2018_benchmarks.json (e.g. comorbidity_hypertension_pct) */
  benchmark_key?: string;
}

export interface AuditComorbidities {
  comorbidities: AuditComorbidityRow[];
  total_patients: number;
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
