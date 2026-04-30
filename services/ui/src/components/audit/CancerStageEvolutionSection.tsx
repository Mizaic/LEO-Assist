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
 * Cancer Stage at Diagnosis -- year-on-year evolution section.
 *
 * Renders four CancerStageYearCards (2018 NCDA baseline + previous two
 * complete calendar years + current calendar year). The 2018 baseline
 * card uses the published early-stage % from the page-level result's
 * benchmark.metrics; live years are fetched in parallel via three
 * fetchAuditCancerStage calls scoped to Jan-Dec calendar windows.
 *
 * A "Drill down by cancer type" button opens CancerStageEvolutionDialog
 * which repeats the four-year strip per NCDA cancer type (DI-38AE4EA1).
 *
 * Decoupled from the global AnalyticsDateFilter context: the new audit
 * model is year-on-year progression against 2018, so on-page date
 * pickers are intentionally not consumed here.
 */

import { useEffect, useMemo, useState } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Grid from "@mui/material/Grid";
import Typography from "@mui/material/Typography";
import OpenInFullIcon from "@mui/icons-material/OpenInFull";

import {
  fetchAuditCancerStage,
  type AuditCancerStageSummary,
  type AuditSectionResult,
} from "@/lib/analyticsApi";
import { useOrgId } from "@/context/OrgContext";
import SectionCard from "./SectionCard";
import CancerStageYearCard from "./CancerStageYearCard";
import CancerStageEvolutionDialog, {
  type YearDataset,
} from "./CancerStageEvolutionDialog";

const BASELINE_YEAR = 2018;
const C_EARLY = "#16A34A";
const C_LATE = "#EA580C";
const C_GREY = "#CBD5E1";
const C_BENCH18 = "#92400E";

interface LiveYearState {
  year: number;
  loading: boolean;
  data: AuditCancerStageSummary | null;
  error: string | null;
}

interface Props {
  result: AuditSectionResult<AuditCancerStageSummary> | null;
  loading: boolean;
  error?: string | null;
  orgSelected?: boolean;
}

function calendarYearWindow(year: number): { from: string; to: string } {
  return {
    from: `${year}-01-01`,
    to: `${year}-12-31`,
  };
}

function extractStageGroup(
  data: AuditCancerStageSummary | null,
  group: "early" | "late",
): { pct: number | null; n: number | null } {
  if (!data) return { pct: null, n: null };
  const rows =
    data.by_stage_group ??
    data.rows ??
    [];
  const row = rows.find((r) => r.stage_group === group);
  if (!row) return { pct: null, n: null };
  return { pct: row.pct ?? null, n: row.n ?? null };
}

function totalSampleN(data: AuditCancerStageSummary | null): number {
  if (!data) return 0;
  const rows = data.by_stage_group ?? data.rows ?? [];
  return rows.reduce((acc, r) => acc + (r.n ?? 0), 0);
}

function resolveBaselineEarly(
  bm:
    | Record<
        string,
        { practice?: number | null; alliance?: number | null; national?: number | null }
      >
    | null
    | undefined,
  orgSelected: boolean,
): number | null {
  if (!bm) return null;
  const entry = bm["cancer_stage.early_stage_pct"];
  if (!entry) return null;
  const value = orgSelected
    ? (entry.practice ?? entry.national ?? null)
    : (entry.national ?? null);
  return value == null ? null : Number(value);
}

interface LegendSwatchProps {
  colour: string;
  label: string;
  hatched?: boolean;
  dashed?: boolean;
}

function LegendSwatch({
  colour,
  label,
  hatched = false,
  dashed = false,
}: LegendSwatchProps) {
  return (
    <Box sx={{ display: "flex", alignItems: "center", gap: 0.75 }}>
      <Box
        aria-hidden="true"
        sx={{
          width: 18,
          height: 10,
          borderRadius: 0.5,
          border: dashed ? `1.5px dashed ${colour}` : "none",
          bgcolor: dashed ? "transparent" : colour,
          backgroundImage: hatched
            ? `repeating-linear-gradient(45deg, ${colour} 0, ${colour} 3px, #E2E8F0 3px, #E2E8F0 6px)`
            : undefined,
          opacity: dashed ? 1 : 0.85,
          flexShrink: 0,
        }}
      />
      <Typography
        variant="caption"
        sx={{ fontSize: "0.72rem", color: "text.secondary" }}
      >
        {label}
      </Typography>
    </Box>
  );
}

