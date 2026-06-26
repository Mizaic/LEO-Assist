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
