/**
 * API client for the domain-agnostic patient EPR endpoints.
 *
 * Atlas trace:
 *   DO: DO-EBF0B124, DO-5D3EA371
 *   DI: DI-0ADA35BF, DI-357A7468, DI-7DE8E8ED
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
  nhs_number: string | null;
  gender: string | null;
  birth_date: string | null;
  practice_name: string | null;
  episode_count: number;
  encounter_count: number;
  last_activity: string | null;
  active_alert_count: number;
  document_count: number;
  referral_count: number;
  coded_concept_count: number;
  semantic_tags: string[];
  condition_types: string[];
}

export interface EpisodeSummaryEpr {
  episode_id: string | null;
  condition_type: string | null;
  status: string | null;
  referral_date: string | null;
  end_date: string | null;
  first_presentation_date: string | null;
  inferred_outcome: string | null;
  staging_value: string | null;
  staging_early_late: string | null;
  referral_route: string | null;
  place_of_presentation: string | null;
  prior_consultations_n: number | null;
  safety_netting_recorded: boolean | null;
}

export interface CodedEntityRow {
  entity_type: "disease" | "finding" | "situation" | "medication" | string;
  name: string;
  concept_id: string | null;
}

/** The kind of node a coded concept's evidence hangs off. */
export type ConceptMentionSourceType = "encounter" | "document" | "communication";

/** One dated mention of a coded concept (no evidence sentence yet). */
export interface ConceptMention {
  source_id: string;
  source_type: ConceptMentionSourceType;
  source_date: string | null;
  assertion: string | null;
  confidence: number | null;
}

/** Full evidence for a single dated mention, fetched on demand. */
export interface ConceptMentionDetail {
  source_id: string;
  source_type: ConceptMentionSourceType;
  source_date: string | null;
  concept_id: string;
  name: string | null;
  read_code: string | null;
  assertion: string | null;
  confidence: number | null;
  evidence: string | null;
  evidence_sentence: string | null;
}

