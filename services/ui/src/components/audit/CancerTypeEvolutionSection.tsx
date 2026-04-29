/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-BFF68D36
 *   DI: DI-077C8810
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-BFF68D36")
 */
"use client";

import { useEffect, useMemo, useState } from "react";
import Box from "@mui/material/Box";
import Grid from "@mui/material/Grid";
import Typography from "@mui/material/Typography";
import ChartZoomDialog from "./ChartZoomDialog";

import {
  CANCER_TYPE_OPTIONS,
  CANCER_TYPE_OTHER,
  normaliseCancerType,
} from "@/lib/cancerTypes";
import {
  fetchAuditCancerType,
  type AuditCancerTypeRow,
  type AuditSectionResult,
} from "@/lib/analyticsApi";
import { useOrgId } from "@/context/OrgContext";
import SectionCard from "./SectionCard";
import CancerTypeRadarCard, { type AxisDatum } from "./CancerTypeRadarCard";

const BASELINE_YEAR = 2018;
const TOP_N_AXES = 13;

type LiveYearState = {
  year: number;
  loading: boolean;
  rows: AuditCancerTypeRow[] | null;
  error: string | null;
};

interface Props {
  result: AuditSectionResult<AuditCancerTypeRow[]> | null;
  loading: boolean;
  error?: string | null;
  orgSelected?: boolean;
}

interface BaselineEntry {
  type: string;
  pct: number;
}

interface AxisSource {
  type: string;
  pct: number | null;
  count?: number | null;
}

function canonicalToMetricKey(canonical: string): string {
  return canonical.toLowerCase().replace(/\s+/g, "_");
}

function extractBaseline(
  bm: Record<
    string,
    { practice?: number | null; alliance?: number | null; national?: number | null }
  > | null | undefined,
  orgSelected: boolean,
): BaselineEntry[] {
  if (!bm) return [];
  const out: BaselineEntry[] = [];
  for (const canonical of CANCER_TYPE_OPTIONS) {
    const key = `condition_type.${canonicalToMetricKey(canonical)}`;
    const entry = bm[key];
    if (!entry) continue;
    const value = orgSelected
      ? (entry.practice ?? entry.national ?? null)
      : (entry.national ?? null);
    if (value == null) continue;
    out.push({ type: canonical, pct: Number(value) });
  }
  return out;
}

function calendarYearWindow(year: number): { from: string; to: string } {
  return {
    from: `${year}-01-01`,
    to: `${year}-12-31`,
  };
}

function ensureOtherAxis(types: string[]): string[] {
  return types.includes(CANCER_TYPE_OTHER)
    ? types
    : [...types, CANCER_TYPE_OTHER];
}

function buildAxisOrder(
  baseline: BaselineEntry[],
  liveYears: LiveYearState[],
): string[] {
  const ranked = [...baseline].sort((a, b) => b.pct - a.pct);
  const top = ranked.slice(0, TOP_N_AXES).map((b) => b.type);
  if (top.length >= TOP_N_AXES) return ensureOtherAxis(top);

  // Fallback: not enough baseline coverage. Top up the axis order from any
  // live-year prevalence so the radar is still meaningful before benchmarks
  // are available.
  const seen = new Set(top);
  const livePrev = new Map<string, number>();
  for (const ly of liveYears) {
    for (const row of ly.rows ?? []) {
      const canonical = normaliseCancerType(row.cancer_type);
      const prev = livePrev.get(canonical) ?? 0;
      livePrev.set(canonical, prev + (row.pct ?? 0));
    }
  }
  const liveRanked = [...livePrev.entries()]
    .filter(([type]) => !seen.has(type) && type !== CANCER_TYPE_OTHER)
    .sort((a, b) => b[1] - a[1])
    .map(([type]) => type);

  const combined = [...top];
  for (const t of liveRanked) {
    if (combined.length >= TOP_N_AXES) break;
    combined.push(t);
  }
  return ensureOtherAxis(combined);
}

