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
 * Safety Netting -- year-on-year evolution section.
 *
 * Renders four cards (2018 NCDA baseline + previous two calendar years
 * + current calendar year). Each card shows the % of episodes with a
 * safety-netting plan recorded, scoped to that Jan-Dec window via the
 * shared `outcome_date` audit anchor (year of diagnosis or benign
 * closure).
 *
 * Each live year card carries an "Open detail" zoom button that opens
 * a dialog with the four-bucket signal-strength breakdown for that
 * year (strong / medium / advice-only / none) -- this is the right
 * drill for "did we record safety netting?" rather than a per-cancer-
 * type contribution split, which is not the question the section
 * answers.
 */

import { useMemo, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Grid from "@mui/material/Grid";
import Typography from "@mui/material/Typography";

import {
  fetchAuditSafetyNetting,
  type AuditSafetyNetting,
  type AuditSectionResult,
} from "@/lib/analyticsApi";
import { useOrgId } from "@/context/OrgContext";
import { resolveBenchmarkValue } from "./BenchmarkLegend";

import SectionCard from "./SectionCard";
import EvolutionDetailDialog from "./EvolutionDetailDialog";
import EvolutionYearCard, { EvolutionLegendSwatch } from "./EvolutionYearCard";
import { useAuditYearWindows, BASELINE_YEAR } from "./_useAuditYearWindows";

const ACCENT = "#0d46d6";
const C_BENCH18 = "#92400E";

const MIN_EPISODES_FOR_ZERO = 5;

// Signal-strength row colours -- match the legend used in the dialog
// title strip and the audit summary tile tooltip.
const SIGNAL_COLOURS: Record<
  "strong" | "medium" | "advice_only" | "none",
  string
> = {
  strong: "#15803D",       // green: defensible "Yes" for NCDA Section 8
  medium: "#0d46d6",       // blue: structured PRISM template only
  advice_only: "#C2410C",  // orange: generic "return if X" -- not counted
  none: "#9CA3AF",         // grey: no safety-net evidence in window
};

const SIGNAL_LABELS: Record<
  "strong" | "medium" | "advice_only" | "none",
  string
> = {
  strong: "Strong -- free-text \"safety netted\" / \"safety net advice\" or Read code Y281b",
  medium: "Medium -- PRISM \"Advice if worsens, no better or concerns: Yes\" template field only",
  advice_only: "Advice-only -- generic \"return if X\" / red-flag wording (NOT counted)",
  none: "None -- no safety-net evidence in the encounter window",
};

interface Props {
  result: AuditSectionResult<AuditSafetyNetting> | null;
  loading: boolean;
  error?: string | null;
  orgSelected?: boolean;
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
          {count} <Box component="span" sx={{ color: "text.secondary", fontWeight: 500 }}>({pct.toFixed(1)}%)</Box>
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
  data: AuditSafetyNetting;
  year: number;
}) {
  const counts = data.signal_counts ?? {
    strong: 0,
    medium: 0,
    advice_only: 0,
    none: 0,
  };
  const pct = data.signal_pct ?? {
    strong: 0,
    medium: 0,
    advice_only: 0,
    none: 0,
  };
  const total = data.total_episodes ?? 0;
  const recordedN = (data.recorded_n ?? counts.strong + counts.medium) || 0;
  const recordedPct = data.recorded_pct ?? 0;
  const strongN = data.strong_n ?? counts.strong;
  const strongPct = data.strong_pct ?? pct.strong;

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
            Headline (NCDA-defensible)
          </Typography>
          <Typography
            sx={{ fontSize: "1.4rem", fontWeight: 700, color: SIGNAL_COLOURS.strong, lineHeight: 1.1, mt: 0.25 }}
          >
            {recordedPct.toFixed(1)}%
          </Typography>
          <Typography variant="caption" sx={{ color: "text.secondary", fontSize: "0.78rem" }}>
            {recordedN} of {total} confirmed cancers (strong + medium)
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
            Strict (free-text or Y281b only)
          </Typography>
          <Typography
            sx={{ fontSize: "1.4rem", fontWeight: 700, color: SIGNAL_COLOURS.strong, lineHeight: 1.1, mt: 0.25 }}
          >
            {strongPct.toFixed(1)}%
          </Typography>
          <Typography variant="caption" sx={{ color: "text.secondary", fontSize: "0.78rem" }}>
            {strongN} of {total} confirmed cancers (strong only)
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
        Signal-strength breakdown
      </Typography>
      <SignalRow
        label={SIGNAL_LABELS.strong}
        count={counts.strong}
        pct={pct.strong}
        total={total}
        colour={SIGNAL_COLOURS.strong}
        emphasis
      />
      <SignalRow
        label={SIGNAL_LABELS.medium}
        count={counts.medium}
        pct={pct.medium}
        total={total}
        colour={SIGNAL_COLOURS.medium}
        emphasis
      />
      <SignalRow
        label={SIGNAL_LABELS.advice_only}
        count={counts.advice_only}
        pct={pct.advice_only}
        total={total}
        colour={SIGNAL_COLOURS.advice_only}
      />
      <SignalRow
        label={SIGNAL_LABELS.none}
        count={counts.none}
        pct={pct.none}
        total={total}
        colour={SIGNAL_COLOURS.none}
      />

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
        Detection window: 30 days before the earliest milestone
        (referral / FTR / diagnosis) to 14 days after the last
        milestone. Headline percentage uses the canonical
        confirmed-cancer cohort as the denominator. Generic
        &ldquo;return if X&rdquo; phrasing is reported but NOT counted in
        the Section 8 figure -- it is too noisy on its own.
      </Typography>
    </Box>
  );
}

