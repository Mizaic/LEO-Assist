"use client";

import Box from "@mui/material/Box";
import SectionCard from "./SectionCard";
import ComparisonBarChart, { type ComparisonDataRow } from "./ComparisonBarChart";
import BenchmarkLegend, { resolveBenchmarkValue } from "./BenchmarkLegend";
import SummaryStatsTable from "./SummaryStatsRow";
import CancerTypeBenchmarkGrid from "./CancerTypeBenchmarkGrid";
import type { AuditConsultations, AuditSectionResult } from "@/lib/analyticsApi";

interface Props {
  result: AuditSectionResult<AuditConsultations> | null;
  loading: boolean;
  error?: string | null;
  orgSelected?: boolean;
}

export default function ConsultationsSection({ result, loading, error, orgSelected = false }: Props) {
  const practice = result?.scopes.practice;
  const allianceLive = result?.scopes.alliance_live;
  const englandLive = result?.scopes.england_live;
  const bm = result?.benchmark?.metrics;

  const visibleKeys = orgSelected
    ? (["practice", "national", "similar", "alliance"] as const)
    : (["practice", "national"] as const);

  const fewerThan3Bm = resolveBenchmarkValue(bm, "consultations.fewer_than_3_pct", orgSelected);

  const chartData: ComparisonDataRow[] = [
    {
      category: "Fewer than 3",
      practice: practice?.fewer_than_3_pct ?? null,
      similar: allianceLive?.fewer_than_3_pct ?? null,
      alliance: englandLive?.fewer_than_3_pct ?? null,
      national: fewerThan3Bm,
    },
    {
      category: "3 or more",
      practice: practice?.three_or_more_pct ?? null,
      similar: allianceLive?.three_or_more_pct ?? null,
      alliance: englandLive?.three_or_more_pct ?? null,
      national: fewerThan3Bm != null ? 100 - fewerThan3Bm : null,
    },
  ];

  const summaryRows = [
    {
      label: "Fewer than 3 consultations (%)",
      unit: "%",
      practice: practice ? { value: practice.fewer_than_3_pct, n: practice.fewer_than_3_n } : null,
      similar: allianceLive ? { value: allianceLive.fewer_than_3_pct } : null,
      alliance: englandLive ? { value: englandLive.fewer_than_3_pct } : { value: bm?.["consultations.fewer_than_3_pct"]?.alliance ?? null },
      national: { value: fewerThan3Bm },
    },
    {
      label: "Median consultations",
      unit: "",
      practice: practice
        ? { value: practice.median_consultations, iqr: [practice.iqr_low, practice.iqr_high] as [number | null, number | null] }
        : null,
      similar: allianceLive ? { value: allianceLive.median_consultations } : null,
      alliance: englandLive ? { value: englandLive.median_consultations } : { value: bm?.["consultations.median_consultations"]?.alliance ?? null },
      national: { value: resolveBenchmarkValue(bm, "consultations.median_consultations", orgSelected) },
    },
  ];

  return (
    <SectionCard
      id="section-consultations"
      title="Consultations"
      description="Number of consultations for cancer-related symptoms in the year before the referral leading to diagnosis."
      availability="ready"
      loading={loading}
      error={error}
    >
      <BenchmarkLegend visibleKeys={visibleKeys} orgSelected={orgSelected} />
      <ComparisonBarChart
        data={chartData}
        unit="percent"
        height={240}
        visibleKeys={visibleKeys}
        orgSelected={orgSelected}
        ariaLabel="Proportion of patients with fewer than 3 vs 3 or more consultations"
      />
      <Box sx={{ mt: 2 }}>
        <SummaryStatsTable
          rows={summaryRows}
          visibleKeys={visibleKeys}
          orgSelected={orgSelected}
          caption="Consultation summary statistics"
        />
      </Box>
      <CancerTypeBenchmarkGrid
        bm={bm}
        section="consultations"
        metrics={[{ metricKey: "fewer_than_3_pct", label: "Fewer than 3" }]}
        orgSelected={orgSelected}
        heading="2018 Baseline by Cancer Type — Fewer than 3 Consultations (%)"
      />
    </SectionCard>
  );
}
