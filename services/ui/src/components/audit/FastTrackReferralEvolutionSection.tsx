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
import Button from "@mui/material/Button";
import Grid from "@mui/material/Grid";
import Typography from "@mui/material/Typography";
import BubbleChartOutlinedIcon from "@mui/icons-material/BubbleChartOutlined";

import {
  fetchAuditFastTrackReferrals,
  type AuditFastTrackReferralRow,
  type AuditSectionResult,
} from "@/lib/analyticsApi";
import { useOrgId } from "@/context/OrgContext";
import SectionCard from "./SectionCard";
import CancerTypeRadarCard, { type AxisDatum } from "./CancerTypeRadarCard";
import NSSOutcomeSankeyDialog from "./NSSOutcomeSankeyDialog";

// ---------------------------------------------------------------------------
// SNOMED concept ID → display label.
// Keyed by concept ID string — these are the source of truth, matching
// FAST_TRACK_REFERRAL_IDS in libs/domains/ncda_concept_sets.py exactly.
// Numerical order matches the concept set so the axis order is stable.
// ---------------------------------------------------------------------------

export const FTR_CONCEPT_LABELS: Record<string, string> = {
  "276281000000104": "Skin",
  "276311000000101": "Gynaecological",
  "276341000000100": "Breast",
  "276371000000106": "Children's Tumour",
  "276401000000108": "Colorectal",
  "276431000000102": "Urological",
  "276461000000107": "Haematology",
  "276491000000101": "Lung",
  "276521000000103": "Sarcoma",
  "276551000000108": "Upper GI",
  "276581000000102": "Brain Tumour",
  "280521000000108": "Head & Neck",
  "892201000000106": "Lower GI",
  "1556551000000104": "NSS",
  "__uncoded__": "Uncoded site",
};

export const NSS_CONCEPT_ID = "1556551000000104";

// Stable axis order: numerical order of concept IDs
const FTR_AXIS_ORDER = Object.keys(FTR_CONCEPT_LABELS);

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function calendarYearWindow(year: number): { from: string; to: string } {
  return { from: `${year}-01-01`, to: `${year}-12-31` };
}

function buildAxesForYear(
  rows: AuditFastTrackReferralRow[] | null,
): AxisDatum[] {
  // Key by concept_id — the SNOMED source of truth
  const lookup = new Map<string, number>();
  const countLookup = new Map<string, number>();
  for (const row of rows ?? []) {
    const cid = row.concept_id;
    if (cid) {
      lookup.set(cid, (lookup.get(cid) ?? 0) + (row.pct ?? 0));
      countLookup.set(cid, (countLookup.get(cid) ?? 0) + (row.n ?? 0));
    }
  }
  return FTR_AXIS_ORDER.map((cid) => ({
    key: cid,
    label: FTR_CONCEPT_LABELS[cid] ?? cid,
    value: lookup.has(cid) ? (lookup.get(cid) as number) : null,
    count: countLookup.has(cid) ? (countLookup.get(cid) as number) : null,
  }));
}

function totalSampleN(rows: AuditFastTrackReferralRow[] | null): number {
  if (!rows) return 0;
  return rows.reduce((acc, r) => acc + (r.n ?? 0), 0);
}