export interface PatientDetail {
  patient_id: string;
  display_name?: string | null;
  nhs_number: string | null;
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

export interface EncounterRow {
  encounter_id: string;
  encounter_date: string | null;
  encounter_type: string;
  specialty: string | null;
  text_preview: string | null;
  coded_count: number;
  episode_id: string | null;
}

export interface CodedTerm {
  code_id: string | null;
  display: string | null;
  system: string;
  evidence_sentence: string | null;
  assertion: string | null;
  confidence: number | null;
  value: string | null;
  unit: string | null;
}

export interface EncounterDetail {
  encounter_id: string;
  encounter_date: string | null;
  encounter_type: string;
  specialty: string | null;
  full_text: string;
  episode_id: string | null;
  coded_terms: CodedTerm[];
}

export interface SbarContent {
  sbar_id: string;
  status: string | null;
  situation: string | null;
  background: string | null;
  assessment: string | null;
  recommendation: string | null;
}

export interface DocumentRow {
  document_id: string;
  document_date: string | null;
  document_type: string;
  title: string;
  category: string | null;
  text_preview: string | null;
  full_text: string;
  content_type: string | null;
  original_url: string | null;
  markdown_url: string | null;
  episode_id: string | null;
  episode_label: string;
  sbar: SbarContent | null;
}

export interface AssessmentRow {
  assessment_id: string;
  episode_id: string | null;
  episode_label: string;
  scope: string | null;
  status: string | null;
  created_at: string | null;
  situation: string | null;
  background: string | null;
  assessment: string | null;
  recommendation: string | null;
  content: string | null;
  stt: string | null;
  stt_evidence: string | null;
  completeness_failed_count: number | null;
  /** JSON-serialised SbarBackgroundPart[] stored on the Assessment node */
  background_parts: string | null;
  /** JSON-serialised CompletenessFinding stored on the Assessment node */
  completeness_result_json: string | null;
}

export interface AlertRow {
  alert_id: string;
  alert_type: string;
  severity: string;
  created_at: string | null;
  resolved_at: string | null;
  message: string | null;
  condition_context: string | null;
  guideline_ref: string | null;
}

export interface MilestoneStep {
  milestone_type: string;
  dates: string[];
}

export interface EpisodeMilestones {
  episode_id: string;
  referral_date: string | null;
  end_date: string | null;
  steps: MilestoneStep[];
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

/** Return encounter list with text previews. */
export async function fetchEprEncounters(
  patientId: string
): Promise<EncounterRow[]> {
  return fetchJson<EncounterRow[]>(
    `${ANALYTICS_BASE}/patients/${encodeURIComponent(patientId)}/encounters`
  );
}

/** Return full encounter detail including coded terms. */
export async function fetchEprEncounterDetail(
  patientId: string,
  encounterId: string
): Promise<EncounterDetail> {
  return fetchJson<EncounterDetail>(
    `${ANALYTICS_BASE}/patients/${encodeURIComponent(patientId)}/encounters/${encodeURIComponent(encounterId)}`
  );
}

/** Return documents with linked SBAR content. */
export async function fetchEprDocuments(
  patientId: string
): Promise<DocumentRow[]> {
  return fetchJson<DocumentRow[]>(
    `${ANALYTICS_BASE}/patients/${encodeURIComponent(patientId)}/documents`
  );
}

/** Return all SBAR assessments for a patient. */
export async function fetchEprAssessments(
  patientId: string
): Promise<AssessmentRow[]> {
  return fetchJson<AssessmentRow[]>(
    `${ANALYTICS_BASE}/patients/${encodeURIComponent(patientId)}/assessments`
  );
}

/** Return all safety alerts for a patient. */
export async function fetchEprAlerts(
  patientId: string
): Promise<AlertRow[]> {
  return fetchJson<AlertRow[]>(
    `${ANALYTICS_BASE}/patients/${encodeURIComponent(patientId)}/alerts`
  );
}

/** Return patient-level SNOMED coded entities (diseases, findings, medications, situations). */
export async function fetchCodedEntities(
  patientId: string
): Promise<CodedEntityRow[]> {
  return fetchJson<CodedEntityRow[]>(
    `${ANALYTICS_BASE}/patients/${encodeURIComponent(patientId)}/coded-entities`
  );
}

/**
 * Return dated mentions for one coded concept (lightweight, no sentence).
 *
 * Covers all three evidence source types (encounter, document/chunk,
 * communication) -- a concept coded from a document pipeline has no
 * Encounter-level mention at all, so this must not be encounter-only.
 */
export async function fetchConceptMentions(
  patientId: string,
  conceptId: string
): Promise<ConceptMention[]> {
  return fetchJson<ConceptMention[]>(
    `${ANALYTICS_BASE}/patients/${encodeURIComponent(patientId)}/coded-entities/` +
      `${encodeURIComponent(conceptId)}/mentions`
  );
}

/** Return the evidence sentence for one dated mention of a coded concept. */
export async function fetchConceptMentionDetail(
  patientId: string,
  conceptId: string,
  sourceType: ConceptMentionSourceType,
  sourceId: string
): Promise<ConceptMentionDetail> {
  return fetchJson<ConceptMentionDetail>(
    `${ANALYTICS_BASE}/patients/${encodeURIComponent(patientId)}/coded-entities/` +
      `${encodeURIComponent(conceptId)}/mentions/${encodeURIComponent(sourceType)}/` +
      `${encodeURIComponent(sourceId)}`
  );
}

/** Return milestone steps for a single episode. */
export async function fetchEpisodeMilestones(
  patientId: string,
  episodeId: string
): Promise<EpisodeMilestones> {
  return fetchJson<EpisodeMilestones>(
    `${ANALYTICS_BASE}/patients/${encodeURIComponent(patientId)}/episodes/${encodeURIComponent(episodeId)}/milestones`
  );
}

export interface AlertActionResult {
  alert_id: string;
  alert_type: string | null;
  resolved_at: string | null;
  escalated_at: string | null;
  action: string | null;
}

/** Mark an alert as reviewed, resolved, or escalated. */
export async function patchAlert(
  patientId: string,
  alertId: string,
  action: "resolve" | "escalate" | "review",
  reviewedBy?: string
): Promise<AlertActionResult> {
  return fetchJson<AlertActionResult>(
    `${ANALYTICS_BASE}/patients/${encodeURIComponent(patientId)}/alerts/${encodeURIComponent(alertId)}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action, reviewed_by: reviewedBy }),
    }
  );
}
