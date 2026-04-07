/**
 * Typed API client for /api/admin/dq/* endpoints.
 * All calls require platform admin; session cookie sent via credentials: 'include'.
 */

import { api } from './client';

const DQ_BASE = '/api/admin/dq';

function qs(params: Record<string, unknown>): string {
  const entries = Object.entries(params)
    .filter(([, v]) => v !== undefined && v !== null && v !== '')
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`);
  return entries.length ? `?${entries.join('&')}` : '';
}

// ---------------------------------------------------------------------------
// Response types
// ---------------------------------------------------------------------------

export interface EpisodeHealthResult {
  total_count: number;
  status_counts: Record<string, number>;
  stale_count: number;
  hitl_count: number;
  auto_closed_count: number;
}

export interface StaleEpisode {
  patient_id: string;
  episode_id: string;
  site: string;
  status: string;
  days_stale: number;
  referral_date: string | null;
  specialist_date: string | null;
  last_encounter_date: string | null;
  encounter_count: number;
}

export interface SignalHit {
  date: string;
  label: string;
  snippet: string;
}

export interface OutcomeInferenceResult {
  patient_id: string;
  episode_id: string;
  site: string;
  referral_date: string | null;
  specialist_date: string | null;
  window_end: string | null;
  verdict: string;
  flag: string;
  cancer_signals: SignalHit[];
  benign_signals: SignalHit[];
  private_blocked: boolean;
  specialist_confirmed: boolean;
  phase2_encounter_count: number;
}

export interface MilestoneRow {
  patient_id: string;
  episode_id: string;
  site: string;
  status: string;
  has_referral: boolean;
  has_specialist: boolean;
  has_diagnosis: boolean;
  has_treatment: boolean;
  has_letter: boolean;
  has_benign_closure: boolean;
}

export interface SurfaceFormAuditResult {
  total_count: number;
  orphan_count: number;
  duplicate_count: number;
  inactive_target_count: number;
  low_confidence_count: number;
}

export interface DQCheckResult {
  rule_id: string;
  dimension: string;
  severity: string;
  status: 'pass' | 'warn' | 'fail';
  violation_count: number;
  threshold: number;
  sample_violations: Record<string, unknown>[];
  description: string;
}

export interface DQRulesResult {
  results: DQCheckResult[];
  summary: {
    total: number;
    pass: number;
    warn: number;
    fail: number;
    critical_failures: string[];
    overall: 'pass' | 'warn' | 'fail';
  };
}

export interface SitrepResult {
  episode_status_counts: Record<string, number>;
  stale_count: number;
  hitl_queue_depth: number;
  sf_task_backlog: number;
  gold_label_count: number;
  training_candidate_count: number;
  last_dq_run: string | null;
}

export interface PatientSummary {
  patient_id: string;
  encounter_count: number;
  episode_count: number;
  episodes: EpisodeSummary[];
  encounters: EncounterSummary[];
}

export interface EpisodeSummary {
  episode_id: string;
  site: string;
  status: string;
  referral_date: string | null;
  specialist_date: string | null;
  auto_closed: boolean;
  hitl_flag: boolean;
  hitl_reason: string | null;
}

export interface EncounterSummary {
  encounter_id: string;
  date: string;
  classification: string | null;
  coded_concepts: CodedConcept[];
  text_preview: string | null;
}

export interface CodedConcept {
  concept_id: string;
  name: string;
  assertion: string | null;
  confidence: number | null;
  semantic_tag: string | null;
}

export interface RemediationResult {
  operation: string;
  dry_run: boolean;
  affected_count: number;
  affected_items: Record<string, unknown>[];
  message: string;
}

// ---------------------------------------------------------------------------
// API functions
// ---------------------------------------------------------------------------

export const dqApi = {
  // Episode
  getEpisodeHealth: (): Promise<EpisodeHealthResult> =>
    api.get<EpisodeHealthResult>(`${DQ_BASE}/episodes/health`),

  getStaleEpisodes: (site?: string, thresholdDays = 90): Promise<{ episodes: StaleEpisode[] }> =>
    api.get(`${DQ_BASE}/episodes/stale${qs({ site, threshold_days: thresholdDays })}`),

  getCompleteness: (site?: string): Promise<{ episodes: MilestoneRow[] }> =>
    api.get(`${DQ_BASE}/episodes/completeness${qs({ site })}`),

  inferOutcome: (params?: {
    patient_id?: string;
    site?: string;
    threshold_days?: number;
  }): Promise<{ results: OutcomeInferenceResult[]; total: number }> =>
    api.get(`${DQ_BASE}/episodes/infer-outcome${qs(params ?? {})}`),

  // Terminology
  getSfAudit: (): Promise<SurfaceFormAuditResult> =>
    api.get<SurfaceFormAuditResult>(`${DQ_BASE}/terminology/sf/audit`),

  inspectSf: (term: string): Promise<unknown> =>
    api.get(`${DQ_BASE}/terminology/sf/${encodeURIComponent(term)}`),

  // Domain
  getDomainOrphans: (): Promise<{ orphans: unknown[] }> =>
    api.get(`${DQ_BASE}/domain/orphans`),

  getDomainGaps: (site?: string): Promise<{ gaps: unknown[] }> =>
    api.get(`${DQ_BASE}/domain/gaps${qs({ site })}`),

  getDomainCoverage: (domainId = 'ncda-cancer-types'): Promise<unknown> =>
    api.get(`${DQ_BASE}/domain/coverage${qs({ domain_id: domainId })}`),

  // Reports
  getSitrep: (): Promise<SitrepResult> =>
    api.get<SitrepResult>(`${DQ_BASE}/sitrep`),

  getCohort: (params?: {
    status?: string;
    site?: string;
    since?: string;
    until?: string;
  }): Promise<{ patient_ids: string[]; total_count: number }> =>
    api.get(`${DQ_BASE}/cohort${qs(params ?? {})}`),

  // Rules engine
  runRules: (): Promise<DQRulesResult> =>
    api.get<DQRulesResult>(`${DQ_BASE}/rules/run`),

  // Patient
  getPatient: (patientId: string, withText = false): Promise<PatientSummary> =>
    api.get<PatientSummary>(`${DQ_BASE}/patient/${patientId}${qs({ with_text: withText })}`),

  // Remediation
  deletePatient: (patientId: string, dryRun = true): Promise<RemediationResult> =>
    api.post<RemediationResult>(`${DQ_BASE}/remediation/delete-patient`, {
      patient_id: patientId,
      dry_run: dryRun,
    }),

  fixAssertions: (
    encounterId: string,
    oldAssertion: string,
    newAssertion: string,
    dryRun = true,
  ): Promise<RemediationResult> =>
    api.post<RemediationResult>(`${DQ_BASE}/remediation/fix-assertions`, {
      encounter_id: encounterId,
      old_assertion: oldAssertion,
      new_assertion: newAssertion,
      dry_run: dryRun,
    }),
};