function computeMaxScale(allAxisGroups: AxisDatum[][]): number {
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

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type LiveYearState = {
  year: number;
  loading: boolean;
  rows: AuditFastTrackReferralRow[] | null;
  error: string | null;
};

interface Props {
  result: AuditSectionResult<AuditFastTrackReferralRow[]> | null;
  loading: boolean;
  error?: string | null;
  orgSelected?: boolean;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function FastTrackReferralEvolutionSection({
  result,
  loading,
  error,
  orgSelected = false,
}: Props) {
  const orgId = useOrgId();

  const currentYear = new Date().getUTCFullYear();
  const liveYears = useMemo(
    () => [currentYear - 2, currentYear - 1, currentYear],
    [currentYear],
  );

  const [yearStates, setYearStates] = useState<LiveYearState[]>(() =>
    liveYears.map((year) => ({ year, loading: true, rows: null, error: null })),
  );

  const [nssDialogOpen, setNssDialogOpen] = useState(false);

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
          const data = await fetchAuditFastTrackReferrals(
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
            rows: null as AuditFastTrackReferralRow[] | null,
            error:
              e instanceof Error
                ? e.message
                : `Unable to load ${year} fast-track referral data.`,
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

  const liveAxesByYear = useMemo(
    () => yearStates.map((state) => buildAxesForYear(state.rows)),
    [yearStates],
  );

  const maxScale = useMemo(
    () => computeMaxScale(liveAxesByYear),
    [liveAxesByYear],
  );

  const allYearsEmpty = yearStates.every(
    (y) => !y.loading && (!y.rows || y.rows.length === 0),
  );

  return (
    <>
      <SectionCard
        id="section-ftr-types"
        title="Fast Track Referral Types"
        description="Distribution of fast-track (2WW) referral tumour sites. Each card covers a calendar year. NSS = Non-Site-Specific symptoms pathway."
        availability="ready"
        loading={loading}
        loadingSkeletonVariant="pieGrid"
        error={error}
      >
        {allYearsEmpty ? (
          <Typography
            variant="body2"
            color="text.secondary"
            sx={{ py: 3, textAlign: "center" }}
          >
            No fast-track referral data available yet for this practice.
          </Typography>
        ) : (
          <Box>
            <Box sx={{ display: "flex", justifyContent: "flex-end", mb: 1.5 }}>
              <Button
                size="small"
                variant="outlined"
                startIcon={<BubbleChartOutlinedIcon fontSize="small" />}
                onClick={() => setNssDialogOpen(true)}
                aria-label="View NSS referral outcomes Sankey diagram"
                sx={{ fontSize: "0.72rem", py: 0.4, px: 1 }}
              >
                NSS Outcomes
              </Button>
            </Box>
            <Grid container spacing={2}>
              <Grid size={{ xs: 12, sm: 6, md: 3 }}>
                <Box
                  sx={{
                    display: "flex",
                    flexDirection: "column",
                    border: "1px solid",
                    borderColor: "divider",
                    borderRadius: 2,
                    p: 1.5,
                    bgcolor: "background.paper",
                    height: "100%",
                    minHeight: 280,
                  }}
                >
                  <Typography
                    component="h3"
                    sx={{ fontSize: "0.95rem", fontWeight: 700, color: "text.primary" }}
                  >
                    2018
                  </Typography>
                  <Typography
                    variant="caption"
                    sx={{ color: "text.secondary", fontSize: "0.7rem" }}
                  >
                    No baseline
                  </Typography>
                  <Box
                    sx={{
                      flex: 1,
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      px: 1,
                    }}
                  >
                    <Typography
                      variant="caption"
                      sx={{
                        color: "text.secondary",
                        fontStyle: "italic",
                        fontSize: "0.78rem",
                        textAlign: "center",
                      }}
                    >
                      Fast-track referral type breakdown was not published in the 2018 NCDA audit.
                    </Typography>
                  </Box>
                </Box>
              </Grid>
              {yearStates.map((state, idx) => {
                const axes = liveAxesByYear[idx] ?? FTR_AXIS_ORDER.map((cid) => ({
                  key: cid,
                  label: FTR_CONCEPT_LABELS[cid] ?? cid,
                  value: null,
                }));
                return (
                  <Grid key={state.year} size={{ xs: 12, sm: 6, md: 3 }}>
                    <CancerTypeRadarCard
                      yearLabel={String(state.year)}
                      axes={axes}
                      baseline={null}
                      totalN={totalSampleN(state.rows)}
                      maxScale={maxScale}
                      loading={state.loading}
                      hasLiveData={(state.rows?.length ?? 0) > 0}
                    />
                  </Grid>
                );
              })}
            </Grid>
          </Box>
        )}
      </SectionCard>

      <NSSOutcomeSankeyDialog
        open={nssDialogOpen}
        onClose={() => setNssDialogOpen(false)}
      />
    </>
  );
}
