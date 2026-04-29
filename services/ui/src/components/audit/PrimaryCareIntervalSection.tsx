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

export default function PrimaryCareIntervalSection({ result, loading, error, orgSelected = false }: Props) {
  const [zoomOpen, setZoomOpen] = useState(false);
  const { showCancerAlliance, showAllPatients } = useAuditBenchmarkOverlay();
  const visibleKeys = buildAuditBarVisibleKeys(orgSelected, showCancerAlliance, showAllPatients);
  const practice = result?.scopes.practice;
  const allianceLive = result?.scopes.alliance_live;
  const englandLive = result?.scopes.england_live;
  const bm = result?.benchmark?.metrics;

  // When a practice is selected, show that practice's 2018 median as the reference line;
  // fall back to national when no practice-level benchmark exists.
  const practiceMedianBm = bm?.["primary_care_interval.median_pci_days"]?.practice ?? null;
  const nationalMedian = resolveBenchmarkValue(bm, "primary_care_interval.median_pci_days", orgSelected);
  const nationalLabel = orgSelected
    ? (practiceMedianBm != null ? "This Practice (2018)" : "All Patients (2018)")
    : "All Patients (2018)";
  const allianceMedian =
    orgSelected && showCancerAlliance ? (allianceLive?.pci?.median ?? null) : null;

  const tableRows = [
    {
      label: "Median primary care interval (days)",
      unit: "days",
      practice: practice?.pci
        ? { value: practice.pci.median, n: practice.pci.n ?? undefined, iqr: [practice.pci.q1, practice.pci.q3] as [number | null, number | null] }
        : null,
      similar: allianceLive?.pci ? { value: allianceLive.pci.median } : null,
      alliance: englandLive?.pci
        ? { value: englandLive.pci.median }
        : null,
      national: { value: nationalMedian },
    },
  ];

  return (
    <SectionCard
      id="section-pci"
      title="Time to Referral (Primary Care Interval, PCI)"
      description="How many days passed from when the patient first saw their GP with possible cancer symptoms to when they were referred for tests."
      availability="ready"
      loading={loading}
      error={error}
    >
      <BenchmarkLegend visibleKeys={visibleKeys} orgSelected={orgSelected} />
      <IntervalStripPlot
        patients={practice?.patients ?? []}
        intervalKey="pci_days"
        label="Primary Care Interval"
        median={practice?.pci?.median ?? null}
        q1={practice?.pci?.q1 ?? null}
        q3={practice?.pci?.q3 ?? null}
        nationalMedian={nationalMedian}
        nationalLabel={nationalLabel}
        allianceMedian={allianceMedian}
        maxDays={90}
        noDataMessage="No first-presentation dates are captured for this audit cohort, so time to referral cannot be calculated without showing misleading 0-day intervals."
        onZoom={() => setZoomOpen(true)}
      />
      <ChartZoomDialog
        open={zoomOpen}
        onClose={() => setZoomOpen(false)}
        title="Time to Referral \u2014 Primary Care Interval"
        subtitle="Each dot represents one patient. Dots further right = longer interval."
        maxWidth="lg"
        contentHeight={400}
      >
        <Box sx={{ width: "100%", display: "flex", flexDirection: "column" }}>
          <IntervalStripPlot
            patients={practice?.patients ?? []}
            intervalKey="pci_days"
            label="Primary Care Interval"
            median={practice?.pci?.median ?? null}
            q1={practice?.pci?.q1 ?? null}
            q3={practice?.pci?.q3 ?? null}
            nationalMedian={nationalMedian}
            nationalLabel={nationalLabel}
            allianceMedian={allianceMedian}
            maxDays={90}
            chartHeight={320}
            noDataMessage="No first-presentation dates are captured for this audit cohort."
          />
        </Box>
      </ChartZoomDialog>
      {(practice?.pci?.n ?? 0) > (practice?.patients?.length ?? 0) && (
        <Typography variant="caption" color="text.secondary" sx={{ display: "block", textAlign: "right", mt: 0.5 }}>
          Showing {practice!.patients.length} of {practice!.pci!.n} episodes in the chart.
          Median and IQR are calculated from all {practice!.pci!.n} episodes.
        </Typography>
      )}
      <Box sx={{ mt: 2 }}>
        <SummaryStatsTable rows={tableRows} visibleKeys={visibleKeys} orgSelected={orgSelected} caption="Primary care interval statistics" />
      </Box>
    </SectionCard>
  );
}
