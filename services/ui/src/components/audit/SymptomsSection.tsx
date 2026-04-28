/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-D5B9FE5F
 *   DI: DI-6E1B71A4
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-D5B9FE5F")
 */
"use client";

/**
 * Symptoms at Referral section.
 *
 * Heatmap of NCDA symptom buckets versus suspected cancer type, plus PPV
 * hero cards by suspected cancer type. Symptom evidence is sourced from
 * Encounter-[:DOCUMENTS {domain: 'symptoms'}]->(Concept) on encounters
 * within the referral lookback window. PPV is calculated against the
 * referral cohort with explicit following-year and unresolved buckets so
 * provisional values are clearly labelled.
 */

import { useEffect, useMemo, useState } from "react";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Grid from "@mui/material/Grid";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";

import SectionCard from "./SectionCard";
import SymptomsDrilldownDialog from "./SymptomsDrilldownDialog";
import type {
  AuditPpvByCancerTypeRow,
  AuditSymptomHeatmapCell,
  AuditSymptoms,
} from "@/lib/analyticsApi";
import { fetchAuditSymptoms } from "@/lib/analyticsApi";

interface Props {
  loading?: boolean;
  error?: string | null;
  orgId?: string;
  dateFrom?: string;
  dateTo?: string;
}

const PPV_HERO_LIMIT = 6;

const COLOUR_HEATMAP_LOW = "#eff6ff";
const COLOUR_HEATMAP_HIGH = "#1d4ed8";
const COLOUR_HEATMAP_NONE = "#f1f5f9";

function lerpColor(t: number, low: string, high: string): string {
  const parse = (hex: string): [number, number, number] => {
    const v = hex.replace("#", "");
    return [
      parseInt(v.substring(0, 2), 16),
      parseInt(v.substring(2, 4), 16),
      parseInt(v.substring(4, 6), 16),
    ];
  };
  const [lr, lg, lb] = parse(low);
  const [hr, hg, hb] = parse(high);
  const r = Math.round(lr + (hr - lr) * t);
  const g = Math.round(lg + (hg - lg) * t);
  const b = Math.round(lb + (hb - lb) * t);
  return `rgb(${r}, ${g}, ${b})`;
}

function cellColor(pct: number, max: number): string {
  if (max <= 0) return COLOUR_HEATMAP_NONE;
  const ratio = Math.min(1, Math.max(0, pct / max));
  if (ratio === 0) return COLOUR_HEATMAP_NONE;
  return lerpColor(ratio, COLOUR_HEATMAP_LOW, COLOUR_HEATMAP_HIGH);
}

function uniqueBuckets(cells: AuditSymptomHeatmapCell[]): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const c of cells) {
    if (!seen.has(c.bucket_label)) {
      seen.add(c.bucket_label);
      out.push(c.bucket_label);
    }
  }
  return out;
}

function uniqueSymptoms(cells: AuditSymptomHeatmapCell[]): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const c of cells) {
    if (!seen.has(c.symptom)) {
      seen.add(c.symptom);
      out.push(c.symptom);
    }
  }
  return out;
}

function topSymptoms(cells: AuditSymptomHeatmapCell[], limit: number): string[] {
  const totals = new Map<string, number>();
  for (const c of cells) {
    totals.set(c.symptom, (totals.get(c.symptom) ?? 0) + c.n);
  }
  const ranked = Array.from(totals.entries())
    .sort((a, b) => b[1] - a[1])
    .map(([label]) => label);
  return ranked.slice(0, limit);
}

interface HeatmapProps {
  cells: AuditSymptomHeatmapCell[];
  symptomLimit?: number;
  emptyLabel: string;
}

