/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-2E8544FD
 *   DI: DI-C65FD45B
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-2E8544FD")
 */
"use client";

/**
 * Avoidable Delays -- year-on-year evolution section.
 *
 * Renders four cards (2019 NCDA baseline + previous two calendar
 * years + current calendar year). The 2019 NCDA baseline is GP-confirmed
 * (clinicians retrospectively reviewed their own cases). Live year cards
 * show potentially avoidable delays detected automatically from the
 * clinical record: rejected referrals (XaQgL), DNAs (XacSG / XaF81 /
 * Xa1kG or EMIS DNA flag), cancellations, and softer access barriers
 * (unable to contact / patient declined / lost to follow-up). These are
 * NOT clinician-confirmed -- the label "potentially avoidable" makes this
 * distinction explicit on each live card. Scoped to the Jan-Dec window
 * via the shared `outcome_date` audit anchor.
 *
 * Each live year card carries an "Open detail" zoom button that opens
 * a dialog with the four-bucket type breakdown for that year.
 */

import { useMemo, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Grid from "@mui/material/Grid";
import Typography from "@mui/material/Typography";

import {
  fetchAuditCareObstructions,
  type AuditAvoidableDelays,
  type AuditCareObstruction,
  type AuditSectionResult,
} from "@/lib/analyticsApi";
import { useOrgId } from "@/context/OrgContext";
import { resolveBenchmarkValue } from "./BenchmarkLegend";

import SectionCard from "./SectionCard";
import EvolutionDetailDialog from "./EvolutionDetailDialog";
import EvolutionYearCard, { EvolutionLegendSwatch } from "./EvolutionYearCard";
import { useAuditYearWindows, BASELINE_YEAR } from "./_useAuditYearWindows";

const ACCENT = "#B91C1C";
const C_BENCH18 = "#92400E";

// Severity row colours -- the reds and ambers signal "this is a delay
// driver" without overlapping safety-netting's blue/green/orange palette.
const SIGNAL_COLOURS: Record<
  "rejection" | "dna" | "cancellation" | "access_barrier" | "none",
  string
> = {
  rejection: "#B91C1C",       // red: hard stop, worst severity
  dna: "#DC2626",             // bright red: patient no-show
  cancellation: "#D97706",    // amber: re-bookable but still delays
  access_barrier: "#F59E0B",  // light amber: softer access issue
  none: "#9CA3AF",            // grey: no obstruction in window
};

const SIGNAL_LABELS: Record<
  "rejection" | "dna" | "cancellation" | "access_barrier" | "none",
  string
> = {
  rejection:
    "Rejection -- referral returned by service (XaQgL, \"REFERRAL REJECTED\", \"Triage response\")",
  dna: "DNA -- patient did not attend (XacSG / XaF81 / Xa1kG, or EMIS DNA flag)",
  cancellation: "Cancellation -- appointment cancelled by patient or hospital",
  access_barrier:
    "Access barrier -- unable to contact / patient declined / lost to follow-up",
  none: "None -- no obstruction evidence in the encounter window",
};

interface Props {
  result: AuditSectionResult<AuditCareObstruction> | null;
  loading: boolean;
  error?: string | null;
  orgSelected?: boolean;
  /**
   * Avoidable-delays section result from the parent page.  The 2018
   * NCDA does not publish a "care obstruction" baseline, but it does
   * publish the GP-noted avoidable delay rate -- the closest
   * comparable signal (a clinician judging, in hindsight, that the
   * pathway was delayed).  Used to populate the baseline card here
   * so the section is anchored to a real published number rather
   * than an em-dash.
   */
  avoidableDelaysResult?: AuditSectionResult<AuditAvoidableDelays> | null;
}

function formatPct(v: number | null | undefined): string | null {
  if (v == null) return null;
  return `${Math.round(v * 10) / 10}%`;
}

interface SignalRowProps {
  label: string;
  count: number;
  pct: number;
  total: number;
  colour: string;
  emphasis?: boolean;
}

function SignalRow({ label, count, pct, total, colour, emphasis }: SignalRowProps) {
  const widthPct = total > 0 ? (count / total) * 100 : 0;
  return (
    <Box sx={{ mb: 1.25 }}>
      <Box
        sx={{
          display: "flex",
          alignItems: "baseline",
          justifyContent: "space-between",
          gap: 1,
          mb: 0.5,
        }}
      >
        <Typography
          variant="body2"
          sx={{
            fontSize: "0.82rem",
            fontWeight: emphasis ? 700 : 500,
            color: "text.primary",
          }}
        >
          {label}
        </Typography>
        <Typography
          variant="body2"
          sx={{
            fontSize: "0.85rem",
            fontWeight: 700,
            color: colour,
            whiteSpace: "nowrap",
          }}
        >
          {count}{" "}
          <Box component="span" sx={{ color: "text.secondary", fontWeight: 500 }}>
            ({pct.toFixed(1)}%)
          </Box>
        </Typography>
      </Box>
      <Box
        role="progressbar"
        aria-valuenow={Math.round(widthPct)}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={`${label}: ${count} of ${total}`}
        sx={{
          height: 8,
          borderRadius: 1,
          bgcolor: "grey.100",
          overflow: "hidden",
        }}
      >
        <Box
          sx={{
            width: `${widthPct}%`,
            height: "100%",
            bgcolor: colour,
            transition: "width 200ms ease-out",
          }}
        />
      </Box>
    </Box>
  );
}

function SignalBreakdownChart({
  data,
  year,
}: {
  data: AuditCareObstruction;
  year: number;
}) {
  const counts = data.signal_counts ?? {
    rejection: 0,
    dna: 0,
    cancellation: 0,
    access_barrier: 0,
    none: 0,
  };
  const pct = data.signal_pct ?? {
    rejection: 0,
    dna: 0,
    cancellation: 0,
    access_barrier: 0,
    none: 0,
  };
  const total = data.total_episodes ?? 0;
  const recordedN =
    data.recorded_n ??
    counts.rejection + counts.dna + counts.cancellation + counts.access_barrier;
  const recordedPct = data.recorded_pct ?? 0;
  const severeN = data.severe_n ?? counts.rejection + counts.dna;
  const severePct = data.severe_pct ?? pct.rejection + pct.dna;

  if (total === 0) {
    return (
      <Alert severity="info" sx={{ fontSize: "0.85rem" }}>
        No confirmed-cancer episodes closed in {year} yet, so there is
        nothing to break down. Once a case in this window reaches a
        diagnosis or benign-closure outcome it will appear here.
      </Alert>
    );
  }

  return (
    <Box>
      <Box
        sx={{
          display: "grid",
          gridTemplateColumns: { xs: "1fr", sm: "1fr 1fr" },
          gap: 2,
          mb: 2.5,
        }}
      >
        <Box
          sx={{
            border: "1px solid",
            borderColor: "divider",
            borderRadius: 1.5,
            px: 2,
            py: 1.5,
          }}
        >
          <Typography
            variant="caption"
            sx={{
              color: "text.secondary",
              textTransform: "uppercase",
              letterSpacing: 0.5,
              fontWeight: 600,
              fontSize: "0.7rem",
              display: "block",
            }}
          >
            Headline (any potential delay)
          </Typography>
          <Typography
            sx={{
              fontSize: "1.4rem",
              fontWeight: 700,
              color: SIGNAL_COLOURS.rejection,
              lineHeight: 1.1,
              mt: 0.25,
            }}
          >
            {recordedPct.toFixed(1)}%
          </Typography>
          <Typography variant="caption" sx={{ color: "text.secondary", fontSize: "0.78rem" }}>
            {recordedN} of {total} confirmed cancers
          </Typography>
        </Box>
        <Box
          sx={{
            border: "1px solid",
            borderColor: "divider",
            borderRadius: 1.5,
            px: 2,
            py: 1.5,
          }}
        >
          <Typography
            variant="caption"
            sx={{
              color: "text.secondary",
              textTransform: "uppercase",
              letterSpacing: 0.5,
              fontWeight: 600,
              fontSize: "0.7rem",
              display: "block",
            }}
          >
            Severe (rejection + DNA)
          </Typography>
          <Typography
            sx={{
              fontSize: "1.4rem",
              fontWeight: 700,
              color: SIGNAL_COLOURS.rejection,
              lineHeight: 1.1,
              mt: 0.25,
            }}
          >
            {severePct.toFixed(1)}%
          </Typography>
          <Typography variant="caption" sx={{ color: "text.secondary", fontSize: "0.78rem" }}>
            {severeN} of {total} pathways hard-stopped or no-shows
          </Typography>
        </Box>
      </Box>

      <Typography
        variant="subtitle2"
        sx={{
          fontSize: "0.78rem",
          fontWeight: 700,
          textTransform: "uppercase",
          letterSpacing: 0.5,
          color: "text.secondary",
          mb: 1,
        }}
      >
        Severity breakdown
      </Typography>
      <SignalRow
        label={SIGNAL_LABELS.rejection}
        count={counts.rejection}
        pct={pct.rejection}
        total={total}
        colour={SIGNAL_COLOURS.rejection}
        emphasis
      />
      <SignalRow
        label={SIGNAL_LABELS.dna}
        count={counts.dna}
        pct={pct.dna}
        total={total}
        colour={SIGNAL_COLOURS.dna}
        emphasis
      />
      <SignalRow
        label={SIGNAL_LABELS.cancellation}
        count={counts.cancellation}
        pct={pct.cancellation}
        total={total}
        colour={SIGNAL_COLOURS.cancellation}
      />
      <SignalRow
        label={SIGNAL_LABELS.access_barrier}
        count={counts.access_barrier}
        pct={pct.access_barrier}
        total={total}
        colour={SIGNAL_COLOURS.access_barrier}
      />
      <SignalRow
        label={SIGNAL_LABELS.none}
        count={counts.none}
        pct={pct.none}
        total={total}
        colour={SIGNAL_COLOURS.none}
      />

      {((data.confirmed_n ?? 0) > 0 ||
        (data.unrelated_filtered_events ?? 0) > 0) && (
        <Box
          sx={{
            mt: 2.5,
            p: 1.5,
            borderRadius: 1.5,
            bgcolor: "grey.50",
            border: "1px solid",
            borderColor: "divider",
          }}
        >
          <Typography
            variant="caption"
            sx={{
              display: "block",
              fontSize: "0.72rem",
              fontWeight: 700,
              textTransform: "uppercase",
              letterSpacing: 0.5,
              color: "text.secondary",
              mb: 0.5,
            }}
          >
            Pathway-relatedness
          </Typography>
          {(data.confirmed_n ?? 0) > 0 && (
            <Typography
              variant="caption"
              sx={{ display: "block", fontSize: "0.78rem", color: "text.primary", mb: 0.25 }}
            >
              <strong>{data.confirmed_n}</strong> of{" "}
              {data.recorded_n ?? 0} obstructed episodes had at least one
              encounter with explicit cancer-pathway markers (2WW, FTR,
              oncology, MDT, or the site-specific specialty -- e.g.
              dermatology for melanoma, urology for prostate). The
              remainder are generic "did not attend" lines with no
              clear cancer context.
            </Typography>
          )}
          {(data.unrelated_filtered_events ?? 0) > 0 && (
            <Typography
              variant="caption"
              sx={{ display: "block", fontSize: "0.78rem", color: "text.primary" }}
            >
              <strong>{data.unrelated_filtered_events}</strong> event
              {(data.unrelated_filtered_events ?? 0) === 1 ? " was" : "s were"}{" "}
              filtered out as clearly unrelated to the cancer pathway
              (midwife, district nurse, phlebotomy, urgent treatment
              centre, cardiac / pulmonary rehab, smoking cessation,
              etc.) and so are NOT in the headline.
            </Typography>
          )}
        </Box>
      )}

      <Typography
        variant="caption"
        sx={{
          display: "block",
          mt: 2,
          fontSize: "0.74rem",
          color: "text.secondary",
          fontStyle: "italic",
        }}
      >
        Detection window: 30 days before the referral, extended back
        to first presentation when there is a longer GP-to-referral
        gap (so PCI obstructions are captured), through to 14 days
        after the last milestone. Cohort-3 pathways with no referral
        fall back to 30 days before the earliest milestone. Each
        episode counts once -- per the strongest signal in the
        window, with bucket counts summing to the total. Rejection
        &gt; DNA &gt; cancellation &gt; access barrier &gt; none.
        Events whose encounter text comes from a clearly non-cancer
        service (midwife, district nurse, UTC, etc.) AND has no
        positive cancer-pathway marker are filtered out before
        counting -- see "Pathway-relatedness" above.
      </Typography>
    </Box>
  );
}

export default function CareObstructionsSection({
  result,
  loading,
  error,
  orgSelected = false,
  avoidableDelaysResult = null,
}: Props) {
  const orgId = useOrgId();
  const bm = result?.benchmark?.metrics;
  const avoidableBm = avoidableDelaysResult?.benchmark?.metrics;

  const { liveYears } = useAuditYearWindows<AuditCareObstruction>(
    fetchAuditCareObstructions,
    { orgId },
  );

  // The 2018 NCDA does not publish a "care obstruction" baseline -- it
  // is not a Section-8 metric.  The closest published comparator is
  // the GP-noted avoidable delay rate (NCDA Section 5: GPs reporting,
  // in hindsight, that diagnosis could have happened sooner), which
  // is exactly the signal these obstructions try to detect from the
  // record automatically.  Try the obstruction-specific key first in
  // case a future benchmark set adds one, then fall back to the
  // avoidable_delays metric so the baseline card always anchors to a
  // real published number.
  const baselinePct = useMemo(() => {
    const obstructionPct = resolveBenchmarkValue(
      bm,
      "care_obstruction.recorded_pct",
      orgSelected,
    );
    if (obstructionPct != null) return obstructionPct;
    return resolveBenchmarkValue(
      avoidableBm,
      "avoidable_delays.avoidable_delay_pct",
      orgSelected,
    );
  }, [bm, avoidableBm, orgSelected]);

  // Track whether the baseline came from the avoidable-delay fallback
  // so we can label the card honestly (otherwise an auditor might
  // assume NCDA published a care-obstruction figure).
  const baselineFromAvoidableDelay = useMemo(() => {
    if (baselinePct == null) return false;
    const obstructionPct = resolveBenchmarkValue(
      bm,
      "care_obstruction.recorded_pct",
      orgSelected,
    );
    return obstructionPct == null;
  }, [bm, orgSelected, baselinePct]);

  // Detail-dialog state.
  const [detailYear, setDetailYear] = useState<number | null>(null);
  const detailState = liveYears.find((y) => y.year === detailYear) ?? null;

  return (
    <SectionCard
      id="section-avoidable-delays"
      title="Avoidable Delays"
      description="Events detected in clinical records that may have delayed the cancer workup: rejected referrals, did-not-attends (DNAs), cancellations, and access barriers. The 2019 NCDA baseline is GP-confirmed -- GPs retrospectively reviewed their own cases and judged where the diagnosis could have happened sooner. Live year figures are potential avoidable delays detected automatically from the record and have not been reviewed by a clinician. Each card covers a Jan-Dec calendar year, counted by year of diagnosis or benign closure. Open the detail panel on a live year to see the type breakdown."
      availability="pipeline_pending"
      loading={loading}
      loadingSkeletonVariant="segmentedCards"
      error={error}
    >
      <Box sx={{ display: "flex", gap: 2, mb: 1.5, flexWrap: "wrap" }}>
        <EvolutionLegendSwatch colour={C_BENCH18} label="2018 NCDA baseline" dashed />
        <EvolutionLegendSwatch colour={ACCENT} label="Live year" />
      </Box>

      <Grid container spacing={2}>
        <Grid size={{ xs: 12, sm: 6, md: 3 }}>
          <EvolutionYearCard
            yearLabel={String(BASELINE_YEAR)}
            headlineValue={formatPct(baselinePct)}
            headlineSubLabel="GP-confirmed"
            isBaseline
            baselineFootnote={
              baselinePct == null
                ? "No published 2019 NCDA value loaded for this scope."
                : "2019 NCDA: GPs retrospectively reviewed their own cases and confirmed where, in hindsight, the diagnosis could have happened sooner. This is a clinician-confirmed figure, not an algorithmic estimate."
            }
          />
        </Grid>
        {liveYears.map((state) => {
          const hasBreakdown =
            state.data != null && state.data.signal_counts != null;
          return (
            <Grid key={state.year} size={{ xs: 12, sm: 6, md: 3 }}>
              <EvolutionYearCard
                yearLabel={String(state.year)}
                loading={state.loading}
                error={state.error}
                totalN={state.data?.total_episodes ?? 0}
                headlineValue={formatPct(state.data?.recorded_pct)}
                headlineSubLabel="potentially avoidable"
                accentColor={ACCENT}
                onZoom={
                  hasBreakdown ? () => setDetailYear(state.year) : undefined
                }
                zoomAriaLabel={`Open ${state.year} avoidable-delay type breakdown`}
              />
            </Grid>
          );
        })}
      </Grid>

      <EvolutionDetailDialog
        open={detailState != null}
        onClose={() => setDetailYear(null)}
        title={
          detailState
            ? `Avoidable delays -- ${detailState.year} type breakdown`
            : "Avoidable delays -- type breakdown"
        }
        subtitle="These are potential delays detected automatically from the record -- not GP-confirmed. Rejection = referral returned by the service; DNA = patient did not attend; Cancellation = appointment cancelled; Access barrier = unable to contact / declined / lost to follow-up."
        maxWidth="md"
      >
        {detailState?.data ? (
          <SignalBreakdownChart data={detailState.data} year={detailState.year} />
        ) : (
          <Alert severity="info" sx={{ fontSize: "0.85rem" }}>
            Loading breakdown...
          </Alert>
        )}
      </EvolutionDetailDialog>
    </SectionCard>
  );
}
