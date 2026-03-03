/**
 * API client for Analytics API and FHIR API.
 * Uses backend proxy (session cookie auth). Token stays server-side.
 */
import type { TimelineEvent } from "@/lib/types";

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
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || `Request failed (${res.status})`);
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

export async function fetchKPIBenchmarks(orgId?: string) {
  const params = orgId ? `?org_id=${orgId}` : "";
  return fetchJson<
    Array<{
      avg_days_to_referral: number | null;
      avg_days_to_diagnosis: number | null;
      avg_days_to_treatment: number | null;
      avg_consultations: number | null;
      episode_count: number;
    }>
  >(`${ANALYTICS_BASE}/analytics/benchmarks/kpis${params}`);
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
  custom_cypher?: string;
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

// ── Analytics: Domains (two-level hierarchy) ──

export interface DomainSummary {
  id: string;
  name: string;
  description: string;
  subdomain_count: number;
}

export interface SubdomainSummary {
  name: string;
  description: string;
  milestone_type?: string;
  time_window_months?: number;
  semantic_tags: string[];
  concept_count: number;
}

export interface DomainDetail extends DomainSummary {
  subdomains: SubdomainSummary[];
}

export interface SubdomainDetail extends SubdomainSummary {
  concepts: Array<{
    concept_id: number;
    term: string;
    preferred_term: string;
    semantic_tag?: string;
    subdomain: string;
    guideline_synonyms?: string[];
  }>;
}

export async function fetchDomains(): Promise<DomainSummary[]> {
  return fetchJson<DomainSummary[]>(`${ANALYTICS_BASE}/analytics/domains`);
}

export async function fetchDomain(domainId: string): Promise<DomainDetail> {
  return fetchJson<DomainDetail>(
    `${ANALYTICS_BASE}/analytics/domains/${encodeURIComponent(domainId)}`,
  );
}

export async function createDomain(
  name: string,
  description = "",
): Promise<DomainSummary> {
  return fetchJson<DomainSummary>(`${ANALYTICS_BASE}/analytics/domains`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, description }),
  });
}

export async function updateDomain(
  domainId: string,
  update: { name?: string; description?: string },
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
  await fetch(
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

export async function updateSubdomain(
  domainId: string,
  subdomainName: string,
  update: {
    description?: string;
    milestone_type?: string;
    time_window_months?: number;
    semantic_tags?: string[];
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

export async function addConceptToSubdomain(
  domainId: string,
  subdomainName: string,
  conceptId: number,
  term: string,
  synonyms: string[] = [],
): Promise<SubdomainDetail> {
  return fetchJson<SubdomainDetail>(
    `${ANALYTICS_BASE}/analytics/domains/${encodeURIComponent(domainId)}/subdomains/${encodeURIComponent(subdomainName)}/concepts`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ concept_id: conceptId, term, synonyms }),
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

// -- Patient coding timeline --

export async function fetchPatientCodingTimeline(patientId: string): Promise<TimelineEvent[]> {
  return fetchJson<TimelineEvent[]>(
    `${PROXY_BASE}/patients/${encodeURIComponent(patientId)}/timeline`,
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
