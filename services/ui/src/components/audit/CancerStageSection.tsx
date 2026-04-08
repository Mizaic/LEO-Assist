"use client";

import SectionCard from "./SectionCard";
import ComparisonBarChart, { type ComparisonDataRow } from "./ComparisonBarChart";
import BenchmarkLegend, { resolveBenchmarkValue } from "./BenchmarkLegend";
import SummaryStatsTable from "./SummaryStatsRow";
import CancerTypeBenchmarkGrid from "./CancerTypeBenchmarkGrid";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Typography from "@mui/material/Typography";
import type { AuditCancerStageSummary, AuditSectionResult } from "@/lib/analyticsApi";

const LABELS: Record<string, string> = {
  early: "Early (stage 0/1/2)",
  late: "Late (stage 3/4)",
  unknown: "Unknown / not recorded",
};

interface Props {
  result: AuditSectionResult<AuditCancerStageSummary> | null;
  loading: boolean;
  error?: string | null;
  orgSelected?: boolean;
}

export default function CancerStageSection({ result, loading, error, orgSelected = false }: Props) {
  const practice = result?.scopes.practice?.rows ?? [];
  const allianceLive = result?.scopes.alliance_live;
  const englandLive = result?.scopes.england_live;
  const practiceBySource = result?.scopes.practice?.by_source ?? [];
  const practiceCoverage = result?.scopes.practice?.coverage_pct ?? 0;
  const practiceCoverageN = result?.scopes.practice?.coverage_numerator ?? 0;
  const practiceCoverageD = result?.scopes.practice?.coverage_denominator ?? 0;
  const stageDetail = result?.scopes.practice?.by_stage_group_detail ?? [];
  const bm = result?.benchmark?.metrics;
  const byCancerType = result?.scopes.practice?.by_cancer_type ?? [];

  const normaliseCancerTypeKey = (value: string): string => {
    const key = value.toLowerCase();
    if (key === "bowel") return "colorectal";
    return key;
  };
  const liveByCancerType = byCancerType.reduce<Record<string, Record<string, number | null>>>((acc, row) => {
    const cancerTypeKey = normaliseCancerTypeKey(row.cancer_type || "unknown");
    if (!acc[cancerTypeKey]) {
      acc[cancerTypeKey] = {};
    }
    if (row.stage_group === "early") {
      acc[cancerTypeKey].early_stage_pct = row.pct;
    }
    if (row.stage_group === "late") {
      acc[cancerTypeKey].late_stage_pct = row.pct;
    }
    return acc;
  }, {});

  const visibleKeys = orgSelected
    ? (["practice", "national", "similar", "alliance"] as const)
    : (["practice", "national"] as const);

  const chartData: ComparisonDataRow[] = ["early", "late"].map((group) => {
    const pRow = practice.find((r) => r.stage_group === group);
    const aRow = allianceLive?.rows?.find((r) => r.stage_group === group);
    const eRow = englandLive?.rows?.find((r) => r.stage_group === group);
    const metricKey = `cancer_stage.${group}_stage_pct`;
    return {
      category: LABELS[group],
      practice: pRow?.pct ?? null,
      similar: aRow?.pct ?? null,
      alliance: eRow?.pct ?? null,
      national: resolveBenchmarkValue(bm, metricKey, orgSelected),
    };
  });

  const tableRows = ["early", "late"].map((group) => {
    const pRow = practice.find((r) => r.stage_group === group);
    const aRow = allianceLive?.rows?.find((r) => r.stage_group === group);
    const eRow = englandLive?.rows?.find((r) => r.stage_group === group);
    const metricKey = `cancer_stage.${group}_stage_pct`;
    return {
      label: LABELS[group],
      unit: "%",
      practice: pRow ? { value: pRow.pct, n: pRow.n } : null,
      similar: aRow ? { value: aRow.pct } : null,
      alliance: eRow ? { value: eRow.pct } : { value: bm?.[metricKey]?.alliance ?? null },
      national: { value: resolveBenchmarkValue(bm, metricKey, orgSelected) },
    };
  });

  return (
    <SectionCard
      id="section-cancer-stage"
      title="Cancer Stage at Diagnosis"
      description="Whether cancer was found early (stage 0, 1, or 2) or late (stage 3 or 4). Finding cancer early usually leads to better outcomes."
      availability="ready"
      loading={loading}
      error={error}
    >
      <BenchmarkLegend visibleKeys={visibleKeys} orgSelected={orgSelected} />
      {practice.length === 0 && (
        <Typography variant="body2" color="text.secondary" sx={{ py: 2 }}>
          No stage data is available yet for the selected filters.
        </Typography>
      )}
      <Box sx={{ mb: 1 }}>
        <Typography variant="body2" color="text.secondary">
          Stage recorded for {practiceCoverage}% of confirmed cases ({practiceCoverageN} of {practiceCoverageD})
        </Typography>
        <Typography variant="body2" color="text.secondary">
          Data sources: {practiceBySource.map((s) => `${s.staging_source} (${s.n})`).join(", ") || "none"}
        </Typography>
      </Box>
      <ComparisonBarChart
        data={chartData}
        unit="percent"
        visibleKeys={visibleKeys}
        height={240}
        orgSelected={orgSelected}
        ariaLabel="Cancer stage at diagnosis compared to alliance and national benchmarks"
      />
      <SummaryStatsTable
        rows={tableRows}
        visibleKeys={visibleKeys}
        orgSelected={orgSelected}
        caption="Stage at diagnosis — % of audited cases"
      />
      {stageDetail.length > 0 && (
        <Box sx={{ mt: 2 }}>
          <Typography variant="subtitle2" sx={{ mb: 0.5 }}>
            Stage group detail
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {stageDetail.map((r) => `${r.cancer_stage_group}: ${r.n}`).join(" | ")}
          </Typography>
        </Box>
      )}
      <CancerTypeBenchmarkGrid
        bm={bm}
        section="cancer_stage"
        metrics={[
          { metricKey: "early_stage_pct", label: "Early" },
          { metricKey: "late_stage_pct",  label: "Late" },
        ]}
        liveByCancerType={liveByCancerType}
        primarySeriesLabel={orgSelected ? "This Practice (today)" : "All Patients (today)"}
        orgSelected={orgSelected}
        heading="Stage at Diagnosis by Cancer Type"
      />
    </SectionCard>
  );
}
