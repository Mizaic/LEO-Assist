"use client";

import SectionCard from "./SectionCard";
import ComparisonBarChart, { type ComparisonDataRow } from "./ComparisonBarChart";
import BenchmarkLegend from "./BenchmarkLegend";
import Typography from "@mui/material/Typography";
import Box from "@mui/material/Box";

const REASONS: { key: string; label: string; national: number; alliance: number }[] = [
  { key: "complexity", label: "Complexity of presentation", national: 53.5, alliance: 55.1 },
  { key: "patient_factors", label: "Patient factors", national: 0, alliance: 0 },
  { key: "gp_factors", label: "GP factors", national: 0, alliance: 0 },
  { key: "diagnostic_process", label: "Diagnostic process", national: 0, alliance: 0 },
];

const REASON_DESCRIPTIONS: Record<string, string> = {
  complexity: "Vague/non-specific symptoms, co-morbidity blurring picture, symptoms suggested different initial diagnosis",
  patient_factors: "Patient declined test or referral, patient did not attend",
  gp_factors: "Poor communication, inadequate history taken, referred to wrong specialty, seen by multiple health professionals",
  diagnostic_process: "Reassurance from negative investigation, multiple consultations to discuss test results",
};

export default function MultipleConsultationsSection() {
  const chartData: ComparisonDataRow[] = REASONS.map((r) => ({
    category: r.label.length > 28 ? r.label.slice(0, 27) + "…" : r.label,
    practice: null,
    alliance: r.alliance || null,
    national: r.national || null,
  }));

  return (
    <SectionCard
      id="section-multiple-consultations"
      title="Reasons for Multiple Consultations"
      description="For patients who had 3 or more consultations before referral — the reasons as assessed by the GP. Requires structured data entry."
      availability="manual_entry"
    >
      <BenchmarkLegend visibleKeys={["practice", "alliance", "national"]} />
      <ComparisonBarChart
        data={chartData}
        unit="percent"
        height={260}
        visibleKeys={["practice", "alliance", "national"]}
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
