/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-2E8544FD
 *   DI: DI-C65FD45B
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-2E8544FD")
 */
"use client";

import SectionCard from "./SectionCard";
import ComparisonBarChart, { type ComparisonDataRow } from "./ComparisonBarChart";
import BenchmarkLegend, { resolveBenchmarkValue } from "./BenchmarkLegend";
import Typography from "@mui/material/Typography";
import Box from "@mui/material/Box";
import type { AuditSectionResult, BenchmarkMetricValues } from "@/lib/analyticsApi";

interface Props {
  /** Passed for future live data; not yet used beyond benchmark overlay. */
  result?: AuditSectionResult<unknown> | null;
  loading?: boolean;
  error?: string | null;
  orgSelected?: boolean;
}

const REASONS: { key: string; label: string; metricKey: string }[] = [
  { key: "complexity", label: "Complexity of presentation", metricKey: "consultations.multiple_reason_complexity_pct" },
  { key: "patient_factors", label: "Patient factors", metricKey: "" },
  { key: "gp_factors", label: "GP factors", metricKey: "" },
  { key: "diagnostic_process", label: "Diagnostic process", metricKey: "" },
];

const REASON_DESCRIPTIONS: Record<string, string> = {
  complexity: "Vague/non-specific symptoms, co-morbidity blurring picture, symptoms suggested different initial diagnosis",
  patient_factors: "Patient declined test or referral, patient did not attend",
  gp_factors: "Poor communication, inadequate history taken, referred to wrong specialty, seen by multiple health professionals",
  diagnostic_process: "Reassurance from negative investigation, multiple consultations to discuss test results",
};

export default function MultipleConsultationsSection({ result, loading, error, orgSelected = false }: Props) {
  const bm = result?.benchmark?.metrics as Record<string, BenchmarkMetricValues> | undefined;

  const visibleKeys = ["practice", "alliance", "national"] as const;

  const chartData: ComparisonDataRow[] = REASONS.map((r) => ({
    category: r.label.length > 28 ? r.label.slice(0, 27) + "…" : r.label,
    practice: null,
    alliance: r.metricKey ? (bm?.[r.metricKey]?.alliance ?? null) : null,
    national: r.metricKey ? resolveBenchmarkValue(bm, r.metricKey, orgSelected) : null,
  }));

  return (
    <SectionCard
      id="section-multiple-consultations"
      title="Reasons for Multiple Consultations"
      description="For patients who had 3 or more consultations before referral — the reasons as assessed by the GP. Requires structured data entry."
      availability="manual_entry"
      loading={loading}
      error={error}
    >
      <BenchmarkLegend visibleKeys={visibleKeys} orgSelected={orgSelected} />
      <ComparisonBarChart
        data={chartData}
        unit="percent"
        height={260}
        visibleKeys={visibleKeys}
        orgSelected={orgSelected}
        ariaLabel="Reasons for multiple consultations compared to benchmarks"
      />
      <Box sx={{ mt: 2 }}>
        <Typography variant="caption" color="text.secondary" sx={{ fontSize: "0.75rem", display: "block" }}>
          <strong>Note:</strong> Patients may have had multiple reasons. Reason groups include:
        </Typography>
        {REASONS.map((r) => (
          <Typography key={r.key} variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.25, fontSize: "0.74rem" }}>
            <strong>{r.label}:</strong> {REASON_DESCRIPTIONS[r.key]}
          </Typography>
        ))}
      </Box>
    </SectionCard>
  );
}
