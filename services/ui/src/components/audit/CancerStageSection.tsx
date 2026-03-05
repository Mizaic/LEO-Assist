"use client";

import SectionCard from "./SectionCard";
import ComparisonBarChart, { type ComparisonDataRow } from "./ComparisonBarChart";
import BenchmarkLegend from "./BenchmarkLegend";
import SummaryStatsTable from "./SummaryStatsRow";
import Typography from "@mui/material/Typography";
import type { AuditCancerStageRow, AuditSectionResult } from "@/lib/analyticsApi";

const LABELS: Record<string, string> = {
  early: "Early (stage 0/1/2)",
  late: "Late (stage 3/4)",
  unknown: "Unknown / not recorded",
};

interface Props {
  result: AuditSectionResult<AuditCancerStageRow[]> | null;
  loading: boolean;
  error?: string | null;
  orgSelected?: boolean;
}

export default function CancerStageSection({ result, loading, error, orgSelected = false }: Props) {
  const practice = result?.scopes.practice ?? [];
  const allianceLive = result?.scopes.alliance_live;
  const englandLive = result?.scopes.england_live;
  const bm = result?.benchmark?.metrics;

  const visibleKeys = orgSelected
    ? (["practice", "similar", "alliance", "national"] as const)
    : (["practice", "national"] as const);

  const chartData: ComparisonDataRow[] = ["early", "late"].map((group) => {
    const pRow = practice.find((r) => r.stage_group === group);
    const aRow = allianceLive?.find((r) => r.stage_group === group);
    const eRow = englandLive?.find((r) => r.stage_group === group);
    const metricKey = `cancer_stage.${group}_stage_pct`;
    return {
      category: LABELS[group],
      practice: pRow?.pct ?? null,
      similar: aRow?.pct ?? null,
      alliance: eRow?.pct ?? null,
      national: bm?.[metricKey]?.national ?? null,
    };
  });

  const tableRows = ["early", "late"].map((group) => {
    const pRow = practice.find((r) => r.stage_group === group);
    const aRow = allianceLive?.find((r) => r.stage_group === group);
    const eRow = englandLive?.find((r) => r.stage_group === group);
    const metricKey = `cancer_stage.${group}_stage_pct`;
    return {
      label: LABELS[group],
      unit: "%",
      practice: pRow ? { value: pRow.pct, n: pRow.n } : null,
      similar: aRow ? { value: aRow.pct } : null,
      alliance: eRow ? { value: eRow.pct } : { value: bm?.[metricKey]?.alliance ?? null },
      national: { value: bm?.[metricKey]?.national ?? null },
    };
  });

  return (
    <SectionCard
      id="section-cancer-stage"
      title="Cancer Stage at Diagnosis"
      description="Early (stage 0/1/2) vs late (stage 3/4) stage at diagnosis. Requires external COSD/cancer registry data feed."
      availability="external_feed"
      loading={loading}
      error={error}
    >
      <BenchmarkLegend visibleKeys={visibleKeys} orgSelected={orgSelected} />
      {practice.length === 0 && (
        <Typography variant="body2" color="text.secondary" sx={{ py: 2 }}>
          Practice-level stage data is not yet available. Connect the Cancer Outcomes and Services Dataset (COSD) feed to populate this section.
        </Typography>
      )}
      <ComparisonBarChart
        data={chartData}
        unit="percent"
        visibleKeys={visibleKeys}
        height={240}
        ariaLabel="Cancer stage at diagnosis compared to alliance and national benchmarks"
      />
      <SummaryStatsTable
        rows={tableRows}
        visibleKeys={visibleKeys}
        caption="Stage at diagnosis — % of audited cases"
      />
    </SectionCard>
  );
}