function buildAxesForYear(
  axisOrder: string[],
  rows: AuditCancerTypeRow[] | BaselineEntry[] | null,
  rowAccessor: (row: AuditCancerTypeRow | BaselineEntry) => AxisSource,
): AxisDatum[] {
  const lookup = new Map<string, number>();
  const countLookup = new Map<string, number>();
  let otherTotal = 0;
  let otherCount: number | null = null;
  let otherSeen = false;
  for (const row of rows ?? []) {
    const { type, pct, count } = rowAccessor(row);
    if (pct == null) continue;
    if (axisOrder.includes(type) && type !== CANCER_TYPE_OTHER) {
      lookup.set(type, (lookup.get(type) ?? 0) + pct);
      if (count != null) {
        countLookup.set(type, (countLookup.get(type) ?? 0) + count);
      }
    } else {
      otherTotal += pct;
      if (count != null) otherCount = (otherCount ?? 0) + count;
      otherSeen = true;
    }
  }
  return axisOrder.map((key) => {
    if (key === CANCER_TYPE_OTHER) {
      return {
        key,
        label: CANCER_TYPE_OTHER,
        value: otherSeen ? otherTotal : null,
        count: otherCount,
      };
    }
    return {
      key,
      label: key,
      value: lookup.has(key) ? (lookup.get(key) as number) : null,
      count: countLookup.has(key) ? (countLookup.get(key) as number) : null,
    };
  });
}

function totalSampleN(rows: AuditCancerTypeRow[] | null): number {
  if (!rows) return 0;
  return rows.reduce((acc, r) => acc + (r.n ?? 0), 0);
}

function computeSharedScale(allAxisGroups: AxisDatum[][]): number {
  let max = 0;
  for (const group of allAxisGroups) {
    for (const datum of group) {
      if (datum.value != null && datum.value > max) max = datum.value;
    }
  }
  if (max <= 0) return 40;
  const stepped = Math.ceil((max + 5) / 10) * 10;
  return Math.max(20, stepped);
}

