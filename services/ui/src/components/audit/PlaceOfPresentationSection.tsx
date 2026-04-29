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
import CircularProgress from "@mui/material/CircularProgress";
import Grid from "@mui/material/Grid";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import {
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip as ChartTooltip,
} from "recharts";

import SectionCard from "./SectionCard";
import type { AuditPlaceRow, AuditSectionResult } from "@/lib/analyticsApi";
import { fetchAuditPlaceOfPresentation } from "@/lib/analyticsApi";

const BASELINE_YEAR = 2018;
const GP_GREEN = "#16A34A";
const NON_GP_RED = "#DC2626";
const INNER_COLOURS = [
  "#2563EB",
  "#7C3AED",
  "#EA580C",
  "#0891B2",
  "#CA8A04",
  "#64748B",
  "#DB2777",
  "#0F766E",
];

const PLACE_DISPLAY: Record<string, string> = {
  gp_surgery: "GP Surgery",
  "gp surgery": "GP Surgery",
  "general practice": "GP Surgery",
  "general practitioner": "GP Surgery",
  ae: "A&E",
  a_and_e: "A&E",
  "a&e": "A&E",
  hospital: "Hospital",
  pharmacy: "Pharmacy",
  "not recorded": "Not Recorded",
};

function formatPlace(raw: string): string {
  const trimmed = raw.trim();
  const key = normalisePlaceKey(trimmed);
  return PLACE_DISPLAY[key] ?? trimmed;
}

function normalisePlaceKey(raw: string): string {
  return raw.toLowerCase().replace(/[_-]+/g, " ").replace(/\s+/g, " ").trim();
}

function isGpPlace(raw: string): boolean {
  return normalisePlaceKey(raw) === "gp surgery";
}

function calendarYearWindow(year: number): { from: string; to: string } {
  return {
    from: `${year}-01-01`,
    to: `${year}-12-31`,
  };
}

function totalN(rows: AuditPlaceRow[] | null): number {
  return (rows ?? []).reduce((acc, row) => acc + (row.n ?? 0), 0);
}

function resolveBmValue(
  bm:
    | Record<
        string,
        { practice?: number | null; alliance?: number | null; national?: number | null }
      >
    | null
    | undefined,
  key: string,
  orgSelected: boolean,
): number | null {
  if (!bm?.[key]) return null;
  const entry = bm[key];
  const value = orgSelected
    ? (entry.practice ?? entry.national ?? null)
    : (entry.national ?? null);
  return value == null ? null : Number(value);
}

function buildBaselineRows(
  bm: AuditSectionResult<AuditPlaceRow[]>["benchmark"] | null | undefined,
  orgSelected: boolean,
): AuditPlaceRow[] {
  const metrics = bm?.metrics;
  const gpPct = resolveBmValue(
    metrics,
    "place_of_presentation.gp_surgery_pct",
    orgSelected,
  );
  if (gpPct == null) return [];

  const aePct = resolveBmValue(
    metrics,
    "place_of_presentation.ae_pct",
    orgSelected,
  );
  const nonGpPct = Math.max(0, 100 - gpPct);
  const knownAePct = aePct == null ? null : Math.min(aePct, nonGpPct);
  const otherPct = knownAePct == null ? nonGpPct : Math.max(0, nonGpPct - knownAePct);

  return [
    { place: "GP Surgery", n: 0, pct: gpPct },
    ...(knownAePct != null && knownAePct > 0
      ? [{ place: "A&E", n: 0, pct: knownAePct }]
      : []),
    ...(otherPct > 0
      ? [{ place: knownAePct == null ? "Non-GP" : "Other non-GP", n: 0, pct: otherPct }]
      : []),
  ];
}

