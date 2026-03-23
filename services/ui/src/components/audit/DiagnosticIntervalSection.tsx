"use client";

import Box from "@mui/material/Box";
import SectionCard from "./SectionCard";
import IntervalStripPlot from "./IntervalStripPlot";
import SummaryStatsTable from "./SummaryStatsRow";
import BenchmarkLegend, { resolveBenchmarkValue } from "./BenchmarkLegend";
import type { AuditIntervals, AuditSectionResult } from "@/lib/analyticsApi";

interface Props {
  result: AuditSectionResult<AuditIntervals> | null;
  loading: boolean;
  error?: string | null;
  orgSelected?: boolean;
}

export default function DiagnosticIntervalSection({ result, loading, error, orgSelected = false }: Props) {
  const practice = result?.scopes.practice;
  const allianceLive = result?.scopes.alliance_live;
  const englandLive = result?.scopes.england_live;
  const bm = result?.benchmark?.metrics;

  const visibleKeys = orgSelected
    ? (["practice", "national", "similar", "alliance"] as const)
    : (["practice", "national"] as const);

  // When a practice is selected, show that practice's 2018 median as the reference line;
  // fall back to national when no practice-level benchmark exists.
  const practiceMedianBm = bm?.["diagnostic_interval.median_di_days"]?.practice ?? null;
  const nationalMedian = resolveBenchmarkValue(bm, "diagnostic_interval.median_di_days", orgSelected);
  const nationalLabel = orgSelected
    ? (practiceMedianBm != null ? "This Practice (2018)" : "All Patients (2018)")
    : "All Patients (2018)";
  const allianceMedian = orgSelected
    ? (allianceLive?.di?.median ?? bm?.["diagnostic_interval.median_di_days"]?.alliance ?? null)
    : null;

  const tableRows = [
    {
      label: "Median diagnostic interval (days)",
      unit: "days",
      practice: practice?.di
        ? { value: practice.di.median, n: practice.di.n ?? undefined, iqr: [practice.di.q1, practice.di.q3] as [number | null, number | null] }
        : null,
      similar: allianceLive?.di ? { value: allianceLive.di.median } : null,
      alliance: englandLive?.di
        ? { value: englandLive.di.median }
        : { value: bm?.["diagnostic_interval.median_di_days"]?.alliance ?? null },
      national: { value: nationalMedian },
    },
  ];

  return (
    <SectionCard
      id="section-di"
      title="Diagnostic Interval (DI)"
      description="Days from when the patient first presented with cancer-related symptoms to the date of cancer diagnosis."
      availability="ready"
      loading={loading}
      error={error}
    >
      <BenchmarkLegend visibleKeys={visibleKeys} orgSelected={orgSelected} />
      <IntervalStripPlot
        patients={practice?.patients ?? []}
        intervalKey="di_days"
        label="Diagnostic Interval"
        median={practice?.di?.median ?? null}
        q1={practice?.di?.q1 ?? null}
        q3={practice?.di?.q3 ?? null}
        nationalMedian={nationalMedian}
        nationalLabel={nationalLabel}
        allianceMedian={allianceMedian}
        maxDays={365}
      />
      <Box sx={{ mt: 2 }}>
        <SummaryStatsTable rows={tableRows} visibleKeys={visibleKeys} orgSelected={orgSelected} caption="Diagnostic interval statistics" />
      </Box>
    </SectionCard>
  );
}
