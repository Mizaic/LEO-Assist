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
 * Reasons for Multiple Consultations -- year-on-year evolution scaffold.
 *
 * This section depends on structured GP-entered reasons (manual_entry).
 * No live data is available yet, so the year cards show "Awaiting
 * structured data entry" and the 2018 baseline card surfaces the
 * published reason mix (Complexity / Patient / GP / Diagnostic
 * process). When GP entry comes online, the live cards will re-use
 * `useAuditYearWindows` like every other audit section.
 */

import Box from "@mui/material/Box";
import Grid from "@mui/material/Grid";
import Typography from "@mui/material/Typography";

import {
  fetchAuditConsultations,
  type AuditConsultations,
  type AuditSectionResult,
  type BenchmarkMetricValues,
} from "@/lib/analyticsApi";
import { useOrgId } from "@/context/OrgContext";
import { resolveBenchmarkValue } from "./BenchmarkLegend";

import SectionCard from "./SectionCard";
import EvolutionYearCard, { EvolutionLegendSwatch } from "./EvolutionYearCard";
import { useAuditYearWindows, BASELINE_YEAR } from "./_useAuditYearWindows";

const ACCENT = "#7C3AED";
const C_BENCH18 = "#92400E";

interface Props {
  result?: AuditSectionResult<unknown> | null;
  loading?: boolean;
  error?: string | null;
  orgSelected?: boolean;
}

const REASONS: { key: string; label: string; metricKey: string }[] = [
  {
    key: "complexity",
    label: "Complexity of presentation",
    metricKey: "consultations.multiple_reason_complexity_pct",
  },
  { key: "patient_factors", label: "Patient factors", metricKey: "" },
  { key: "gp_factors", label: "GP factors", metricKey: "" },
  { key: "diagnostic_process", label: "Diagnostic process", metricKey: "" },
];

const REASON_DESCRIPTIONS: Record<string, string> = {
  complexity:
    "Vague/non-specific symptoms, co-morbidity blurring picture, symptoms suggested different initial diagnosis.",
  patient_factors: "Patient declined test or referral, patient did not attend.",
  gp_factors:
    "Poor communication, inadequate history taken, referred to wrong specialty, seen by multiple health professionals.",
  diagnostic_process:
    "Reassurance from negative investigation, multiple consultations to discuss test results.",
};

export default function MultipleConsultationsSection({
  result,
  loading,
  error,
  orgSelected = false,
}: Props) {
  const orgId = useOrgId();
  const bm = result?.benchmark?.metrics as
    | Record<string, BenchmarkMetricValues>
    | undefined;

  // We re-use the consultations endpoint to fetch per-year sample sizes
  // (so the live cards can show "Awaiting data" alongside the n that
  // *will* feed reasons once GPs start entering structured data).
  const { liveYears } = useAuditYearWindows<AuditConsultations>(
    fetchAuditConsultations,
    { orgId },
  );

  const baselineComplexity = bm
    ? resolveBenchmarkValue(
        bm,
        "consultations.multiple_reason_complexity_pct",
        orgSelected,
      )
    : null;

  return (
    <SectionCard
      id="section-multiple-consultations"
      title="Reasons for Multiple Consultations"
      description="For patients who had 3 or more consultations before referral, the reasons as assessed by the GP. Requires structured data entry. Each card covers a Jan-Dec calendar year and counts episodes by year of diagnosis or benign closure."
      availability="manual_entry"
      loading={loading}
      error={error}
    >
      <Box sx={{ display: "flex", gap: 2, mb: 1.5, flexWrap: "wrap" }}>
        <EvolutionLegendSwatch colour={C_BENCH18} label="2018 NCDA baseline" dashed />
        <EvolutionLegendSwatch colour={ACCENT} label="Awaiting structured entry" />
      </Box>

      <Grid container spacing={2}>
        <Grid size={{ xs: 12, sm: 6, md: 3 }}>
          <EvolutionYearCard
            yearLabel={String(BASELINE_YEAR)}
            headlineValue={
              baselineComplexity != null
                ? `${Math.round(baselineComplexity * 10) / 10}%`
                : null
            }
            headlineSubLabel="complexity"
            isBaseline
            baselineFootnote="Complexity is the only reason published in the 2018 NCDA. Full reason mix shown below."
          >
            <Box sx={{ mt: 1 }}>
              {REASONS.map((r) => (
                <Typography
                  key={r.key}
                  variant="caption"
                  color="text.secondary"
                  sx={{
                    display: "block",
                    fontSize: "0.7rem",
                    lineHeight: 1.4,
                  }}
                >
                  <strong>{r.label}:</strong> {REASON_DESCRIPTIONS[r.key]}
                </Typography>
              ))}
            </Box>
          </EvolutionYearCard>
        </Grid>
        {liveYears.map((state) => (
          <Grid key={state.year} size={{ xs: 12, sm: 6, md: 3 }}>
            <EvolutionYearCard
              yearLabel={String(state.year)}
              loading={state.loading}
              error={state.error}
              totalN={state.data?.total_episodes ?? 0}
              headlineValue={null}
              headlineSubLabel="reasons not captured"
              accentColor={ACCENT}
              caption={state.loading ? "Loading..." : "Awaiting data"}
            >
              <Typography
                variant="caption"
                color="text.secondary"
                sx={{
                  display: "block",
                  fontSize: "0.7rem",
                  fontStyle: "italic",
                  mt: 1,
                }}
              >
                Reasons require structured GP entry, which has not yet been
                turned on.
              </Typography>
            </EvolutionYearCard>
          </Grid>
        ))}
      </Grid>
    </SectionCard>
  );
}
