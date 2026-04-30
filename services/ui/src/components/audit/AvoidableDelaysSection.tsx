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
 * Headline metric per card is `avoidable_delay_pct` (the % of cases
 * where the GP, in hindsight, felt diagnosis could have happened
 * sooner). The card body adds a compact stacked bar showing the phase
 * breakdown (before presentation / presentation-to-referral / after
 * referral) so the report can show "how much delay" and "where in the
 * pathway" on one card.
 */

import { useMemo } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Grid from "@mui/material/Grid";
import Typography from "@mui/material/Typography";

import {
  fetchAuditAvoidableDelays,
  type AuditAvoidableDelays,
  type AuditSectionResult,
} from "@/lib/analyticsApi";
import { useOrgId } from "@/context/OrgContext";
import { useAuditBenchmarkOverlay } from "@/context/AuditBenchmarkOverlayContext";
import { resolveBenchmarkValue } from "./BenchmarkLegend";

import SectionCard from "./SectionCard";
import CancerTypeBenchmarkGrid from "./CancerTypeBenchmarkGrid";
import EvolutionYearCard, { EvolutionLegendSwatch } from "./EvolutionYearCard";
import { useAuditYearWindows, BASELINE_YEAR } from "./_useAuditYearWindows";

const ACCENT = "#B45309";
const C_BENCH18 = "#92400E";
const C_PRE = "#FCA5A5";
const C_PRE_REF = "#F97316";
const C_POST = "#7C2D12";

const MIN_EPISODES_FOR_ZERO = 5;

interface Props {
  result: AuditSectionResult<AuditAvoidableDelays> | null;
  loading: boolean;
  error?: string | null;
  orgSelected?: boolean;
}

function formatPct(v: number | null | undefined): string | null {
  if (v == null) return null;
  return `${Math.round(v * 10) / 10}%`;
}

interface PhaseBarProps {
  before: number | null;
  presToRef: number | null;
  after: number | null;
}

/**
 * Phase split bar -- proportions are within the avoidable-delay
 * subgroup, not the full denominator (so they sum to 100% by design).
 */
function PhaseBar({ before, presToRef, after }: PhaseBarProps) {
  const b = Math.max(0, before ?? 0);
  const m = Math.max(0, presToRef ?? 0);
  const a = Math.max(0, after ?? 0);
  const total = b + m + a;
  if (total === 0) {
    return (
      <Typography
        variant="caption"
        color="text.secondary"
        sx={{ fontSize: "0.7rem", fontStyle: "italic" }}
      >
        No phase breakdown recorded.
      </Typography>
    );
  }
  return (
    <Box>
      <Box
        role="img"
        aria-label="Phase breakdown of avoidable delays"
        sx={{
          display: "flex",
          height: 10,
          width: "100%",
          borderRadius: 0.5,
          overflow: "hidden",
          bgcolor: "grey.200",
        }}
      >
        <Box sx={{ width: `${(b / total) * 100}%`, bgcolor: C_PRE }} />
        <Box sx={{ width: `${(m / total) * 100}%`, bgcolor: C_PRE_REF }} />
        <Box sx={{ width: `${(a / total) * 100}%`, bgcolor: C_POST }} />
      </Box>
      <Box
        sx={{
          display: "flex",
          gap: 1.5,
          mt: 0.5,
          flexWrap: "wrap",
          fontSize: "0.65rem",
          color: "text.secondary",
        }}
      >
        <span>
          <strong style={{ color: C_PRE }}>{Math.round(b)}%</strong> pre
        </span>
        <span>
          <strong style={{ color: C_PRE_REF }}>{Math.round(m)}%</strong>{" "}
          referral
        </span>
        <span>
          <strong style={{ color: C_POST }}>{Math.round(a)}%</strong> post
        </span>
      </Box>
    </Box>
  );
}

