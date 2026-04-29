/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-2E8544FD
 *   DI: DI-C65FD45B
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-2E8544FD")
 */
"use client";

import { useState } from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import SectionCard from "./SectionCard";
import IntervalStripPlot from "./IntervalStripPlot";
import SummaryStatsTable from "./SummaryStatsRow";
import BenchmarkLegend, { resolveBenchmarkValue } from "./BenchmarkLegend";
import ChartZoomDialog from "./ChartZoomDialog";
import type { AuditIntervals, AuditSectionResult } from "@/lib/analyticsApi";
import { useAuditBenchmarkOverlay } from "@/context/AuditBenchmarkOverlayContext";
import { buildAuditBarVisibleKeys } from "@/lib/auditVisibleKeys";

interface Props {
  result: AuditSectionResult<AuditIntervals> | null;
  loading: boolean;
  error?: string | null;
  orgSelected?: boolean;
}

export default function DiagnosticIntervalSection({ result, loading, error, orgSelected = false }: Props) {
  const [zoomOpen, setZoomOpen] = useState(false);
  const { showCancerAlliance, showAllPatients } = useAuditBenchmarkOverlay();
  const visibleKeys = buildAuditBarVisibleKeys(orgSelected, showCancerAlliance, showAllPatients);
  const practice = result?.scopes.practice;
  const allianceLive = result?.scopes.alliance_live;
  const englandLive = result?.scopes.england_live;
  const bm = result?.benchmark?.metrics;

  // When a practice is selected, show that practice's 2018 median as the reference line;
  // fall back to national when no practice-level benchmark exists.
  const practiceMedianBm = bm?.["diagnostic_interval.median_di_days"]?.practice ?? null;
  const nationalMedian = resolveBenchmarkValue(bm, "diagnostic_interval.median_di_days", orgSelected);
  const nationalLabel = orgSelected
    ? (practiceMedianBm != null ? "This Practice (2018)" : "All Patients (2018)")
    : "All Patients (2018)";
  const allianceMedian =
    orgSelected && showCancerAlliance ? (allianceLive?.di?.median ?? null) : null;

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
        : null,
      national: { value: nationalMedian },
    },
  ];

  return (
    <SectionCard
      id="section-di"
      title="Time to Diagnosis (Diagnostic Interval, DI)"
      description="How many days passed from when the patient first saw their GP with possible cancer symptoms to when cancer was confirmed."
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
        onZoom={() => setZoomOpen(true)}
      />
      <ChartZoomDialog
        open={zoomOpen}
        onClose={() => setZoomOpen(false)}
        title="Time to Diagnosis \u2014 Diagnostic Interval"
        subtitle="Each dot represents one patient. Dots further right = longer interval."
        maxWidth="lg"
        contentHeight={400}
      >
        <Box sx={{ width: "100%", display: "flex", flexDirection: "column" }}>
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
            chartHeight={320}
          />
        </Box>
      </ChartZoomDialog>
      {(practice?.di?.n ?? 0) > (practice?.patients?.length ?? 0) && (
        <Typography variant="caption" color="text.secondary" sx={{ display: "block", textAlign: "right", mt: 0.5 }}>
          Showing {practice!.patients.length} of {practice!.di!.n} episodes in the chart.
          Median and IQR are calculated from all {practice!.di!.n} episodes.
        </Typography>
      )}
      <Box sx={{ mt: 2 }}>
        <SummaryStatsTable rows={tableRows} visibleKeys={visibleKeys} orgSelected={orgSelected} caption="Diagnostic interval statistics" />
      </Box>
    </SectionCard>
  );
}