export default function CancerStageEvolutionSection({
  result,
  loading,
  error,
  orgSelected = false,
}: Props) {
  const orgId = useOrgId();
  const bm = result?.benchmark?.metrics;

  const currentYear = new Date().getUTCFullYear();
  const liveYearNumbers = useMemo(
    () => [currentYear - 2, currentYear - 1, currentYear],
    [currentYear],
  );

  const [yearStates, setYearStates] = useState<LiveYearState[]>(() =>
    liveYearNumbers.map((year) => ({
      year,
      loading: true,
      data: null,
      error: null,
    })),
  );

  const [drillOpen, setDrillOpen] = useState(false);

  useEffect(() => {
    let cancelled = false;

    setYearStates(
      liveYearNumbers.map((year) => ({
        year,
        loading: true,
        data: null,
        error: null,
      })),
    );

    const orgArg = orgId ?? undefined;

    Promise.all(
      liveYearNumbers.map(async (year) => {
        const window = calendarYearWindow(year);
        try {
          const res = await fetchAuditCancerStage(
            orgArg,
            window.from,
            window.to,
          );
          return {
            year,
            data: res?.scopes?.practice ?? null,
            error: null as string | null,
          };
        } catch (e) {
          return {
            year,
            data: null as AuditCancerStageSummary | null,
            error:
              e instanceof Error
                ? e.message
                : `Unable to load ${year} cancer stage data.`,
          };
        }
      }),
    ).then((results) => {
      if (cancelled) return;
      setYearStates(
        results.map((r) => ({
          year: r.year,
          loading: false,
          data: r.data,
          error: r.error,
        })),
      );
    });

    return () => {
      cancelled = true;
    };
  }, [orgId, liveYearNumbers]);

  const baselineEarly = useMemo(
    () => resolveBaselineEarly(bm, orgSelected),
    [bm, orgSelected],
  );

  const liveYearDatasets: YearDataset[] = useMemo(
    () =>
      yearStates.map((s) => ({
        yearLabel: String(s.year),
        data: s.data,
      })),
    [yearStates],
  );

  const anyLiveData = yearStates.some((s) => totalSampleN(s.data) > 0);

  return (
    <SectionCard
      id="section-cancer-stage"
      title="Cancer Stage at Diagnosis"
      description="How the practice's stage-at-diagnosis mix has evolved against the 2018 NCDA baseline. Each card covers a calendar year (Jan-Dec). Stage is rarely captured in primary care, so cards may be sparse -- the n badge and warnings show how reliable each card is."
      availability="ready"
      loading={loading}
      loadingSkeletonVariant="segmentedCards"
      error={error}
    >
      <Box>
        <Box
          sx={{
            display: "flex",
            gap: 2,
            mb: 1.5,
            flexWrap: "wrap",
            alignItems: "center",
            justifyContent: "space-between",
          }}
        >
          <Box sx={{ display: "flex", gap: 2, flexWrap: "wrap" }}>
            <LegendSwatch colour={C_EARLY} label="Early (stage 0-2)" />
            <LegendSwatch colour={C_LATE} label="Late (stage 3-4)" />
            <LegendSwatch colour={C_GREY} label="Not staged / unknown" />
            <LegendSwatch colour={C_BENCH18} label="2018 NCDA baseline" dashed />
          </Box>
          <Button
            variant="outlined"
            size="small"
            startIcon={<OpenInFullIcon fontSize="small" />}
            onClick={() => setDrillOpen(true)}
            disabled={!anyLiveData && baselineEarly == null}
            aria-haspopup="dialog"
          >
            Drill down by cancer type
          </Button>
        </Box>

        <Grid container spacing={2}>
          <Grid size={{ xs: 12, sm: 6, md: 3 }}>
            <CancerStageYearCard
              yearLabel={String(BASELINE_YEAR)}
              earlyPct={baselineEarly}
              latePct={null}
              totalN={0}
              coveragePct={null}
              baseline2018Early={baselineEarly}
              isBaseline
            />
          </Grid>
          {yearStates.map((state) => {
            const early = extractStageGroup(state.data, "early");
            const late = extractStageGroup(state.data, "late");
            const total = totalSampleN(state.data);
            const coverage = state.data?.coverage_pct ?? null;
            return (
              <Grid key={state.year} size={{ xs: 12, sm: 6, md: 3 }}>
                <CancerStageYearCard
                  yearLabel={String(state.year)}
                  earlyPct={early.pct}
                  latePct={late.pct}
                  totalN={total}
                  coveragePct={coverage}
                  baseline2018Early={baselineEarly}
                  loading={state.loading}
                />
              </Grid>
            );
          })}
        </Grid>
      </Box>

      <CancerStageEvolutionDialog
        open={drillOpen}
        onClose={() => setDrillOpen(false)}
        liveYears={liveYearDatasets}
        bm={bm}
      />
    </SectionCard>
  );
}
