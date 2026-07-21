/**
 * Synthetic mock data for the audit template builder preview.
 *
 * When no org is selected (or useMockData=true), MetricTile uses this data
 * instead of calling the real API. This allows authors to see realistic
 * chart shapes while building templates without needing live tenant data.
 *
 * generateMockData(entry) returns a MetricRunResult shaped to match the
 * metric's output_schema. If the metric_id is known, curated NHS-shaped
 * data is returned; otherwise a generic generator uses the column types.
 *
 * Data is deterministic -- same metric_id always produces the same rows.
 */

import type { MetricCatalogueEntry, MetricRunResult } from "./auditTemplateApi";

// ---------------------------------------------------------------------------
// Curated mock data per metric_id
// ---------------------------------------------------------------------------

type MockRows = Record<string, unknown>[];

const CURATED: Record<string, MockRows> = {
  patient_count: [{ metric: "Total patients", count: 142 }],

  episode_count_by_condition: [
    { condition_type: "Breast", count: 34 },
    { condition_type: "Colorectal", count: 28 },
    { condition_type: "Lung", count: 22 },
    { condition_type: "Prostate", count: 19 },
    { condition_type: "Upper GI", count: 14 },
    { condition_type: "Haematological", count: 11 },
    { condition_type: "Other", count: 14 },
  ],

  cancer_stage_distribution: [
    { stage: "Stage 1", count: 41 },
    { stage: "Stage 2", count: 29 },
    { stage: "Stage 3", count: 18 },
    { stage: "Stage 4", count: 12 },
    { stage: "Unknown", count: 8 },
  ],

  referral_route_distribution: [
    { referral_route: "2WW", n: 89, pct: 62.7 },
    { referral_route: "Urgent GP", n: 27, pct: 19.0 },
    { referral_route: "Emergency", n: 15, pct: 10.6 },
    { referral_route: "Screening", n: 11, pct: 7.7 },
  ],

  episodes_over_time: buildMonthly(12, 18, 42),

  primary_care_interval: buildIntervals(20, 5, 45),

  diagnostic_interval: buildIntervals(20, 10, 60),

  referral_stt_rate: [
    { metric: "Straight-to-test rate", value: 68.4, target: 70.0 },
  ],

  referral_guideline_compliance_rate: [
    { metric: "NG12 compliance", value: 82.1, target: 85.0 },
  ],

  referral_alternative_pathway_rate: [
    { metric: "Alternative pathway rate", value: 12.3 },
  ],

  referral_completeness_rate: [
    { metric: "Referral completeness", value: 91.7, target: 95.0 },
  ],

  // -- Tier F: ReferralRequest audit metrics --
  rr_status_distribution: [
    { status: "AWAITING_TRIAGE", count: 228 },
    { status: "ACTIVE", count: 74 },
    { status: "DEFERRED_TO_PROVIDER", count: 18 },
    { status: "CLOSED", count: 6 },
  ],

  rr_priority_distribution: [
    { priority: "TWO_WEEK_WAIT", count: 270 },
    { priority: "URGENT", count: 37 },
    { priority: "ROUTINE", count: 15 },
    { priority: "unknown", count: 4 },
  ],

  rr_monthly_trend: buildMonthly(12, 18, 42),

  rr_yoy_trend: [
    { month: "01", year: "2024", count: 18 }, { month: "02", year: "2024", count: 22 },
    { month: "03", year: "2024", count: 29 }, { month: "04", year: "2024", count: 25 },
    { month: "05", year: "2024", count: 31 }, { month: "06", year: "2024", count: 27 },
    { month: "01", year: "2025", count: 24 }, { month: "02", year: "2025", count: 28 },
    { month: "03", year: "2025", count: 35 }, { month: "04", year: "2025", count: 31 },
    { month: "05", year: "2025", count: 38 }, { month: "06", year: "2025", count: 42 },
  ],

  rr_by_service: [
    { service: "Fast track cancer referral", count: 290 },
    { service: "Lower GI - Colorectal", count: 54 },
    { service: "Breast Services", count: 48 },
    { service: "Upper GI", count: 32 },
    { service: "Gynaecology", count: 28 },
    { service: "Other", count: 14 },
  ],

  rr_by_commissioning_org: [
    { organisation: "NHS Trust A", count: 145 },
    { organisation: "NHS Trust B", count: 98 },
    { organisation: "PCN Central", count: 67 },
    { organisation: "PCN North", count: 43 },
    { organisation: "PCN South", count: 21 },
  ],

  rr_avg_days_to_appointment: [
    { metric: "Avg days to first appointment", value: 18.5, target: 14.0 },
  ],

  rr_workflow_state: [
    { state: "AWAITING_TRIAGE", count: 228 },
    { state: "ACTIVE", count: 74 },
    { state: "DEFERRED_TO_PROVIDER", count: 18 },
    { state: "CLOSED", count: 6 },
  ],

  rr_wait_time_distribution: [
    { band: "0-2 weeks", count: 45 },
    { band: "2-4 weeks", count: 88 },
    { band: "4-8 weeks", count: 112 },
    { band: "8-12 weeks", count: 54 },
    { band: "12+ weeks", count: 27 },
  ],

  rr_wait_time_breaches_by_service: [
    { service: "Upper GI", total: 32, breaches: 11, breach_pct: 34.4 },
    { service: "Gynaecology", total: 28, breaches: 8, breach_pct: 28.6 },
    { service: "Lower GI - Colorectal", total: 54, breaches: 12, breach_pct: 22.2 },
    { service: "Breast Services", total: 48, breaches: 7, breach_pct: 14.6 },
    { service: "Fast track cancer referral", total: 290, breaches: 28, breach_pct: 9.7 },
  ],

  rr_peer_review_analysis: [
    { ai_assessment: "Appropriate - 2WW", count: 198 },
    { ai_assessment: "Appropriate - Urgent", count: 54 },
    { ai_assessment: "Consider downgrade", count: 38 },
    { ai_assessment: "Consider upgrade", count: 22 },
    { ai_assessment: "Insufficient information", count: 14 },
  ],

  rr_top_conditions: [
    { condition: "Rectal bleeding", count: 89 },
    { condition: "Change in bowel habit", count: 74 },
    { condition: "Breast lump", count: 61 },
    { condition: "Postmenopausal bleeding", count: 48 },
    { condition: "Unexplained weight loss", count: 37 },
    { condition: "Abdominal pain", count: 29 },
    { condition: "Dysphagia", count: 18 },
  ],

  rr_top_medications: [
    { medication: "Aspirin", count: 145 },
    { medication: "Metformin", count: 98 },
    { medication: "Atorvastatin", count: 87 },
    { medication: "Omeprazole", count: 74 },
    { medication: "Amlodipine", count: 61 },
  ],

  rr_abnormal_observations: [
    { observation: "Haemoglobin (low)", count: 78 },
    { observation: "CEA (elevated)", count: 45 },
    { observation: "CRP (elevated)", count: 38 },
    { observation: "Ferritin (low)", count: 29 },
    { observation: "CA125 (elevated)", count: 18 },
  ],

  rr_outcome_flow: [
    { priority: "TWO_WEEK_WAIT", state: "AWAITING_TRIAGE", count: 228 },
    { priority: "TWO_WEEK_WAIT", state: "ACTIVE", count: 42 },
    { priority: "URGENT", state: "AWAITING_TRIAGE", count: 27 },
    { priority: "ROUTINE", state: "DEFERRED_TO_PROVIDER", count: 15 },
    { priority: "URGENT", state: "ACTIVE", count: 10 },
  ],

  rr_patient_gender: [
    { gender: "female", count: 162 },
    { gender: "male", count: 159 },
    { gender: "other", count: 3 },
    { gender: "unknown", count: 2 },
  ],

  rr_patient_age_bands: [
    { age_band: "Under 18", count: 0 },
    { age_band: "18-29", count: 19 },
    { age_band: "30-44", count: 49 },
    { age_band: "45-59", count: 91 },
    { age_band: "60-74", count: 93 },
    { age_band: "75+", count: 70 },
  ],

  rr_imd_distribution: [
    { imd_group: "Most deprived (1-3)", count: 89 },
    { imd_group: "Middle (4-7)", count: 156 },
    { imd_group: "Least deprived (8-10)", count: 81 },
  ],

  rr_document_types: [
    { doc_type: "application/pdf", count: 364 },
    { doc_type: "unknown", count: 176 },
    { doc_type: "Word document", count: 95 },
    { doc_type: "text/html", count: 5 },
    { doc_type: "text/markdown", count: 2 },
  ],

  rr_data_completeness: [
    { field: "Commissioning org", present_n: 0, total: 326, pct: 0.0 },
    { field: "Service", present_n: 95, total: 326, pct: 29.1 },
    { field: "Appointment", present_n: 232, total: 326, pct: 71.2 },
    { field: "Document", present_n: 326, total: 326, pct: 100.0 },
    { field: "Patient", present_n: 324, total: 326, pct: 99.4 },
  ],

  rr_dq_score: [
    { metric: "Data quality score (%)", value: 28.5, target: 95.0 },
  ],

  unactioned_alerts_by_age: [
    { age_bucket: "0-3 days", count: 4 },
    { age_bucket: "4-7 days", count: 7 },
    { age_bucket: "8-14 days", count: 3 },
    { age_bucket: ">14 days", count: 1 },
  ],

  alert_escalation_rate: [{ metric: "Escalation rate", value: 23.5 }],

  repeat_referral_patients: buildPatientList(8),
};