function buildOuterRows(rows: AuditPlaceRow[] | null): AuditPlaceRow[] {
  const gpPct = (rows ?? [])
    .filter((row) => isGpPlace(formatPlace(row.place)))
    .reduce((acc, row) => acc + row.pct, 0);
  const nonGpPct = Math.max(0, 100 - gpPct);
  return [
    { place: "GP Surgery", n: 0, pct: Number(gpPct.toFixed(1)) },
    { place: "Non-GP", n: 0, pct: Number(nonGpPct.toFixed(1)) },
  ].filter((row) => row.pct > 0);
}

interface Props {
  result: AuditSectionResult<AuditPlaceRow[]> | null;
  loading: boolean;
  error?: string | null;
  orgSelected?: boolean;
  orgId?: string;
}

interface LiveYearState {
  year: number;
  loading: boolean;
  data: AuditPlaceRow[] | null;
}

function PlacePieCard({
  yearLabel,
  rows,
  sampleN,
  loading = false,
  isBaseline = false,
}: {
  yearLabel: string;
  rows: AuditPlaceRow[];
  sampleN: number;
  loading?: boolean;
  isBaseline?: boolean;
}) {
  const innerRows = rows
    .filter((row) => row.pct > 0)
    .map((row) => ({ ...row, place: formatPlace(row.place) }));
  const outerRows = buildOuterRows(innerRows);
  const gpPct = outerRows.find((row) => isGpPlace(row.place))?.pct ?? null;
  const hasData = innerRows.length > 0;

  return (
    <Box
      sx={{
        height: "100%",
        border: "1px solid",
        borderColor: "divider",
        borderRadius: 1.5,
        p: 1.5,
        bgcolor: "background.paper",
      }}
    >
      <Stack direction="row" justifyContent="space-between" alignItems="flex-start" spacing={1}>
        <Box>
          <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
            {yearLabel}
          </Typography>
          <Typography variant="caption" color="text.secondary">
            {isBaseline ? "NCDA baseline" : sampleN > 0 ? `n = ${sampleN}` : "No cases"}
          </Typography>
        </Box>
        <Typography
          variant="caption"
          sx={{
            px: 0.75,
            py: 0.25,
            borderRadius: 999,
            bgcolor: gpPct == null ? "grey.100" : "rgba(22,163,74,0.12)",
            color: gpPct == null ? "text.secondary" : GP_GREEN,
            fontWeight: 700,
          }}
        >
          {gpPct == null ? "No data" : `${gpPct}% GP`}
        </Typography>
      </Stack>

      <Box
        role="img"
        aria-label={`${yearLabel} place of presentation pie chart`}
        sx={{ height: 220, mt: 1 }}
      >
        {loading ? (
          <Box sx={{ display: "grid", placeItems: "center", height: "100%" }}>
            <CircularProgress size={28} aria-label={`Loading ${yearLabel} place data`} />
          </Box>
        ) : hasData ? (
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={innerRows}
                dataKey="pct"
                nameKey="place"
                cx="50%"
                cy="50%"
                outerRadius={58}
                stroke="#FFFFFF"
                strokeWidth={1}
              >
                {innerRows.map((row, idx) => (
                  <Cell
                    key={`${yearLabel}-${row.place}`}
                    fill={INNER_COLOURS[idx % INNER_COLOURS.length]}
                  />
                ))}
              </Pie>
              <Pie
                data={outerRows}
                dataKey="pct"
                nameKey="place"
                cx="50%"
                cy="50%"
                innerRadius={68}
                outerRadius={86}
                stroke="#FFFFFF"
                strokeWidth={1}
              >
                {outerRows.map((row) => (
                  <Cell
                    key={`${yearLabel}-${row.place}`}
                    fill={isGpPlace(row.place) ? GP_GREEN : NON_GP_RED}
                  />
                ))}
              </Pie>
              <ChartTooltip formatter={(value) => `${value}%`} />
            </PieChart>
          </ResponsiveContainer>
        ) : (
          <Box sx={{ display: "grid", placeItems: "center", height: "100%" }}>
            <Typography variant="body2" color="text.secondary">
              No place data available
            </Typography>
          </Box>
        )}
      </Box>

      <Stack spacing={0.75}>
        {innerRows.slice(0, 5).map((row, idx) => (
          <Stack
            key={`${yearLabel}-legend-${row.place}`}
            direction="row"
            alignItems="center"
            justifyContent="space-between"
            spacing={1}
          >
            <Stack direction="row" alignItems="center" spacing={0.75} sx={{ minWidth: 0 }}>
              <Box
                aria-hidden="true"
                sx={{
                  width: 9,
                  height: 9,
                  borderRadius: "50%",
                  bgcolor: INNER_COLOURS[idx % INNER_COLOURS.length],
                  flexShrink: 0,
                }}
              />
              <Typography variant="caption" noWrap color="text.secondary">
                {row.place}
              </Typography>
            </Stack>
            <Typography variant="caption" sx={{ fontWeight: 700 }}>
              {row.pct}%
            </Typography>
          </Stack>
        ))}
      </Stack>
    </Box>
  );
}

