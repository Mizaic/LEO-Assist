"use client";

import Box from "@mui/material/Box";
import SectionCard from "./SectionCard";
import ComparisonBarChart, { type ComparisonDataRow } from "./ComparisonBarChart";
import BenchmarkLegend from "./BenchmarkLegend";
import SummaryStatsTable from "./SummaryStatsRow";
import type { AuditAvoidableDelays } from "@/lib/analyticsApi";

interface Props {
  data: AuditAvoidableDelays | null;
  loading: boolean;
  error?: string | null;
}

export default function AvoidableDelaysSection({ data, loading, error }: Props) {
  const mainChart: ComparisonDataRow[] = [
    {
      category: "Avoidable delay identified",
      practice: data?.has_avoidable_delay_pct ?? null,
      alliance: 24.8,
      national: 23.5,
    },
  ];

  const stageChart: ComparisonDataRow[] = [
    {
      category: "Before presentation",
      practice: data?.delay_before_presentation_pct ?? null,
      alliance: 45.6,
      national: 43.7,
    },
    {
      category: "Presentation to referral",
      practice: data?.delay_before_referral_pct ?? null,
      alliance: 46.1,
      national: 43.9,
    },
    {
      category: "After referral",
      practice: data?.delay_after_referral_pct ?? null,
      alliance: 33.5,
      national: 39.3,
    },
  ];

  const tableRows = [
    {
      label: "GP-assessed avoidable delay (%)",
      unit: "%",
      practice: data ? { value: data.has_avoidable_delay_pct, n: data.has_avoidable_delay_n } : null,
      alliance: { value: 24.8 },
      national: { value: 23.5 },
    },
    {
      label: "Delay — before presentation (%)",
      unit: "%",
      practice: data ? { value: data.delay_before_presentation_pct } : null,
      alliance: { value: 45.6 },
      national: { value: 43.7 },
    },
    {
      label: "Delay — presentation to referral (%)",
      unit: "%",
      practice: data ? { value: data.delay_before_referral_pct } : null,
      alliance: { value: 46.1 },
      national: { value: 43.9 },
    },
    {
      label: "Delay — after referral (%)",
      unit: "%",
      practice: data ? { value: data.delay_after_referral_pct } : null,
      alliance: { value: 33.5 },
      national: { value: 39.3 },
    },
  ];

  return (
    <SectionCard
      id="section-avoidable-delays"
      title="Avoidable Delays"
      description="Cases where the GP, with hindsight, judged there to have been an avoidable delay in the patient's cancer diagnosis. Requires structured GP data entry."
      availability="manual_entry"
      loading={loading}
      error={error}
    >
      <BenchmarkLegend visibleKeys={["practice", "alliance", "national"]} />
      <ComparisonBarChart
        data={mainChart}
        unit="percent"
        height={200}
        visibleKeys={["practice", "alliance", "national"]}
        ariaLabel="Proportion of patients with GP-assessed avoidable delay"
      />
      <Box sx={{ mt: 2 }}>
        <ComparisonBarChart
          data={stageChart}
          unit="percent"
          height={240}
          visibleKeys={["practice", "alliance", "national"]}
          ariaLabel="Stage at which avoidable delay occurred"
        />
      </Box>
      <Box sx={{ mt: 2 }}>
        <SummaryStatsTable rows={tableRows} visibleKeys={["practice", "alliance", "national"]} caption="Avoidable delays by stage in pathway (% of patients with delay)" />
      </Box>
    </SectionCard>
  );
}