function HeatmapTable({ cells, symptomLimit = 12, emptyLabel }: HeatmapProps) {
  const buckets = uniqueBuckets(cells);
  const orderedSymptoms = topSymptoms(cells, symptomLimit);
  if (buckets.length === 0 || orderedSymptoms.length === 0) {
    return (
      <Typography
        variant="body2"
        color="text.secondary"
        sx={{ py: 1.5, fontSize: "0.82rem" }}
      >
        {emptyLabel}
      </Typography>
    );
  }
  const lookup = new Map<string, AuditSymptomHeatmapCell>();
  for (const c of cells) {
    lookup.set(`${c.bucket_label}|${c.symptom}`, c);
  }
  const max = cells.reduce((acc, c) => Math.max(acc, c.pct ?? 0), 0);
  return (
    <Box sx={{ overflowX: "auto" }}>
      <Box
        component="table"
        sx={{
          borderCollapse: "collapse",
          fontSize: "0.74rem",
          width: "100%",
          "& th, & td": { padding: "4px 6px", textAlign: "left" },
          "& th": {
            fontWeight: 600,
            color: "text.secondary",
            verticalAlign: "bottom",
          },
        }}
      >
        <thead>
          <tr>
            <th style={{ minWidth: 160 }}>Cancer type</th>
            <th style={{ width: 64 }}>Cohort</th>
            {orderedSymptoms.map((s) => (
              <th
                key={s}
                style={{
                  writingMode: "vertical-rl",
                  transform: "rotate(180deg)",
                  whiteSpace: "nowrap",
                  height: 110,
                }}
              >
                {s}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {buckets.map((bucket) => {
            const sample = cells.find((c) => c.bucket_label === bucket);
            return (
              <tr key={bucket}>
                <td style={{ fontWeight: 600, whiteSpace: "nowrap" }}>{bucket}</td>
                <td style={{ color: "var(--mui-palette-text-secondary)" }}>
                  {sample?.cohort_n ?? 0}
                </td>
                {orderedSymptoms.map((s) => {
                  const cell = lookup.get(`${bucket}|${s}`);
                  const pct = cell?.pct ?? 0;
                  const n = cell?.n ?? 0;
                  return (
                    <td key={s}>
                      <Tooltip
                        title={`${bucket} — ${s}: n=${n} (${pct}%)`}
                        arrow
                        placement="top"
                      >
                        <Box
                          sx={{
                            backgroundColor: cellColor(pct, max),
                            color: pct / Math.max(max, 1) > 0.5 ? "#fff" : "#0f172a",
                            borderRadius: 0.5,
                            textAlign: "center",
                            px: 0.5,
                            py: 0.25,
                            minWidth: 36,
                            fontVariantNumeric: "tabular-nums",
                          }}
                        >
                          {pct > 0 ? `${pct}%` : "·"}
                        </Box>
                      </Tooltip>
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </Box>
    </Box>
  );
}

interface PpvCardProps {
  row: AuditPpvByCancerTypeRow;
}

function PpvHeroCard({ row }: PpvCardProps) {
  const ppvLabel = row.ppv_pct == null ? "n/a" : `${row.ppv_pct}%`;
  return (
    <Box
      sx={{
        border: "1px solid",
        borderColor: "divider",
        borderRadius: 1,
        p: 2,
        height: "100%",
        display: "flex",
        flexDirection: "column",
        gap: 0.75,
      }}
    >
      <Typography variant="subtitle2" sx={{ fontWeight: 700, lineHeight: 1.2 }}>
        {row.cancer_type}
      </Typography>
      <Stack direction="row" alignItems="baseline" spacing={1}>
        <Typography variant="h5" sx={{ fontWeight: 700 }}>
          {ppvLabel}
        </Typography>
        <Typography variant="caption" color="text.secondary">
          PPV (resolved cohort)
        </Typography>
      </Stack>
      <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
        <Chip
          size="small"
          label={`Referrals: ${row.referrals_n}`}
          sx={{ fontSize: "0.7rem" }}
        />
        <Chip
          size="small"
          color="success"
          label={`Diagnosed: ${row.diagnosed_in_year_n}`}
          sx={{ fontSize: "0.7rem" }}
        />
        <Chip
          size="small"
          label={`No cancer: ${row.no_cancer_in_year_n}`}
          sx={{ fontSize: "0.7rem" }}
        />
        {row.diagnosed_following_year_n > 0 && (
          <Chip
            size="small"
            color="warning"
            variant="outlined"
            label={`Y+1 diagnosis: ${row.diagnosed_following_year_n}`}
            sx={{ fontSize: "0.7rem" }}
          />
        )}
        {row.unresolved_n > 0 && (
          <Chip
            size="small"
            variant="outlined"
            label={`Unresolved: ${row.unresolved_n}`}
            sx={{ fontSize: "0.7rem" }}
          />
        )}
      </Stack>
      {row.provisional && (
        <Typography variant="caption" color="warning.main" sx={{ fontSize: "0.7rem" }}>
          Provisional - cohort still has unresolved or following-year cases.
        </Typography>
      )}
    </Box>
  );
}

export default function SymptomsSection({
  loading: parentLoading,
  error: parentError,
  orgId,
  dateFrom,
  dateTo,
}: Props) {
  const [data, setData] = useState<AuditSymptoms | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [drilldownOpen, setDrilldownOpen] = useState(false);
  const [view, setView] = useState<"suspected" | "diagnosed">("suspected");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchAuditSymptoms(orgId, dateFrom, dateTo)
      .then((d) => {
        if (!cancelled) setData(d);
      })
      .catch(() => {
        if (!cancelled) setError("Unable to load symptom data.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [orgId, dateFrom, dateTo]);

  const heroPpv = useMemo<AuditPpvByCancerTypeRow[]>(() => {
    if (!data?.ppv_by_suspected_cancer_type) return [];
    return data.ppv_by_suspected_cancer_type.slice(0, PPV_HERO_LIMIT);
  }, [data]);

  const heatmapCells =
    view === "suspected"
      ? data?.heatmap_by_suspected_cancer_type ?? []
      : data?.heatmap_by_diagnosed_cancer_type ?? [];

  const totalSymptoms = data?.symptoms?.filter((s) => s.n > 0).length ?? 0;
  const totalHeatmapSymptoms = uniqueSymptoms(heatmapCells).length;

  return (
    <SectionCard
      id="section-symptoms"
      title="Symptoms at Referral"
      description="Distinct-per-patient symptom evidence from the referral lookback window (NCDA symptoms ValueSet). Heatmap clusters symptoms against suspected and diagnosed cancer type. PPV cards summarise referral-cohort outcomes with explicit unresolved and following-year buckets."
      availability="ready"
      loading={parentLoading || loading}
      error={parentError || error}
    >
      {!loading && data ? (
        <Box>
          <Stack
            direction={{ xs: "column", md: "row" }}
            spacing={1}
            alignItems={{ md: "center" }}
            justifyContent="space-between"
            sx={{ mb: 2 }}
          >
            <Typography variant="subtitle2" sx={{ fontWeight: 600, fontSize: "0.85rem" }}>
              PPV by suspected cancer type
            </Typography>
            <Typography variant="caption" color="text.secondary">
              Cohort: {data.cohort_n} patients, {data.total_referrals} referrals,
              {" "}{totalSymptoms} symptoms recorded ({totalHeatmapSymptoms} in heatmap).
            </Typography>
          </Stack>
          {heroPpv.length > 0 ? (
            <Grid container spacing={2} sx={{ mb: 3 }}>
              {heroPpv.map((row) => (
                <Grid key={row.cancer_type} size={{ xs: 12, sm: 6, md: 4, lg: 2 }}>
                  <PpvHeroCard row={row} />
                </Grid>
              ))}
            </Grid>
          ) : (
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
              No PPV cohorts available for this window.
            </Typography>
          )}

          <Stack
            direction="row"
            spacing={1}
            alignItems="center"
            justifyContent="space-between"
            sx={{ mb: 1, flexWrap: "wrap", gap: 1 }}
          >
            <Typography variant="subtitle2" sx={{ fontWeight: 600, fontSize: "0.85rem" }}>
              Symptom clustering by {view === "suspected" ? "suspected" : "diagnosed"} cancer type
            </Typography>
            <Stack direction="row" spacing={1}>
              <Button
                variant={view === "suspected" ? "contained" : "outlined"}
                size="small"
                onClick={() => setView("suspected")}
              >
                Suspected
              </Button>
              <Button
                variant={view === "diagnosed" ? "contained" : "outlined"}
                size="small"
                onClick={() => setView("diagnosed")}
              >
                Diagnosed
              </Button>
              <Button
                variant="outlined"
                size="small"
                onClick={() => setDrilldownOpen(true)}
              >
                Breakdown
              </Button>
            </Stack>
          </Stack>
          <HeatmapTable
            cells={heatmapCells}
            emptyLabel={
              view === "suspected"
                ? "No symptom evidence in the suspected-cancer cohort window."
                : "No symptom evidence in the diagnosed-cancer cohort window."
            }
          />

          <Typography
            variant="caption"
            color="text.secondary"
            display="block"
            sx={{ mt: 2 }}
          >
            Heatmap shows the share of patients in each cancer-type bucket that
            had at least one occurrence of the symptom in the referral lookback
            window. PPV uses the referral cohort as denominator; following-year
            diagnoses are excluded from the no-cancer bucket and unresolved
            referrals are reported separately.
          </Typography>

          <SymptomsDrilldownDialog
            open={drilldownOpen}
            onClose={() => setDrilldownOpen(false)}
            orgId={orgId}
            dateFrom={dateFrom}
            dateTo={dateTo}
          />
        </Box>
      ) : !loading ? (
        <Typography variant="body2" color="text.secondary" sx={{ py: 1.5 }}>
          Symptom data is not yet available for this practice.
        </Typography>
      ) : (
        <Box sx={{ display: "flex", justifyContent: "center", py: 3 }}>
          <CircularProgress size={28} />
        </Box>
      )}
    </SectionCard>
  );
}
