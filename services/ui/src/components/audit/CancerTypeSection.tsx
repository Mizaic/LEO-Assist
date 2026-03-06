"use client";

import SectionCard from "./SectionCard";
import ComparisonBarChart, { type ComparisonDataRow } from "./ComparisonBarChart";
import BenchmarkLegend, { resolveBenchmarkValue } from "./BenchmarkLegend";
import SummaryStatsTable from "./SummaryStatsRow";
import Typography from "@mui/material/Typography";
import type { AuditCancerTypeRow, AuditSectionResult } from "@/lib/analyticsApi";

interface Props {
  result: AuditSectionResult<AuditCancerTypeRow[]> | null;
  loading: boolean;
  error?: string | null;
  orgSelected?: boolean;
}

export default function CancerTypeSection({ result, loading, error, orgSelected = false }: Props) {
  const practice = result?.scopes.practice ?? [];
  const allianceLive = result?.scopes.alliance_live;
  const englandLive = result?.scopes.england_live;
  const bm = result?.benchmark?.metrics;

  const visibleKeys = orgSelected
    ? (["practice", "national", "similar", "alliance"] as const)
    : (["practice", "national"] as const);

  // Build the full type list as a union of live data + 2018 benchmark types so that
  // types present in 2018 but absent from today's patient data are still shown
  // (they'll render a 2018 bar with no live bar — a meaningful signal in itself).
  const liveTypes = new Set(practice.map((r) => r.cancer_type).filter(Boolean));

  const bmTypes: string[] = bm
    ? Object.keys(bm)
        .filter((k) => k.startsWith("condition_type.") && k.split(".").length === 2)
        .map((k) => k.replace("condition_type.", ""))
    : [];

  const allTypes = Array.from(new Set([...liveTypes, ...bmTypes]))
    // Sort by live practice proportion descending; benchmark-only types fall to the end
    .sort((a, b) => {
      const pa = practice.find((r) => r.cancer_type === a)?.pct ?? -1;
      const pb = practice.find((r) => r.cancer_type === b)?.pct ?? -1;
      return pb - pa;
    });

  const chartData: ComparisonDataRow[] = allTypes.map((type) => {
    const pRow = practice.find((r) => r.cancer_type === type);
    const aRow = allianceLive?.find((r) => r.cancer_type === type);
    const eRow = englandLive?.find((r) => r.cancer_type === type);
    const metricKey = `condition_type.${type.toLowerCase()}`;
    return {
      category: type,
      practice: pRow?.pct ?? null,
      similar: aRow?.pct ?? null,
      alliance: eRow?.pct ?? null,
      national: resolveBenchmarkValue(bm, metricKey, orgSelected),
    };
  });

  const tableRows = allTypes.map((type) => {
    const pRow = practice.find((r) => r.cancer_type === type);
    const aRow = allianceLive?.find((r) => r.cancer_type === type);
    const eRow = englandLive?.find((r) => r.cancer_type === type);
    const metricKey = `condition_type.${type.toLowerCase()}`;
    return {
      label: type,
      unit: "%",
      practice: pRow ? { value: pRow.pct, n: pRow.n } : null,
      similar: aRow ? { value: aRow.pct } : null,
      alliance: eRow ? { value: eRow.pct } : { value: bm?.[metricKey]?.alliance ?? null },
      national: { value: resolveBenchmarkValue(bm, metricKey, orgSelected) },
    };
  });

  return (
    <SectionCard
      id="section-cancer-type"
      title="Cancer Type"
      description="Distribution of cancer types among patients in this audit, compared to Cancer Alliance and national benchmarks."
      availability="ready"
      loading={loading}
      error={error}
    >
      {practice.length === 0 ? (
        <Typography variant="body2" color="text.secondary" sx={{ py: 3, textAlign: "center" }}>
          No cancer type data available for the selected period.
        </Typography>
      ) : (
        <>
          <BenchmarkLegend visibleKeys={visibleKeys} orgSelected={orgSelected} />
          <ComparisonBarChart
            data={chartData}
            unit="percent"
            height={Math.max(280, allTypes.length * 30 + 80)}
            visibleKeys={visibleKeys}
            orgSelected={orgSelected}
            ariaLabel="Cancer type distribution compared to alliance and national benchmarks"
          />
          <SummaryStatsTable
            rows={tableRows}
            visibleKeys={visibleKeys}
            orgSelected={orgSelected}
            caption="Top cancer types by proportion (%)"
          />
        </>
      )}
    </SectionCard>
  );
}