export default function AvoidableDelaysSection({
  result,
  loading,
  error,
  orgSelected = false,
}: Props) {
  const orgId = useOrgId();
  const { showCancerAlliance, showAllPatients } = useAuditBenchmarkOverlay();
  const bm = result?.benchmark?.metrics;

  const { liveYears } = useAuditYearWindows<AuditAvoidableDelays>(
    fetchAuditAvoidableDelays,
    { orgId },
  );

  const baselinePct = useMemo(
    () =>
      resolveBenchmarkValue(
        bm,
        "avoidable_delays.avoidable_delay_pct",
        orgSelected,
      ),
    [bm, orgSelected],
  );

  const dataNotCaptured = liveYears.every(
    (y) =>
      y.data != null &&
      y.data.avoidable_delay_n === 0 &&
      y.data.total_episodes >= MIN_EPISODES_FOR_ZERO,
  );

  return (
    <SectionCard
      id="section-avoidable-delays"
      title="Avoidable Delays"
      description="Cases where the GP (family doctor), looking back, felt that diagnosis could have happened sooner. Each card covers a Jan-Dec calendar year and counts episodes by year of diagnosis or benign closure. This section needs GPs to fill in a form -- it is not calculated automatically."
      availability="manual_entry"
      loading={loading}
      error={error}
    >
      {dataNotCaptured && (
        <Alert severity="warning" sx={{ mb: 2, fontSize: "0.8rem" }}>
          Avoidable delay reads as 0% across every year shown. This section
          needs GPs to fill in a form, which has not been done yet. The 0%
          figure does not mean there were no delays.
        </Alert>
      )}

      <Box sx={{ display: "flex", gap: 2, mb: 1.5, flexWrap: "wrap" }}>
        <EvolutionLegendSwatch colour={C_BENCH18} label="2018 NCDA baseline" dashed />
        <EvolutionLegendSwatch colour={ACCENT} label="Live year" />
        <EvolutionLegendSwatch colour={C_PRE} label="Pre-presentation" />
        <EvolutionLegendSwatch colour={C_PRE_REF} label="Pres -> referral" />
        <EvolutionLegendSwatch colour={C_POST} label="After referral" />
      </Box>

      <Grid container spacing={2}>
        <Grid size={{ xs: 12, sm: 6, md: 3 }}>
          <EvolutionYearCard
            yearLabel={String(BASELINE_YEAR)}
            headlineValue={formatPct(baselinePct)}
            headlineSubLabel="with delay"
            isBaseline
            baselineFootnote={
              baselinePct == null
                ? "No published 2018 NCDA value for the selected scope."
                : "2018 NCDA does not publish phase breakdown."
            }
          />
        </Grid>
        {liveYears.map((state) => (
          <Grid key={state.year} size={{ xs: 12, sm: 6, md: 3 }}>
            <EvolutionYearCard
              yearLabel={String(state.year)}
              loading={state.loading}
              error={state.error}
              totalN={state.data?.total_episodes ?? 0}
              headlineValue={formatPct(state.data?.avoidable_delay_pct)}
              headlineSubLabel="with delay"
              accentColor={ACCENT}
            >
              {state.data && (state.data.avoidable_delay_n ?? 0) > 0 && (
                <Box sx={{ mt: 1 }}>
                  <PhaseBar
                    before={state.data.delay_before_presentation_pct ?? null}
                    presToRef={state.data.delay_pres_to_referral_pct ?? null}
                    after={state.data.delay_after_referral_pct ?? null}
                  />
                </Box>
              )}
            </EvolutionYearCard>
          </Grid>
        ))}
      </Grid>

      <Box sx={{ mt: 3 }}>
        <CancerTypeBenchmarkGrid
          bm={bm}
          section="avoidable_delays"
          metrics={[{ metricKey: "avoidable_delay_pct", label: "Avoidable delay %" }]}
          orgSelected={orgSelected}
          heading="2018 Baseline by Cancer Type - Avoidable Delay (%)"
          showAlliance2018={orgSelected ? showCancerAlliance : undefined}
          showNational2018={orgSelected ? showAllPatients : undefined}
        />
      </Box>
    </SectionCard>
  );
}
