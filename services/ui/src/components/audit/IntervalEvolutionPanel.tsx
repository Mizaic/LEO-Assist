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
import Typography from "@mui/material/Typography";

import { useOrgId } from "@/context/OrgContext";
import {
  fetchAuditIntervals,
  type AuditIntervalSplitStats,
  type AuditIntervals,
} from "@/lib/analyticsApi";
import IntervalCompositeBoxScatterPlot, {
  type IntervalCompositeStats,
  type IntervalCompositeYearDatum,
} from "./IntervalCompositeBoxScatterPlot";
import { useAuditYearWindows, BASELINE_YEAR } from "./_useAuditYearWindows";

type IntervalFamily = "pci" | "di";
type IntervalKey = "pci_days" | "di_days";

interface Props {
  intervalFamily: IntervalFamily;
  intervalKey: IntervalKey;
  label: string;
  showBenign: boolean;
  onToggleBenign: (show: boolean) => void;
  nationalMedian?: number | null;
  nationalLabel?: string;
  maxDays: number;
}

function splitStats(data: AuditIntervals | null, family: IntervalFamily) {
  if (!data) return { cancer: null, benign: null };
  return family === "pci"
    ? { cancer: data.pci_cancer, benign: data.pci_benign }
    : { cancer: data.di_cancer, benign: data.di_benign };
}

function toBoxStats(stats: AuditIntervalSplitStats | null): IntervalCompositeStats {
  return {
    n: stats?.n ?? 0,
    median: stats?.median ?? null,
    q1: stats?.q1 ?? null,
    q3: stats?.q3 ?? null,
  };
}

export default function IntervalEvolutionPanel({
  intervalFamily,
  intervalKey,
  label,
  showBenign,
  onToggleBenign,
  nationalMedian,
  nationalLabel,
  maxDays,
}: Props) {
  const orgId = useOrgId();
  const { liveYears: yearStates, anyLoading } = useAuditYearWindows<AuditIntervals>(
    fetchAuditIntervals,
    { orgId },
  );

  const yearData: IntervalCompositeYearDatum[] = yearStates.map((state) => {
    const stats = splitStats(state.data, intervalFamily);
    return {
      year: String(state.year),
      cancer: toBoxStats(stats.cancer),
      benign: toBoxStats(stats.benign),
      patients: state.data?.patients ?? [],
    };
  });
  const baselineBox: IntervalCompositeYearDatum | null =
    nationalMedian == null
      ? null
      : {
          year: String(BASELINE_YEAR),
          cancer: { n: 0, median: null, q1: null, q3: null },
          benign: { n: 0, median: null, q1: null, q3: null },
          baseline: { n: 0, median: nationalMedian, q1: null, q3: null },
          patients: [],
          isBaseline: true,
        };
  const compositeData = baselineBox ? [baselineBox, ...yearData] : yearData;
  const yearErrors = yearStates.filter((state) => state.error);

  return (
    <Box>
      {yearErrors.length > 0 && (
        <Typography
          variant="caption"
          color="warning.main"
          sx={{ display: "block", mt: 1 }}
        >
          Some yearly interval data could not be loaded.
        </Typography>
      )}

      {anyLoading ? (
        <Typography
          variant="body2"
          color="text.secondary"
          sx={{ py: 3, textAlign: "center" }}
        >
          Loading yearly referrals...
        </Typography>
      ) : (
        <IntervalCompositeBoxScatterPlot
          yearData={compositeData}
          intervalKey={intervalKey}
          label={label}
          showBenign={showBenign}
          onToggleBenign={onToggleBenign}
          maxDays={maxDays}
          baselineLabel={nationalLabel}
        />
      )}
    </Box>
  );
}
