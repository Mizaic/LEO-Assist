/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-2E8544FD
 *   DI: DI-C65FD45B
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-2E8544FD")
 */
"use client";

import Box from "@mui/material/Box";
import Alert from "@mui/material/Alert";
import SectionCard from "./SectionCard";
import ComparisonBarChart, { type ComparisonDataRow } from "./ComparisonBarChart";
import BenchmarkLegend, { resolveBenchmarkValue } from "./BenchmarkLegend";
import SummaryStatsTable from "./SummaryStatsRow";
import CancerTypeBenchmarkGrid from "./CancerTypeBenchmarkGrid";
import type { AuditSafetyNetting, AuditSectionResult } from "@/lib/analyticsApi";
import { useAuditBenchmarkOverlay } from "@/context/AuditBenchmarkOverlayContext";
import { buildAuditBarVisibleKeys } from "@/lib/auditVisibleKeys";

interface Props {
  result: AuditSectionResult<AuditSafetyNetting> | null;
  loading: boolean;
  error?: string | null;
  orgSelected?: boolean;
}

export default function SafetyNettingSection({ result, loading, error, orgSelected = false }: Props) {
  const { showCancerAlliance, showAllPatients } = useAuditBenchmarkOverlay();
  const visibleKeys = buildAuditBarVisibleKeys(orgSelected, showCancerAlliance, showAllPatients);
  const practice = result?.scopes.practice;
  const allianceLive = result?.scopes.alliance_live;
  const englandLive = result?.scopes.england_live;
  const bm = result?.benchmark?.metrics;

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
      alliance: englandLive ? { value: englandLive.recorded_pct } : null,
      national: { value: resolveBenchmarkValue(bm, "safety_netting.recorded_pct", orgSelected) },
    },
  ];

  // 0% with real episodes almost always means the field has not been captured,
  // not that no safety netting occurred. Surface this distinction clearly.
  const MIN_EPISODES_FOR_ZERO = 5;
  const dataNotCaptured =
    practice != null &&
    practice.recorded_n === 0 &&
    practice.total_episodes >= MIN_EPISODES_FOR_ZERO;

  return (
    <SectionCard
      id="section-safety-netting"
      title="Safety Netting"
      description="Whether a follow-up plan (safety netting) was written in the clinical record at any point during the patient's diagnostic journey. Safety netting means agreeing what to do if symptoms do not improve."
      availability="pipeline_pending"
      loading={loading}
      error={error}
    >
      {dataNotCaptured && (
        <Alert severity="warning" sx={{ mb: 2, fontSize: "0.8rem" }}>
          Safety netting shows as 0% across {practice!.total_episodes} cases.
          This is most likely because the system has not yet read this information from the clinical records.
          Do not use this figure in reports until the reading process is complete.
        </Alert>
      )}
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
      <CancerTypeBenchmarkGrid
        bm={bm}
        section="safety_netting"
        metrics={[{ metricKey: "positive_contribution_pct", label: "Positive contribution %" }]}
        orgSelected={orgSelected}
        heading="2018 Baseline by Cancer Type — Safety Netting Positive Contribution (%)"
        showAlliance2018={orgSelected ? showCancerAlliance : undefined}
        showNational2018={orgSelected ? showAllPatients : undefined}
      />
    </SectionCard>
  );
}