export default function SafetyNettingSection({
  result,
  loading,
  error,
  orgSelected = false,
}: Props) {
  const orgId = useOrgId();
  const bm = result?.benchmark?.metrics;

  const { liveYears } = useAuditYearWindows<AuditSafetyNetting>(
    fetchAuditSafetyNetting,
    { orgId },
  );

  const baselinePct = useMemo(
    () => resolveBenchmarkValue(bm, "safety_netting.recorded_pct", orgSelected),
    [bm, orgSelected],
  );

  // Across-window data-capture warning: stays visible if every live year
  // has episodes but no recorded safety netting.
  const dataNotCaptured = liveYears.every(
    (y) =>
      y.data != null &&
      y.data.recorded_n === 0 &&
      y.data.total_episodes >= MIN_EPISODES_FOR_ZERO,
  );

  // Detail-dialog state. We track WHICH year card opened the dialog
  // so the same detail pane can be re-used across all live years.
  const [detailYear, setDetailYear] = useState<number | null>(null);
  const detailState = liveYears.find((y) => y.year === detailYear) ?? null;

  return (
    <SectionCard
      id="section-safety-netting"
      title="Safety Netting"
      description="Whether a follow-up plan (safety netting) was written in the clinical record at any point during the patient's diagnostic journey. Safety netting means agreeing what to do if symptoms do not improve. Each card covers a Jan-Dec calendar year and counts episodes by year of diagnosis or benign closure."
      availability="pipeline_pending"
      loading={loading}
      loadingSkeletonVariant="cardGrid"
      error={error}
    >
      {dataNotCaptured && (
        <Alert severity="warning" sx={{ mb: 2, fontSize: "0.8rem" }}>
          Safety netting reads as 0% across every year shown. This is most
          likely because the system has not yet read this information from the
          clinical records. Do not use this figure in reports until the reading
          process is complete.
        </Alert>
      )}

      <Box sx={{ display: "flex", gap: 2, mb: 1.5, flexWrap: "wrap" }}>
        <EvolutionLegendSwatch colour={C_BENCH18} label="2018 NCDA baseline" dashed />
        <EvolutionLegendSwatch colour={ACCENT} label="Live year" />
      </Box>

      <Grid container spacing={2}>
        <Grid size={{ xs: 12, sm: 6, md: 3 }}>
          <EvolutionYearCard
            yearLabel={String(BASELINE_YEAR)}
            headlineValue={formatPct(baselinePct)}
            headlineSubLabel="recorded"
            isBaseline
            baselineFootnote={
              baselinePct == null
                ? "No published 2018 NCDA value for the selected scope."
                : undefined
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
                headlineSubLabel="recorded"
                accentColor={ACCENT}
                onZoom={
                  hasBreakdown ? () => setDetailYear(state.year) : undefined
                }
                zoomAriaLabel={`Open ${state.year} safety-netting signal-strength breakdown`}
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
            ? `Safety netting -- ${detailState.year} signal-strength breakdown`
            : "Safety netting -- signal-strength breakdown"
        }
        subtitle="Why this many cases? Strong = free-text or Y281b code; Medium = PRISM template only; Advice-only = generic 'return if X' (NOT counted in headline); None = no signal in the encounter window."
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
