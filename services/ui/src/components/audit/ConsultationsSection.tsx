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
 * Consultations -- year-on-year evolution section.
 *
 * Headline metric per card is the % of patients with fewer than 3
 * pre-referral consultations (NCDA "early detection" KPI). The
 * secondary value is the median number of consultations. Each card
 * covers a Jan-Dec window anchored on the year of diagnosis or benign
 * closure.
 */

import { useMemo } from "react";
import Box from "@mui/material/Box";
import Grid from "@mui/material/Grid";

import {
  fetchAuditConsultations,
  type AuditConsultations,
  type AuditSectionResult,
} from "@/lib/analyticsApi";
import { useOrgId } from "@/context/OrgContext";
import { useAuditBenchmarkOverlay } from "@/context/AuditBenchmarkOverlayContext";
import { resolveBenchmarkValue } from "./BenchmarkLegend";

import SectionCard from "./SectionCard";
import CancerTypeBenchmarkGrid from "./CancerTypeBenchmarkGrid";
import EvolutionYearCard, { EvolutionLegendSwatch } from "./EvolutionYearCard";
import { useAuditYearWindows, BASELINE_YEAR } from "./_useAuditYearWindows";

const ACCENT = "#0F766E";
const C_BENCH18 = "#92400E";

interface Props {
  result: AuditSectionResult<AuditConsultations> | null;
  loading: boolean;
  error?: string | null;
  orgSelected?: boolean;
}

function formatPct(v: number | null | undefined): string | null {
  if (v == null) return null;
  return `${Math.round(v * 10) / 10}%`;
}

function formatMedian(
  v: number | null | undefined,
  iqrLow: number | null | undefined,
  iqrHigh: number | null | undefined,
): string | null {
  if (v == null) return null;
  const med = Number.isInteger(v) ? `${v}` : v.toFixed(1);
  if (iqrLow != null && iqrHigh != null) {
    return `${med} (IQR ${iqrLow}-${iqrHigh})`;
  }
  return med;
}

export default function ConsultationsSection({
  result,
  loading,
  error,
  orgSelected = false,
}: Props) {
  const orgId = useOrgId();
  const { showCancerAlliance, showAllPatients } = useAuditBenchmarkOverlay();
  const bm = result?.benchmark?.metrics;

  const { liveYears } = useAuditYearWindows<AuditConsultations>(
    fetchAuditConsultations,
    { orgId },
  );

  const baselinePct = useMemo(
    () => resolveBenchmarkValue(bm, "consultations.fewer_than_3_pct", orgSelected),
    [bm, orgSelected],
  );
  const baselineMedian = useMemo(
    () =>
      resolveBenchmarkValue(
        bm,
        "consultations.median_consultations",
        orgSelected,
      ),
    [bm, orgSelected],
  );

  return (
    <SectionCard
      id="section-consultations"
      title="Consultations"
      description="How many times patients saw a GP for possible cancer symptoms in the year before being referred for tests that led to their diagnosis. Each card covers a Jan-Dec calendar year and counts episodes by year of diagnosis or benign closure."
      availability="ready"
      loading={loading}
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
            headlineSubLabel="< 3 consultations"
            secondaryValue={
              baselineMedian != null
                ? `${baselineMedian} median`
                : null
            }
            isBaseline
            baselineFootnote={
              baselinePct == null
                ? "No published 2018 NCDA value for the selected scope."
                : undefined
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
              headlineValue={formatPct(state.data?.fewer_than_3_pct)}
              headlineSubLabel="< 3 consultations"
              secondaryValue={
                state.data
                  ? formatMedian(
                      state.data.median_consultations,
                      state.data.iqr_low,
                      state.data.iqr_high,
                    )
                  : null
              }
              accentColor={ACCENT}
            />
          </Grid>
        ))}
      </Grid>

      <Box sx={{ mt: 3 }}>
        <CancerTypeBenchmarkGrid
          bm={bm}
          section="consultations"
          metrics={[{ metricKey: "fewer_than_3_pct", label: "Fewer than 3" }]}
          orgSelected={orgSelected}
          heading="2018 Baseline by Cancer Type - Fewer than 3 Consultations (%)"
          showAlliance2018={orgSelected ? showCancerAlliance : undefined}
          showNational2018={orgSelected ? showAllPatients : undefined}
        />
      </Box>
    </SectionCard>
  );
}
