/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-2E8544FD
 *   DI: DI-C65FD45B
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-2E8544FD")
 */
"use client";

import { useEffect, useMemo, useState } from "react";
import Box from "@mui/material/Box";
import FormControlLabel from "@mui/material/FormControlLabel";
import Switch from "@mui/material/Switch";
import Tab from "@mui/material/Tab";
import Tabs from "@mui/material/Tabs";
import Typography from "@mui/material/Typography";
import SectionCard from "./SectionCard";
import IntervalStripPlot from "./IntervalStripPlot";
import IntervalYearlyBarChart, { type YearBarDatum } from "./IntervalYearlyBarChart";
import SummaryStatsTable from "./SummaryStatsRow";
import BenchmarkLegend, { resolveBenchmarkValue } from "./BenchmarkLegend";
import ChartZoomDialog from "./ChartZoomDialog";
import {
  fetchAuditIntervals,
  type AuditIntervals,
  type AuditSectionResult,
} from "@/lib/analyticsApi";
import { useAuditBenchmarkOverlay } from "@/context/AuditBenchmarkOverlayContext";
import { buildAuditBarVisibleKeys } from "@/lib/auditVisibleKeys";
import { useOrgId } from "@/context/OrgContext";

interface Props {
  result: AuditSectionResult<AuditIntervals> | null;
  loading: boolean;
  error?: string | null;
  orgSelected?: boolean;
}

interface LiveYearState {
  year: number;
  loading: boolean;
  data: AuditIntervals | null;
  error: string | null;
}

function calendarYearWindow(year: number) {
  return { from: `${year}-01-01`, to: `${year}-12-31` };
}

const BASELINE_YEAR = 2018;

