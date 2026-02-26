/**
 * API client for Analytics API, FHIR API, and new service endpoints.
 */

const ANALYTICS_BASE =
  typeof process !== "undefined" && process.env?.NEXT_PUBLIC_ANALYTICS_API_BASE
    ? process.env.NEXT_PUBLIC_ANALYTICS_API_BASE
    : "http://localhost:8004";

const FHIR_BASE =
  typeof process !== "undefined" && process.env?.NEXT_PUBLIC_FHIR_API_BASE
    ? process.env.NEXT_PUBLIC_FHIR_API_BASE
    : "http://localhost:8003";

async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || `Request failed (${res.status})`);
  }
  return res.json();
}

// ── Analytics: Dashboards ──

export async function fetchEpisodeSummary(orgId?: string) {
  const params = orgId ? `?org_id=${orgId}` : "";
  return fetchJson<
    Array<{ cancer_type: string; status: string; count: number }>
  >(`${ANALYTICS_BASE}/analytics/episodes/summary${params}`);
}

export async function fetchEpisodeTimeline(patientId?: string, orgId?: string) {
  const params = new URLSearchParams();
  if (patientId) params.set("patient_id", patientId);
  if (orgId) params.set("org_id", orgId);
  const qs = params.toString();
  return fetchJson<
    Array<{
      episode_id: string;
      patient_id?: string;
      cancer_type: string;
      status: string;
      referral_date?: string;
      milestones?: Array<{
        encounter_id: string;
        date: string;
        milestone_type: string;
      }>;
    }>
  >(`${ANALYTICS_BASE}/analytics/episodes/timeline${qs ? `?${qs}` : ""}`);
}

export async function fetchCSSAlerts(orgId?: string) {
  const params = orgId ? `?org_id=${orgId}` : "";
  return fetchJson<
    Array<{
      episode_id: string;
      type: string;
      severity: string;
      description: string;
    }>
  >(`${ANALYTICS_BASE}/analytics/css/alerts${params}`);
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