export default function CancerTypeEvolutionSection({
  result,
  loading,
  error,
  orgSelected = false,
}: Props) {
  const orgId = useOrgId();
  const bm = result?.benchmark?.metrics;

  const currentYear = new Date().getUTCFullYear();
  const liveYears = useMemo(
    () => [currentYear - 2, currentYear - 1, currentYear],
    [currentYear],
  );

  const [yearStates, setYearStates] = useState<LiveYearState[]>(() =>
    liveYears.map((year) => ({
      year,
      loading: true,
      rows: null,
      error: null,
    })),
  );

  useEffect(() => {
    let cancelled = false;

    setYearStates(
      liveYears.map((year) => ({ year, loading: true, rows: null, error: null })),
    );

    const orgArg = orgId ?? undefined;

    Promise.all(
      liveYears.map(async (year) => {
        const window = calendarYearWindow(year);
        try {
          const data = await fetchAuditCancerType(
            orgArg,
            window.from,
            window.to,
          );
          return {
            year,
            rows: data?.scopes?.practice ?? [],
            error: null as string | null,
          };
        } catch (e) {
          return {
            year,
            rows: null as AuditCancerTypeRow[] | null,
            error:
              e instanceof Error
                ? e.message
                : `Unable to load ${year} cancer type data.`,
          };
        }
      }),
    ).then((results) => {
      if (cancelled) return;
      setYearStates(
        results.map((r) => ({
          year: r.year,
          loading: false,
          rows: r.rows,
          error: r.error,
        })),
      );
    });

    return () => {
      cancelled = true;
    };
  }, [orgId, liveYears]);

  const baseline = useMemo(
    () => extractBaseline(bm, orgSelected),
    [bm, orgSelected],
  );

  const axisOrder = useMemo(
    () => buildAxisOrder(baseline, yearStates),
    [baseline, yearStates],
  );

  const baselineAxes = useMemo(
    () =>
      buildAxesForYear(axisOrder, baseline, (row) => {
        const b = row as BaselineEntry;
        return { type: b.type, pct: b.pct };
      }),
    [axisOrder, baseline],
  );

  const liveAxesByYear = useMemo(
    () =>
      yearStates.map((state) =>
        buildAxesForYear(axisOrder, state.rows, (row) => {
          const r = row as AuditCancerTypeRow;
          return {
            type: normaliseCancerType(r.cancer_type),
            pct: r.pct ?? null,
          count: r.n ?? null,
          };
        }),
      ),
    [axisOrder, yearStates],
  );

  const sharedScaleMax = useMemo(
    () => computeSharedScale([baselineAxes, ...liveAxesByYear]),
    [baselineAxes, liveAxesByYear],
  );

  const baselineHasData = baseline.length > 0;

  const [zoomedYear, setZoomedYear] = useState<string | null>(null);
  const zoomedYearState = yearStates.find((y) => String(y.year) === zoomedYear) ?? null;
  const zoomedAxes =
    zoomedYear === String(BASELINE_YEAR)
      ? baselineAxes
      : zoomedYearState
        ? liveAxesByYear[yearStates.indexOf(zoomedYearState)]
        : null;
  const zoomedN =
    zoomedYear === String(BASELINE_YEAR)
      ? baseline.length
      : totalSampleN(zoomedYearState?.rows ?? null);

  return (
    <SectionCard
      id="section-cancer-type"
      title="Cancer Type"
      description="How the practice's confirmed-cancer case mix has evolved against the 2018 NCDA baseline. Each card covers a calendar year (Jan-Dec). All radar cards use the same shared percentage scale, and the 2018 polygon is faded onto each live-year card so the reference shape is always visible."
      availability="ready"
      loading={loading}
      error={error}
    >
      {!baselineHasData && yearStates.every((y) => !y.rows || y.rows.length === 0) ? (
        <Typography
          variant="body2"
          color="text.secondary"
          sx={{ py: 3, textAlign: "center" }}
        >
          No cancer type data available yet for this practice.
        </Typography>
      ) : (
        <Box>
          <Box sx={{ display: "flex", gap: 2, mb: 1.5, flexWrap: "wrap" }}>
            <LegendSwatch colour="#92400E" label="2018 NCDA baseline" dashed />
            <LegendSwatch colour="#1D4ED8" label="Live year" />
            <Typography
              variant="caption"
              sx={{ color: "text.secondary", fontSize: "0.75rem" }}
            >
              Shared scale: 0-{sharedScaleMax}%
            </Typography>
          </Box>
          <Grid container spacing={2}>
            <Grid size={{ xs: 12, sm: 6, md: 3 }}>
              <CancerTypeRadarCard
                yearLabel={String(BASELINE_YEAR)}
                axes={baselineAxes}
                baseline={null}
                totalN={baseline.length}
                maxScale={sharedScaleMax}
                isBaseline
                hasLiveData={baselineHasData}
                onZoom={() => setZoomedYear(String(BASELINE_YEAR))}
              />
            </Grid>
            {yearStates.map((state, idx) => (
              <Grid key={state.year} size={{ xs: 12, sm: 6, md: 3 }}>
                <CancerTypeRadarCard
                  yearLabel={String(state.year)}
                  axes={liveAxesByYear[idx]}
                  baseline={baselineAxes}
                  totalN={totalSampleN(state.rows)}
                  maxScale={sharedScaleMax}
                  loading={state.loading}
                  hasLiveData={(state.rows?.length ?? 0) > 0}
                  onZoom={() => setZoomedYear(String(state.year))}
                />
              </Grid>
            ))}
          </Grid>

          {zoomedYear !== null && zoomedAxes !== null && (
            <ChartZoomDialog
              open
              onClose={() => setZoomedYear(null)}
              title={`Cancer Type \u2014 ${zoomedYear}`}
              subtitle={`Shared scale: 0\u2013${sharedScaleMax}%`}
              maxWidth="sm"
              contentHeight={520}
            >
              <CancerTypeRadarCard
                yearLabel={zoomedYear}
                axes={zoomedAxes}
                baseline={zoomedYear === String(BASELINE_YEAR) ? null : baselineAxes}
                totalN={zoomedN}
                maxScale={sharedScaleMax}
                isBaseline={zoomedYear === String(BASELINE_YEAR)}
                hasLiveData={
                  zoomedYear === String(BASELINE_YEAR)
                    ? baselineHasData
                    : (zoomedYearState?.rows?.length ?? 0) > 0
                }
              />
            </ChartZoomDialog>
          )}
        </Box>
      )}
    </SectionCard>
  );
}

interface LegendSwatchProps {
  colour: string;
  label: string;
  dashed?: boolean;
}

function LegendSwatch({ colour, label, dashed = false }: LegendSwatchProps) {
  return (
    <Box sx={{ display: "flex", alignItems: "center", gap: 0.75 }}>
      <Box
        aria-hidden="true"
        sx={{
          width: 18,
          height: 10,
          borderRadius: 1,
          border: `1.5px ${dashed ? "dashed" : "solid"} ${colour}`,
          bgcolor: dashed ? "transparent" : colour,
          opacity: dashed ? 0.85 : 0.35,
          flexShrink: 0,
        }}
      />
      <Typography variant="caption" sx={{ fontSize: "0.75rem", color: "text.secondary" }}>
        {label}
      </Typography>
    </Box>
  );
}