export default function DiagnosticIntervalSection({ result, loading, error, orgSelected = false }: Props) {
  const orgId = useOrgId();
  const [zoomOpen, setZoomOpen] = useState(false);
  const [showBenign, setShowBenign] = useState(true);
  const { showCancerAlliance, showAllPatients } = useAuditBenchmarkOverlay();
  const visibleKeys = buildAuditBarVisibleKeys(orgSelected, showCancerAlliance, showAllPatients);

  const bm = result?.benchmark?.metrics;
  const practiceMedianBm = bm?.["diagnostic_interval.median_di_days"]?.practice ?? null;
  const nationalMedian = resolveBenchmarkValue(bm, "diagnostic_interval.median_di_days", orgSelected);
  const nationalLabel = orgSelected
    ? (practiceMedianBm != null ? "This Practice (2018)" : "All Patients (2018)")
    : "All Patients (2018)";

  const currentYear = new Date().getUTCFullYear();
  const liveYears = useMemo(() => [currentYear - 2, currentYear - 1, currentYear], [currentYear]);

  const [selectedYear, setSelectedYear] = useState(String(currentYear));
  const [yearStates, setYearStates] = useState<LiveYearState[]>(() =>
    liveYears.map((y) => ({ year: y, loading: true, data: null, error: null })),
  );

  useEffect(() => {
    let cancelled = false;
    setYearStates(liveYears.map((y) => ({ year: y, loading: true, data: null, error: null })));
    const orgArg = orgId ?? undefined;

    Promise.all(
      liveYears.map(async (year) => {
        const win = calendarYearWindow(year);
        try {
          const res = await fetchAuditIntervals(orgArg, win.from, win.to);
          return { year, data: res?.scopes?.practice ?? null, error: null as string | null };
        } catch (e) {
          return {
            year,
            data: null as AuditIntervals | null,
            error: e instanceof Error ? e.message : `Unable to load ${year} DI data.`,
          };
        }
      }),
    ).then((results) => {
      if (cancelled) return;
      setYearStates(
        results.map((r) => ({ year: r.year, loading: false, data: r.data, error: r.error })),
      );
    });

    return () => { cancelled = true; };
  }, [orgId, liveYears]);

  const selectedState = yearStates.find((s) => String(s.year) === selectedYear);
  const selectedData = selectedState?.data ?? null;

  const yearBars: YearBarDatum[] = [
    {
      year: String(BASELINE_YEAR),
      cancerMedian: nationalMedian,
      benignMedian: null,
      cancerN: 0,
      benignN: 0,
      isBaseline: true,
    },
    ...yearStates.map((s) => ({
      year: String(s.year),
      cancerMedian: s.data?.di_cancer?.median ?? null,
      benignMedian: s.data?.di_benign?.median ?? null,
      cancerN: s.data?.di_cancer?.n ?? 0,
      benignN: s.data?.di_benign?.n ?? 0,
    })),
  ];

  const cancerMedian = selectedData?.di_cancer?.median ?? null;
  const benignMedian = selectedData?.di_benign?.median ?? null;
  const allianceLive = result?.scopes?.alliance_live;
  const englandLive = result?.scopes?.england_live;

  const tableRows = [
    {
      label: `Median DI — cancer confirmed (days) · ${selectedYear}`,
      unit: "days",
      practice: selectedData?.di_cancer?.n
        ? {
            value: cancerMedian,
            n: selectedData.di_cancer.n,
            iqr: [selectedData.di_cancer.q1, selectedData.di_cancer.q3] as [number | null, number | null],
          }
        : null,
      similar: allianceLive?.di ? { value: allianceLive.di.median } : null,
      alliance: englandLive?.di ? { value: englandLive.di.median } : null,
      national: { value: nationalMedian },
    },
    ...(showBenign && (selectedData?.di_benign?.n ?? 0) > 0
      ? [
          {
            label: `Median DI — benign/excluded (days) · ${selectedYear}`,
            unit: "days",
            practice: {
              value: benignMedian,
              n: selectedData!.di_benign!.n,
              iqr: [selectedData!.di_benign!.q1, selectedData!.di_benign!.q3] as [number | null, number | null],
            },
            similar: null,
            alliance: null,
            national: { value: nationalMedian },
          },
        ]
      : []),
  ];

  const stripPlotProps = {
    patients: selectedData?.patients ?? [],
    intervalKey: "di_days" as const,
    label: "Diagnostic Interval",
    median: selectedData?.di?.median ?? null,
    q1: selectedData?.di?.q1 ?? null,
    q3: selectedData?.di?.q3 ?? null,
    cancerMedian,
    benignMedian,
    showBenign,
    nationalMedian,
    nationalLabel,
    allianceMedian:
      orgSelected && showCancerAlliance ? (allianceLive?.di?.median ?? null) : null,
    maxDays: 365,
  };

  const anyLoading = yearStates.some((s) => s.loading) || loading;

  return (
    <SectionCard
      id="section-di"
      title="Time to Diagnosis (Diagnostic Interval, DI)"
      description="How many days passed from when the patient first saw their GP with possible cancer symptoms to when cancer was confirmed."
      availability="ready"
      loading={anyLoading}
      error={error}
    >
      {/* Controls row */}
      <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", mb: 1 }}>
        <BenchmarkLegend visibleKeys={visibleKeys} orgSelected={orgSelected} />
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

      {/* Year-over-year bar chart */}
      <IntervalYearlyBarChart
        yearData={yearBars}
        intervalKey="di"
        showBenign={showBenign}
        selectedYear={selectedYear}
        onSelectYear={setSelectedYear}
      />

      {/* Year selector tabs */}
      <Tabs
        value={selectedYear}
        onChange={(_, v) => setSelectedYear(v as string)}
        variant="scrollable"
        scrollButtons="auto"
        sx={{ mt: 1, mb: 1, minHeight: 32, "& .MuiTab-root": { minHeight: 32, py: 0.5, fontSize: "0.8rem" } }}
        aria-label="Select year for patient-level strip plot"
      >
        {liveYears.map((y) => {
          const state = yearStates.find((s) => s.year === y);
          const n = (state?.data?.di_cancer?.n ?? 0) + (showBenign ? (state?.data?.di_benign?.n ?? 0) : 0);
          return (
            <Tab
              key={y}
              value={String(y)}
              label={`${y}${n > 0 ? ` (${n})` : ""}`}
              disabled={state?.loading}
            />
          );
        })}
      </Tabs>

      {/* Strip plot for selected year */}
      <IntervalStripPlot {...stripPlotProps} onZoom={() => setZoomOpen(true)} />
      <ChartZoomDialog
        open={zoomOpen}
        onClose={() => setZoomOpen(false)}
        title={`Time to Diagnosis — Diagnostic Interval (${selectedYear})`}
        subtitle="Red dots = cancer confirmed, green dots = benign/excluded. Further right = longer time to diagnosis."
        maxWidth="lg"
      >
        <IntervalStripPlot {...stripPlotProps} chartHeight={360} />
      </ChartZoomDialog>

      {/* Summary stats table */}
      <Box sx={{ mt: 2 }}>
        <SummaryStatsTable
          rows={tableRows}
          visibleKeys={visibleKeys}
          orgSelected={orgSelected}
          caption="Diagnostic interval statistics"
        />
      </Box>
    </SectionCard>
  );
}
