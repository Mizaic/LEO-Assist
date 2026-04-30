/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-2E8544FD
 *   DI: DI-C65FD45B
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-2E8544FD")
 */
"use client";

import Box from "@mui/material/Box";
import Grid from "@mui/material/Grid";
import Typography from "@mui/material/Typography";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Skeleton from "@mui/material/Skeleton";
import Divider from "@mui/material/Divider";
import Tooltip from "@mui/material/Tooltip";
import SectionCard from "./SectionCard";
import type { AuditSummary } from "@/lib/analyticsApi";
import { BENCHMARK_COLOURS } from "./BenchmarkLegend";
import { useAnalyticsDateFilter } from "@/context/AnalyticsDateFilterContext";
import { serialiseFilters, DEFAULT_FILTERS } from "@/lib/missionControlFilters";

interface Props {
  summary: AuditSummary | null;
  loading: boolean;
  error?: string | null;
  orgName?: string;
  auditPeriod?: string;
  totalCases?: number;
  /** When true, summary copy explains optional Cancer Alliance / England comparisons. */
  orgSelected?: boolean;
}

interface StatTileProps {
  label: string;
  value: string | number | null | undefined;
  sub?: string;
  color?: string;
  /** Optional tooltip body. When supplied, the tile shows an
   * underlined-dotted label hint on hover. */
  tooltip?: React.ReactNode;
}

function StatTile({ label, value, sub, color = BENCHMARK_COLOURS.practice, tooltip }: StatTileProps) {
  const labelNode = (
    <Typography
      variant="caption"
      sx={{
        color: "text.secondary",
        fontSize: "0.72rem",
        textTransform: "uppercase",
        letterSpacing: 0.5,
        fontWeight: 600,
        ...(tooltip
          ? {
              borderBottom: "1px dotted",
              borderBottomColor: "text.disabled",
              cursor: "help",
            }
          : {}),
      }}
    >
      {label}
    </Typography>
  );
  return (
    <Card variant="outlined" sx={{ height: "100%" }}>
      <CardContent sx={{ py: 1.5, px: 2, "&:last-child": { pb: 1.5 } }}>
        {tooltip ? (
          <Tooltip title={tooltip} arrow placement="top" enterDelay={300}>
            {labelNode}
          </Tooltip>
        ) : (
          labelNode
        )}
        {value == null ? (
          <Skeleton width={80} height={32} />
        ) : (
          <Typography variant="h5" sx={{ color, fontWeight: 700, lineHeight: 1.2, mt: 0.25 }}>
            {value}
          </Typography>
        )}
        {sub && (
          <Typography variant="caption" color="text.secondary" sx={{ fontSize: "0.72rem" }}>
            {sub}
          </Typography>
        )}
      </CardContent>
    </Card>
  );
}

const fmt = (v: number | null | undefined, decimals = 1) =>
  v == null ? null : Number(v.toFixed(decimals));