export default function PlaceOfPresentationSection({
  result,
  loading,
  error,
  orgSelected = false,
  orgId,
}: Props) {
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
    })),
  );

  useEffect(() => {
    let cancelled = false;
    setYearStates(
      liveYearNumbers.map((year) => ({
        year,
        loading: true,
        data: null,
      })),
    );

    Promise.all(
      liveYearNumbers.map(async (year) => {
        const window = calendarYearWindow(year);
        try {
          const res = await fetchAuditPlaceOfPresentation(
            orgId,
            window.from,
            window.to,
          );
          return {
            year,
            data: res?.scopes?.practice ?? null,
          };
        } catch {
          return {
            year,
            data: null,
          };
        }
      }),
    ).then((rows) => {
      if (cancelled) return;
      setYearStates(
        rows.map((row) => ({
          year: row.year,
          loading: false,
          data: row.data,
        })),
      );
    });

    return () => {
      cancelled = true;
    };
  }, [orgId, liveYearNumbers]);

  const baselineRows = useMemo(
    () => buildBaselineRows(result?.benchmark, orgSelected),
    [result?.benchmark, orgSelected],
  );

  return (
    <SectionCard
      id="section-place-of-presentation"
      title="Place of Presentation"
      description="Where patients first presented, shown as 2018 NCDA baseline plus the last two complete calendar years and the current year. Inner pies show the place mix; outer rings highlight GP surgery in green versus non-GP presentation in red."
      availability="ready"
      loading={loading}
      error={error}
    >
      <Box>
        <Box sx={{ display: "flex", gap: 2, mb: 1.5, flexWrap: "wrap" }}>
          <Stack direction="row" alignItems="center" spacing={0.75}>
            <Box
              aria-hidden="true"
              sx={{ width: 18, height: 10, borderRadius: 0.5, bgcolor: GP_GREEN }}
            />
            <Typography variant="caption" color="text.secondary">
              Outer ring: GP Surgery
            </Typography>
          </Stack>
          <Stack direction="row" alignItems="center" spacing={0.75}>
            <Box
              aria-hidden="true"
              sx={{ width: 18, height: 10, borderRadius: 0.5, bgcolor: NON_GP_RED }}
            />
            <Typography variant="caption" color="text.secondary">
              Outer ring: Non-GP
            </Typography>
          </Stack>
        </Box>

        <Grid container spacing={2} sx={{ alignItems: "stretch" }}>
          <Grid size={{ xs: 12, sm: 6, md: 3 }}>
            <PlacePieCard
              yearLabel={String(BASELINE_YEAR)}
              rows={baselineRows}
              sampleN={0}
              isBaseline
            />
          </Grid>
          {yearStates.map((state) => (
            <Grid key={state.year} size={{ xs: 12, sm: 6, md: 3 }}>
              <PlacePieCard
                yearLabel={String(state.year)}
                rows={state.data ?? []}
                sampleN={totalN(state.data)}
                loading={state.loading}
              />
            </Grid>
          ))}
        </Grid>
      </Box>
    </SectionCard>
  );
}
