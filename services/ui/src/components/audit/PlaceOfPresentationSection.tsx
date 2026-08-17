/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-2E8544FD
 *   DI: DI-C65FD45B
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-2E8544FD")
 */
"use client";

import { useMemo, useState } from "react";
import Box from "@mui/material/Box";
import CircularProgress from "@mui/material/CircularProgress";
import Grid from "@mui/material/Grid";
import IconButton from "@mui/material/IconButton";
import Stack from "@mui/material/Stack";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import OpenInFullIcon from "@mui/icons-material/OpenInFull";
import {
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip as ChartTooltip,
} from "recharts";

import SectionCard from "./SectionCard";
import EvolutionDetailDialog from "./EvolutionDetailDialog";
import type { AuditPlaceRow, AuditSectionResult } from "@/lib/analyticsApi";
import { fetchAuditPlaceOfPresentation } from "@/lib/analyticsApi";
import { useOrgId } from "@/context/OrgContext";

import {
  useAuditYearWindows,
  BASELINE_YEAR,
} from "./_useAuditYearWindows";
// Stable colour map keyed by normalised place label so the same segment
// always renders the same colour regardless of sort order across years.
const PLACE_COLOUR_MAP: Record<string, string> = {
  "gp surgery":           "#2563EB", // blue
  "a&e":                  "#EA580C", // orange
  "a&e / emergency":      "#EA580C",
  "accident and emergency": "#EA580C",
  "emergency":            "#EA580C",
  "screening programme":  "#0891B2", // cyan
  "screening":            "#0891B2",
  "hospital":             "#7C3AED", // purple
  "pharmacy":             "#DB2777", // pink
  "not recorded":         "#94A3B8", // light slate
  "other non-gp":         "#CA8A04", // amber
  "other / unknown":      "#64748B", // slate
  "other":                "#64748B",
  "non-gp":               "#CA8A04",
};

// Fallback palette for place values not in the map above.
const FALLBACK_COLOURS = ["#9338ff", "#B45309", "#6D28D9", "#BE123C", "#0369A1"];

const PLACE_DISPLAY: Record<string, string> = {
  gp_surgery:               "GP Surgery",
  "gp surgery":             "GP Surgery",
  "general practice":       "GP Surgery",
  "general practitioner":   "GP Surgery",
  ae:                       "A&E",
  a_and_e:                  "A&E",
  "a&e":                    "A&E",
  "a&e / emergency":        "A&E / Emergency",
  "accident and emergency":  "A&E / Emergency",
  "screening programme":    "Screening Programme",
  hospital:                 "Hospital",
  pharmacy:                 "Pharmacy",
  "not recorded":           "Not Recorded",
  "other / unknown":        "Other / Unknown",
};

function normalisePlaceKey(raw: string): string {
  return raw.toLowerCase().replace(/[_-]+/g, " ").replace(/\s+/g, " ").trim();
}