// ---------------------------------------------------------------------------
// Helpers for deterministic generated data
// ---------------------------------------------------------------------------

function buildMonthly(n: number, base: number, max: number): MockRows {
  const months = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
  ];
  return Array.from({ length: n }, (_, i) => ({
    month: months[i % 12],
    count: Math.round(base + ((max - base) * i) / (n - 1) + (i % 3 === 0 ? -3 : 2)),
  }));
}

function buildIntervals(n: number, min: number, max: number): MockRows {
  return Array.from({ length: n }, (_, i) => ({
    patient_id: `PT-${1000 + i}`,
    interval_days: Math.round(min + ((max - min) * (i % 7)) / 6),
  }));
}

function buildPatientList(n: number): MockRows {
  const routes = ["2WW", "Urgent GP", "Emergency"];
  return Array.from({ length: n }, (_, i) => ({
    patient_id: `PT-${2000 + i}`,
    referral_count: 2 + (i % 3),
    last_referral_route: routes[i % routes.length],
    interval_days: 10 + i * 5,
  }));
}

// ---------------------------------------------------------------------------
// Generic fallback: generate a row per column using column type hints
// ---------------------------------------------------------------------------

function genericMockRows(entry: MetricCatalogueEntry, count = 5): MockRows {
  if (entry.output_schema.length === 0) return [];
  const cats = ["Category A", "Category B", "Category C", "Category D", "Category E"];
  return Array.from({ length: Math.min(count, cats.length) }, (_, i) => {
    const row: Record<string, unknown> = {};
    entry.output_schema.forEach((col, colIdx) => {
      if (colIdx === 0) {
        row[col.name] = cats[i];
      } else if (col.type === "integer" || col.type === "float") {
        row[col.name] = Math.round(10 + i * 15 + colIdx * 3);
      } else {
        row[col.name] = `Value ${i + 1}`;
      }
    });
    return row;
  });
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Return a deterministic MetricRunResult for the given catalogue entry.
 * Used by MetricTile when mockData is enabled (no live tenant data available).
 */
export function generateMockData(entry: MetricCatalogueEntry): MetricRunResult {
  const curated = CURATED[entry.metric_id];
  const rows = curated ?? genericMockRows(entry);

  const columns =
    rows.length > 0
      ? Object.keys(rows[0])
      : entry.output_schema.map((c) => c.name);

  return {
    metric_id: entry.metric_id,
    columns,
    rows: rows.map((r) => columns.map((c) => r[c] ?? null)),
  };
}
