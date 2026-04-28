/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-EF5F7455
 *   DI: DI-38AE4EA1
 *   Risk: R-E00F9C3C
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-EF5F7455")
 */
"use client";

/**
 * Drill-down dialog for the Cancer Stage at Diagnosis evolution view.
 *
 * Renders one row per NCDA canonical cancer type (CANCER_TYPE_OPTIONS
 * minus the catch-all sentinels). Each row has four cells -- the 2018
 * NCDA published baseline plus three live calendar years -- exposing
 * the same evolution signal at the per-cancer-type level. Cells with
 * no live data show an explicit "No data" placeholder; cancer types
 * whose published baseline is null (e.g. brain, leukaemia, lymphoma,
 * myeloma, haematological) render a "Stage convention N/A" row.
 *
 * Backed by the per-year datasets fetched in CancerStageEvolutionSection;
 * no extra network calls are issued from this component.
 */

import { useMemo } from "react";
import Box from "@mui/material/Box";
import Dialog from "@mui/material/Dialog";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import IconButton from "@mui/material/IconButton";
import Typography from "@mui/material/Typography";
import CloseIcon from "@mui/icons-material/Close";

import {
  CANCER_TYPE_OPTIONS,
  CANCER_TYPE_NO_INFORMATION,
  CANCER_TYPE_OTHER,
  CANCER_TYPE_UNKNOWN_PRIMARY,
} from "@/lib/cancerTypes";
import { resolveBaseline2019 } from "@/lib/cancerTypeKeys";
import type { AuditCancerStageSummary } from "@/lib/analyticsApi";
import CancerStagePerTypeRow, {
  type PerTypeYearCell,
} from "./CancerStagePerTypeRow";

const CATCH_ALL_TYPES = new Set<string>([
  CANCER_TYPE_NO_INFORMATION,
  CANCER_TYPE_OTHER,
  CANCER_TYPE_UNKNOWN_PRIMARY,
]);

const BASELINE_YEAR_LABEL = "2018";

export interface YearDataset {
  yearLabel: string;
  data: AuditCancerStageSummary | null;
}

export interface CancerStageEvolutionDialogProps {
  open: boolean;
  onClose: () => void;
  /**
   * Live calendar-year datasets in chronological order
   * (earliest live year first, current year last). Each entry's
   * `data.by_cancer_type` is consumed for per-type cells.
   */
  liveYears: YearDataset[];
  bm:
    | Record<
        string,
        { practice?: number | null; alliance?: number | null; national?: number | null }
      >
    | null
    | undefined;
}

interface AggregatedTypeYear {
  earlyPct: number | null;
  latePct: number | null;
  totalN: number;
}

function canonicalToBaselineKey(canonical: string): string {
  return canonical.toLowerCase().replace(/\s+/g, "_");
}

function aggregatePerTypeYear(
  data: AuditCancerStageSummary | null,
  canonical: string,
): AggregatedTypeYear {
  if (!data) return { earlyPct: null, latePct: null, totalN: 0 };
  const rows = data.by_cancer_type ?? [];
  let earlyN = 0;
  let lateN = 0;
  let unknownN = 0;
  for (const row of rows) {
    if (row.cancer_type !== canonical) continue;
    if (row.stage_group === "early") earlyN += row.n ?? 0;
    else if (row.stage_group === "late") lateN += row.n ?? 0;
    else unknownN += row.n ?? 0;
  }
  const total = earlyN + lateN + unknownN;
  if (total <= 0) return { earlyPct: null, latePct: null, totalN: 0 };
  return {
    earlyPct: Math.round((earlyN * 1000) / total) / 10,
    latePct: Math.round((lateN * 1000) / total) / 10,
    totalN: total,
  };
}

export default function CancerStageEvolutionDialog({
  open,
  onClose,
  liveYears,
  bm,
}: CancerStageEvolutionDialogProps) {
  const orderedTypes = useMemo(
    () =>
      CANCER_TYPE_OPTIONS.filter((canonical) => !CATCH_ALL_TYPES.has(canonical)),
    [],
  );

  const yearLabels = useMemo(
    () => [BASELINE_YEAR_LABEL, ...liveYears.map((y) => y.yearLabel)],
    [liveYears],
  );

  return (
    <Dialog
      open={open}
      onClose={onClose}
      maxWidth="lg"
      fullWidth
      aria-labelledby="cancer-stage-evolution-dialog-title"
    >
      <DialogTitle
        id="cancer-stage-evolution-dialog-title"
        sx={{
          pr: 6,
          fontSize: "1.05rem",
          fontWeight: 700,
        }}
      >
        Cancer stage at diagnosis -- by cancer type
        <Typography
          variant="caption"
          component="div"
          sx={{ color: "text.secondary", fontWeight: 400, mt: 0.25 }}
        >
          One row per NCDA cancer type. Each row repeats the four-year
          evolution: 2018 NCDA baseline followed by three live calendar
          years. Cells with no live data are marked explicitly.
        </Typography>
        <IconButton
          aria-label="Close drill-down"
          onClick={onClose}
          sx={{
            position: "absolute",
            right: 8,
            top: 8,
            color: "text.secondary",
          }}
        >
          <CloseIcon />
        </IconButton>
      </DialogTitle>

      <DialogContent dividers sx={{ p: 0 }}>
        <Box
          role="row"
          sx={{
            position: "sticky",
            top: 0,
            zIndex: 1,
            bgcolor: "background.paper",
            display: "grid",
            gridTemplateColumns: "minmax(160px, 1.4fr) repeat(4, minmax(80px, 1fr)) 70px",
            alignItems: "center",
            gap: 1.25,
            py: 1,
            px: 1,
            borderBottom: "1px solid",
            borderColor: "divider",
            fontSize: "0.7rem",
            fontWeight: 700,
            color: "text.secondary",
            textTransform: "uppercase",
            letterSpacing: "0.04em",
          }}
        >
          <Box>Cancer type</Box>
          {yearLabels.map((label) => (
            <Box key={label} sx={{ textAlign: "center" }}>
              {label}
            </Box>
          ))}
          <Box sx={{ textAlign: "right" }}>vs 2018</Box>
        </Box>

        <Box>
          {orderedTypes.map((canonical) => {
            const baselineKey = canonicalToBaselineKey(canonical);
            const baselineEarly = resolveBaseline2019(baselineKey, bm);

            const cells: PerTypeYearCell[] = [
              {
                yearLabel: BASELINE_YEAR_LABEL,
                earlyPct: baselineEarly,
                latePct: null,
                totalN: 0,
                isBaseline: true,
              },
              ...liveYears.map((y) => {
                const agg = aggregatePerTypeYear(y.data, canonical);
                return {
                  yearLabel: y.yearLabel,
                  earlyPct: agg.earlyPct,
                  latePct: agg.latePct,
                  totalN: agg.totalN,
                };
              }),
            ];

            return (
              <CancerStagePerTypeRow
                key={canonical}
                cancerKey={baselineKey}
                baselineEarlyPct={baselineEarly}
                cells={cells}
                bm={bm}
              />
            );
          })}
        </Box>
      </DialogContent>
    </Dialog>
  );
}
