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
import FormControlLabel from "@mui/material/FormControlLabel";
import Switch from "@mui/material/Switch";
import Typography from "@mui/material/Typography";
import SectionCard from "./SectionCard";
import IntervalStripPlot from "./IntervalStripPlot";
import { resolveBenchmarkValue } from "./BenchmarkLegend";
import ChartZoomDialog from "./ChartZoomDialog";
import {
  type AuditIntervals,
  type AuditSectionResult,
} from "@/lib/analyticsApi";
import { useAuditBenchmarkOverlay } from "@/context/AuditBenchmarkOverlayContext";

interface Props {
  result: AuditSectionResult<AuditIntervals> | null;
  loading: boolean;
  error?: string | null;
  orgSelected?: boolean;
}

export default function DiagnosticIntervalSection({ result, loading, error, orgSelected = false }: Props) {
  const [zoomOpen, setZoomOpen] = useState(false);
  const [showBenign, setShowBenign] = useState(true);
  const { showCancerAlliance } = useAuditBenchmarkOverlay();

  const bm = result?.benchmark?.metrics;
  const practiceMedianBm = bm?.["diagnostic_interval.median_di_days"]?.practice ?? null;
  const nationalMedian = resolveBenchmarkValue(bm, "diagnostic_interval.median_di_days", orgSelected);
  const nationalLabel = orgSelected
    ? (practiceMedianBm != null ? "This Practice (2018)" : "All Patients (2018)")
    : "All Patients (2018)";

  const practice = result?.scopes?.practice ?? null;
  const allianceLive = result?.scopes?.alliance_live;

  const cancerMedian = practice?.di_cancer?.median ?? null;
  const benignMedian = practice?.di_benign?.median ?? null;

  const stripPlotProps = {
    patients: practice?.patients ?? [],
    intervalKey: "di_days" as const,
    label: "Diagnostic Interval",
    median: practice?.di?.median ?? null,
    q1: practice?.di?.q1 ?? null,
    q3: practice?.di?.q3 ?? null,
    cancerMedian,
    benignMedian,
    showBenign,
    nationalMedian,
    nationalLabel,
    allianceMedian:
      orgSelected && showCancerAlliance ? (allianceLive?.di?.median ?? null) : null,
    maxDays: 365,
  };

  return (
    <SectionCard
      id="section-di"
      title="Time to Diagnosis (Diagnostic Interval, DI)"
      description="Days from the patient's first GP contact with cancer symptoms to confirmed diagnosis. Red = cancer confirmed, green = benign or excluded outcome. Click any dot to open the patient record."
      availability="ready"
      loading={loading}
      error={error}
    >
      <Box sx={{ display: "flex", alignItems: "center", justifyContent: "flex-end", mb: 1 }}>
        <FormControlLabel
          control={
            <Switch
              size="small"
              checked={showBenign}
              onChange={(e) => setShowBenign(e.target.checked)}
            />
          }
          label={<Typography variant="caption">Show benign/excluded</Typography>}
          sx={{ mr: 0 }}
        />
      </Box>

      <IntervalStripPlot {...stripPlotProps} onZoom={() => setZoomOpen(true)} />
      <ChartZoomDialog
        open={zoomOpen}
        onClose={() => setZoomOpen(false)}
        title="Time to Diagnosis — Diagnostic Interval"
        subtitle="Red dots = cancer confirmed, green dots = benign/excluded. Further right = longer time to diagnosis."
        maxWidth="lg"
      >
        <IntervalStripPlot {...stripPlotProps} chartHeight={360} />
      </ChartZoomDialog>
    </SectionCard>
  );
}
