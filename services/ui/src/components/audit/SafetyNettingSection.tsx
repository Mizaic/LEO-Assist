"use client";

import Box from "@mui/material/Box";
import SectionCard from "./SectionCard";
import ComparisonBarChart, { type ComparisonDataRow } from "./ComparisonBarChart";
import BenchmarkLegend, { resolveBenchmarkValue } from "./BenchmarkLegend";
import SummaryStatsTable from "./SummaryStatsRow";
import type { AuditSafetyNetting, AuditSectionResult } from "@/lib/analyticsApi";

interface Props {
  result: AuditSectionResult<AuditSafetyNetting> | null;
  loading: boolean;
  error?: string | null;
  orgSelected?: boolean;
}

export default function SafetyNettingSection({ result, loading, error, orgSelected = false }: Props) {
  const practice = result?.scopes.practice;
  const allianceLive = result?.scopes.alliance_live;
  const englandLive = result?.scopes.england_live;
  const bm = result?.benchmark?.metrics;

  const visibleKeys = orgSelected
    ? (["practice", "national", "similar", "alliance"] as const)
    : (["practice", "national"] as const);

  const chartData: ComparisonDataRow[] = [
    {
      category: "Safety netting recorded",
      practice: practice?.recorded_pct ?? null,
      similar: allianceLive?.recorded_pct ?? null,
      alliance: englandLive?.recorded_pct ?? null,
      national: resolveBenchmarkValue(bm, "safety_netting.recorded_pct", orgSelected),
    },
  ];

  const tableRows = [
    {
      label: "Safety netting recorded (%)",
      unit: "%",
      practice: practice ? { value: practice.recorded_pct, n: practice.recorded_n } : null,
      similar: allianceLive ? { value: allianceLive.recorded_pct } : null,
      alliance: englandLive ? { value: englandLive.recorded_pct } : { value: bm?.["safety_netting.recorded_pct"]?.alliance ?? null },
      national: { value: resolveBenchmarkValue(bm, "safety_netting.recorded_pct", orgSelected) },
    },
  ];

  return (
    <SectionCard
      id="section-safety-netting"
      title="Safety Netting"
      description="Whether there was evidence in the clinical record that safety netting was recorded at any stage of the patient's diagnostic process."
      availability="pipeline_pending"
      loading={loading}
      error={error}
    >
      <BenchmarkLegend visibleKeys={visibleKeys} orgSelected={orgSelected} />
      <ComparisonBarChart
        data={chartData}
        unit="percent"
        height={200}
        visibleKeys={visibleKeys}
        orgSelected={orgSelected}
        ariaLabel="Proportion of cases with safety netting recorded, compared to benchmarks"
      />
      <Box sx={{ mt: 2 }}>
        <SummaryStatsTable rows={tableRows} visibleKeys={visibleKeys} orgSelected={orgSelected} caption="Safety netting summary" />
      </Box>
    </SectionCard>
  );
}