function formatPlace(raw: string): string {
  const trimmed = raw.trim();
  const key = normalisePlaceKey(trimmed);
  return PLACE_DISPLAY[key] ?? trimmed;
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


interface Props {
  result: AuditSectionResult<AuditPlaceRow[]> | null;
  loading: boolean;
  error?: string | null;
  orgSelected?: boolean;
  /**
   * @deprecated Resolved internally via useOrgId so every audit section
   *   shares one source of truth for the org filter.
   */
  orgId?: string;
}

function PlacePieCard({
  yearLabel,
  rows,
  sampleN,
  loading = false,
  isBaseline = false,
  onZoom,
}: {
  yearLabel: string;
  rows: AuditPlaceRow[];
  sampleN: number;
  loading?: boolean;
  isBaseline?: boolean;
  onZoom?: () => void;
}) {
  const innerRows = rows
    .filter((row) => row.pct > 0)
    .map((row) => ({ ...row, place: formatPlace(row.place) }));
  // Assign fallback index only to rows not found in PLACE_COLOUR_MAP so that
  // known places always get their stable colour.
  let fallbackCounter = 0;
  const innerColours = innerRows.map((row) => {
    const key = normalisePlaceKey(row.place);
    if (PLACE_COLOUR_MAP[key]) return PLACE_COLOUR_MAP[key];
    return FALLBACK_COLOURS[(fallbackCounter++) % FALLBACK_COLOURS.length];
  });
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
        position: "relative",
      }}
    >
      <Box sx={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between" }}>
        <Box>
          <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
            {yearLabel}
          </Typography>
          <Typography variant="caption" color="text.secondary">
            {isBaseline ? "NCDA baseline" : sampleN > 0 ? `n = ${sampleN}` : "No cases"}
          </Typography>
        </Box>
        {onZoom && (
          <Tooltip title="Expand breakdown">
            <IconButton
              size="small"
              onClick={onZoom}
              aria-label={`Expand ${yearLabel} place of presentation breakdown`}
              sx={{ mt: -0.5, mr: -0.5, color: "text.secondary" }}
            >
              <OpenInFullIcon sx={{ fontSize: 14 }} />
            </IconButton>
          </Tooltip>
        )}
      </Box>

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
                outerRadius={86}
                stroke="#FFFFFF"
                strokeWidth={1}
              >
                {innerRows.map((row, idx) => (
                  <Cell
                    key={`${yearLabel}-${row.place}`}
                    fill={innerColours[idx]}
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
                  bgcolor: innerColours[idx],
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

interface DialogState {
  yearLabel: string;
  rows: AuditPlaceRow[];
  sampleN: number;
  isBaseline: boolean;
}

function PlaceBreakdownTable({
  rows,
  sampleN,
  isBaseline,
}: {
  rows: AuditPlaceRow[];
  sampleN: number;
  isBaseline: boolean;
}) {
  const sorted = [...rows]
    .filter((r) => r.pct > 0 || (r.n ?? 0) > 0)
    .sort((a, b) => b.pct - a.pct);

  if (sorted.length === 0) {
    return (
      <Typography variant="body2" color="text.secondary" sx={{ py: 2 }}>
        No place of presentation data available.
      </Typography>
    );
  }

  return (
    <Table size="small" aria-label="Place of presentation breakdown">
      <TableHead>
        <TableRow>
          <TableCell sx={{ fontWeight: 700, fontSize: "0.78rem" }}>
            Place of first presentation
          </TableCell>
          {!isBaseline && (
            <TableCell align="right" sx={{ fontWeight: 700, fontSize: "0.78rem", whiteSpace: "nowrap" }}>
              n
            </TableCell>
          )}
          <TableCell align="right" sx={{ fontWeight: 700, fontSize: "0.78rem" }}>
            %
          </TableCell>
        </TableRow>
      </TableHead>
      <TableBody>
        {sorted.map((row) => {
          const key = normalisePlaceKey(row.place);
          const colour = PLACE_COLOUR_MAP[key] ?? "#64748B";
          return (
            <TableRow key={row.place} hover>
              <TableCell sx={{ fontSize: "0.8rem" }}>
                <Stack direction="row" alignItems="center" spacing={1}>
                  <Box
                    aria-hidden="true"
                    sx={{
                      width: 9,
                      height: 9,
                      borderRadius: "50%",
                      bgcolor: colour,
                      flexShrink: 0,
                    }}
                  />
                  <span>{formatPlace(row.place)}</span>
                </Stack>
              </TableCell>
              {!isBaseline && (
                <TableCell align="right" sx={{ fontSize: "0.8rem" }}>
                  {row.n ?? "--"}
                </TableCell>
              )}
              <TableCell align="right" sx={{ fontWeight: 600, fontSize: "0.8rem" }}>
                {row.pct}%
              </TableCell>
            </TableRow>
          );
        })}
        {!isBaseline && sampleN > 0 && (
          <TableRow>
            <TableCell sx={{ fontWeight: 700, fontSize: "0.8rem", borderTop: "2px solid", borderColor: "divider" }}>
              Total
            </TableCell>
            <TableCell align="right" sx={{ fontWeight: 700, fontSize: "0.8rem", borderTop: "2px solid", borderColor: "divider" }}>
              {sampleN}
            </TableCell>
            <TableCell align="right" sx={{ fontWeight: 700, fontSize: "0.8rem", borderTop: "2px solid", borderColor: "divider" }}>
              100%
            </TableCell>
          </TableRow>
        )}
      </TableBody>
    </Table>
  );
}

export default function PlaceOfPresentationSection({
  result,
  loading,
  error,
  orgSelected = false,
}: Props) {
  const orgId = useOrgId();
  const { liveYears } = useAuditYearWindows<AuditPlaceRow[]>(
    fetchAuditPlaceOfPresentation,
    { orgId },
  );

  const baselineRows = useMemo(
    () => buildBaselineRows(result?.benchmark, orgSelected),
    [result?.benchmark, orgSelected],
  );

  const [dialog, setDialog] = useState<DialogState | null>(null);

  return (
    <SectionCard
      id="section-place-of-presentation"
      title="Place of Presentation"
      description="Where patients first presented — pie charts per year. Click the expand icon on any card for the full breakdown table with counts and percentages."
      availability="ready"
      loading={loading}
      loadingSkeletonVariant="pieGrid"
      error={error}
    >
      <Box>
        <Grid container spacing={2} sx={{ alignItems: "stretch" }}>
          <Grid size={{ xs: 12, sm: 6, md: 3 }}>
            <PlacePieCard
              yearLabel={String(BASELINE_YEAR)}
              rows={baselineRows}
              sampleN={0}
              isBaseline
              onZoom={() =>
                setDialog({
                  yearLabel: `${BASELINE_YEAR} NCDA Baseline`,
                  rows: baselineRows,
                  sampleN: 0,
                  isBaseline: true,
                })
              }
            />
          </Grid>
          {liveYears.map((state) => (
            <Grid key={state.year} size={{ xs: 12, sm: 6, md: 3 }}>
              <PlacePieCard
                yearLabel={String(state.year)}
                rows={state.data ?? []}
                sampleN={totalN(state.data)}
                loading={state.loading}
                onZoom={
                  state.loading || !state.data
                    ? undefined
                    : () =>
                        setDialog({
                          yearLabel: String(state.year),
                          rows: state.data ?? [],
                          sampleN: totalN(state.data),
                          isBaseline: false,
                        })
                }
              />
            </Grid>
          ))}
        </Grid>
      </Box>

      <EvolutionDetailDialog
        open={dialog !== null}
        onClose={() => setDialog(null)}
        title={`Place of Presentation — ${dialog?.yearLabel ?? ""}`}
        subtitle={
          dialog?.isBaseline
            ? "2018 NCDA published baseline. Only GP Surgery and A&E percentages are available nationally."
            : `${dialog?.sampleN ?? 0} episodes with a recorded place of first presentation.`
        }
        maxWidth="sm"
      >
        {dialog && (
          <PlaceBreakdownTable
            rows={dialog.rows}
            sampleN={dialog.sampleN}
            isBaseline={dialog.isBaseline}
          />
        )}
      </EvolutionDetailDialog>
    </SectionCard>
  );
}