export default function AuditSummarySection({
  summary, loading, error, orgName, auditPeriod, totalCases, orgSelected = false,
}: Props) {
  const { appliedFrom, appliedTo } = useAnalyticsDateFilter();
  const viewCasesHref = `/care/patients?${serialiseFilters({
    ...DEFAULT_FILTERS,
    dateFrom: appliedFrom ?? "",
    dateTo: appliedTo ?? "",
    pathwayFilter: "all",
  })}`;

  const hasCohorts =
    summary != null &&
    (summary.cohort_1a_n != null || summary.cohort_1b_n != null || summary.cohort_3_n != null);

  return (
    <SectionCard
      id="section-summary"
      title="Summary of Results"
      description={`Key figures for ${orgName ?? "this organisation"}.${auditPeriod ? ` Audit period: ${auditPeriod}.` : ""}`}
      availability="ready"
      loading={loading}
      error={error}
      viewCasesHref={viewCasesHref}
    >
      {summary && (
        <>
          {totalCases != null && (
            <Box sx={{ mb: 2, p: 1.5, bgcolor: "grey.50", borderRadius: 1, border: "1px solid", borderColor: "divider" }}>
              <Typography variant="body2" sx={{ fontSize: "0.82rem" }}>
                <strong>{totalCases.toLocaleString("en-GB")}</strong> completed audit cases
                {orgName ? ` for ${orgName}` : ""}.
              </Typography>
            </Box>
          )}

          {/* ── Row 1: Pathway headline + key outcome metrics ── */}
          <Grid container spacing={1.5} sx={{ mb: hasCohorts ? 1 : 2 }}>
            <Grid size={{ xs: 6, sm: 4, md: 2 }}>
              <StatTile label="Cancer pathways" value={summary.total_episodes?.toLocaleString("en-GB")} sub="Total audited" />
            </Grid>
            <Grid size={{ xs: 6, sm: 4, md: 2 }}>
              <StatTile
                label="Confirmed cancer"
                value={summary.confirmed_cancers?.toLocaleString("en-GB")}
                sub={
                  summary.confirmed_cancers_via_2ww != null
                    ? `${summary.confirmed_cancers_via_2ww.toLocaleString("en-GB")} via 2WW (${fmt(summary.confirmed_cancers_via_2ww_pct) ?? "—"}%)`
                    : undefined
                }
                color="#15803D"
              />
            </Grid>
            <Grid size={{ xs: 6, sm: 4, md: 2 }}>
              <StatTile
                label="2WW route rate"
                value={fmt(summary.confirmed_cancers_via_2ww_pct) != null ? `${fmt(summary.confirmed_cancers_via_2ww_pct)}%` : "—"}
                sub="Confirmed cancers referred via fast-track (2WW)"
                color="#15803D"
              />
            </Grid>
            <Grid size={{ xs: 6, sm: 4, md: 2 }}>
              <StatTile
                label="Time to referral"
                value={fmt(summary.median_pci_days) != null ? `${fmt(summary.median_pci_days)} days` : "—"}
                sub="Median — first contact to referral (PCI)"
              />
            </Grid>
            <Grid size={{ xs: 6, sm: 4, md: 2 }}>
              <StatTile
                label="Time to diagnosis"
                value={fmt(summary.median_di_days) != null ? `${fmt(summary.median_di_days)} days` : "—"}
                sub="Median — first contact to diagnosis (DI)"
              />
            </Grid>
            <Grid size={{ xs: 6, sm: 4, md: 2 }}>
              <StatTile
                label="Safety netting"
                value={fmt(summary.safety_netting_pct) != null ? `${fmt(summary.safety_netting_pct)}%` : "—"}
                sub={
                  summary.safety_netting_recorded_n != null && summary.safety_netting_denominator
                    ? `${summary.safety_netting_recorded_n} of ${summary.safety_netting_denominator} confirmed cancers`
                    : "Confirmed cancers with a documented safety-net plan"
                }
                color="#C2410C"
                tooltip={
                  summary.safety_netting_signal_counts ? (
                    <Box sx={{ p: 0.5, fontSize: "0.78rem", lineHeight: 1.5 }}>
                      <Typography variant="caption" sx={{ display: "block", fontWeight: 700, mb: 0.5, color: "common.white" }}>
                        How safety netting is detected
                      </Typography>
                      <Typography variant="caption" sx={{ display: "block", color: "common.white" }}>
                        <strong>{summary.safety_netting_signal_counts.strong}</strong> strong — free-text "safety netted" / "safety-net advice" or Read code Y281b
                      </Typography>
                      <Typography variant="caption" sx={{ display: "block", color: "common.white" }}>
                        <strong>{summary.safety_netting_signal_counts.medium}</strong> medium — PRISM "Advice if worsens / no better / concerns: Yes"
                      </Typography>
                      <Typography variant="caption" sx={{ display: "block", color: "common.white" }}>
                        <strong>{summary.safety_netting_signal_counts.advice_only}</strong> advice-only — generic "return if X" / red-flag wording (NOT counted)
                      </Typography>
                      <Typography variant="caption" sx={{ display: "block", color: "common.white" }}>
                        <strong>{summary.safety_netting_signal_counts.none}</strong> none — no safety-net evidence in the encounter window
                      </Typography>
                      <Divider sx={{ my: 0.75, borderColor: "rgba(255,255,255,0.25)" }} />
                      <Typography variant="caption" sx={{ display: "block", color: "common.white" }}>
                        Headline = strong + medium ({summary.safety_netting_recorded_n ?? 0}/{summary.safety_netting_denominator ?? 0}, {fmt(summary.safety_netting_pct) ?? "—"}%).
                      </Typography>
                      {summary.safety_netting_strong_pct != null && (
                        <Typography variant="caption" sx={{ display: "block", color: "common.white" }}>
                          Strict (strong only): {summary.safety_netting_strong_n ?? 0}/{summary.safety_netting_denominator ?? 0}, {fmt(summary.safety_netting_strong_pct)}%.
                        </Typography>
                      )}
                      <Typography variant="caption" sx={{ display: "block", mt: 0.75, fontStyle: "italic", color: "rgba(255,255,255,0.85)" }}>
                        Window: 30 days before earliest milestone to 14 days after the last.
                      </Typography>
                    </Box>
                  ) : undefined
                }
              />
            </Grid>
          </Grid>

          {/* ── Row 2: NCDA cohort breakdown ── */}
          {hasCohorts && (
            <>
              <Typography variant="caption" sx={{ color: "text.secondary", fontSize: "0.72rem", textTransform: "uppercase", letterSpacing: 0.5, fontWeight: 600, display: "block", mb: 0.75 }}>
                NCDA Cohorts
              </Typography>
              <Grid container spacing={1.5} sx={{ mb: 2 }}>
                <Grid size={{ xs: 12, sm: 4 }}>
                  <Card variant="outlined" sx={{ height: "100%", borderLeft: "3px solid #15803D" }}>
                    <CardContent sx={{ py: 1.5, px: 2, "&:last-child": { pb: 1.5 } }}>
                      <Typography variant="caption" sx={{ color: "text.secondary", fontSize: "0.72rem", textTransform: "uppercase", letterSpacing: 0.5, fontWeight: 600 }}>
                        Cohort 1a — FTR → Cancer found
                      </Typography>
                      <Typography variant="h5" sx={{ color: "#15803D", fontWeight: 700, lineHeight: 1.2, mt: 0.25 }}>
                        {(summary.cohort_1a_n ?? 0).toLocaleString("en-GB")}
                      </Typography>
                      <Typography variant="caption" color="text.secondary" sx={{ fontSize: "0.72rem" }}>
                        Fast-track referral with confirmed cancer diagnosis
                      </Typography>
                    </CardContent>
                  </Card>
                </Grid>
                <Grid size={{ xs: 12, sm: 4 }}>
                  <Card variant="outlined" sx={{ height: "100%", borderLeft: "3px solid #0369A1" }}>
                    <CardContent sx={{ py: 1.5, px: 2, "&:last-child": { pb: 1.5 } }}>
                      <Typography variant="caption" sx={{ color: "text.secondary", fontSize: "0.72rem", textTransform: "uppercase", letterSpacing: 0.5, fontWeight: 600 }}>
                        Cohort 1b — FTR → No cancer
                      </Typography>
                      <Typography variant="h5" sx={{ color: "#0369A1", fontWeight: 700, lineHeight: 1.2, mt: 0.25 }}>
                        {(summary.cohort_1b_n ?? 0).toLocaleString("en-GB")}
                      </Typography>
                      <Typography variant="caption" color="text.secondary" sx={{ fontSize: "0.72rem" }}>
                        Fast-track referral — cancer excluded at outcome
                      </Typography>
                    </CardContent>
                  </Card>
                </Grid>
                <Grid size={{ xs: 12, sm: 4 }}>
                  <Card variant="outlined" sx={{ height: "100%", borderLeft: "3px solid #B45309" }}>
                    <CardContent sx={{ py: 1.5, px: 2, "&:last-child": { pb: 1.5 } }}>
                      <Typography variant="caption" sx={{ color: "text.secondary", fontSize: "0.72rem", textTransform: "uppercase", letterSpacing: 0.5, fontWeight: 600 }}>
                        Cohort 3 — Cancer found, no FTR
                      </Typography>
                      <Typography variant="h5" sx={{ color: "#B45309", fontWeight: 700, lineHeight: 1.2, mt: 0.25 }}>
                        {(summary.cohort_3_n ?? 0).toLocaleString("en-GB")}
                      </Typography>
                      <Typography variant="caption" color="text.secondary" sx={{ fontSize: "0.72rem" }}>
                        Cancer diagnosed without a fast-track referral — needs review
                      </Typography>
                    </CardContent>
                  </Card>
                </Grid>
              </Grid>
            </>
          )}

          <Divider sx={{ mb: 2 }} />

          <Typography variant="body2" color="text.secondary" sx={{ fontSize: "0.8rem" }}>
            Use the sections below to explore each area of the National Cancer Diagnosis Audit (NCDA).
            {orgSelected
              ? " By default, charts compare this practice to the benchmark period you choose above (such as your 2018 figures). Tick the boxes in the filter bar to add Cancer Alliance and all patients in England."
              : " Charts compare live figures to the benchmark period you choose above."}
          </Typography>
        </>
      )}
    </SectionCard>
  );
}
