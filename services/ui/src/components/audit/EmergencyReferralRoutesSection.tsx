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
 * Emergency Referral Routes -- year-on-year evolution scaffold.
 *
 * This section depends on structured route-coding (manual_entry) and
 * has no live data yet. The 2018 NCDA baseline card shows the
 * published route-0 % plus an "Open detail" zoom dialog with the full
 * 8-route reference table. Live year cards show "Awaiting structured
 * entry" so the four-card layout matches every other audit section.
 */

import { useState } from "react";
import Box from "@mui/material/Box";
import Grid from "@mui/material/Grid";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
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
import EvolutionDetailDialog from "./EvolutionDetailDialog";
import { useAuditYearWindows, BASELINE_YEAR } from "./_useAuditYearWindows";

const ACCENT = "#B91C1C";
const C_BENCH18 = "#92400E";

interface Props {
  result?: AuditSectionResult<unknown> | null;
  loading?: boolean;
  error?: string | null;
  orgSelected?: boolean;
}

const ROUTES = [
  {
    key: "0",
    label:
      "Self-referred to A&E - no prior GP consultations",
    metricKey: "emergency_referral_routes.route_0_pct",
  },
  {
    key: "1",
    label: "GP/OOH referred to A&E - no prior GP consultations",
    metricKey: "",
  },
  {
    key: "2",
    label:
      "Self-referred to A&E - previously consulted GP, not awaiting test/referral",
    metricKey: "",
  },
  {
    key: "3",
    label:
      "GP/OOH referred to A&E - previously consulted GP, not awaiting test/referral",
    metricKey: "",
  },
  {
    key: "4",
    label: "Self-referred to A&E - awaiting GP-arranged test/referral",
    metricKey: "",
  },
  {
    key: "5",
    label: "GP/OOH referred to A&E - awaiting prior referral",
    metricKey: "",
  },
  { key: "6", label: "Other", metricKey: "" },
  { key: "7", label: "Not known / cannot verify", metricKey: "" },
];

export default function EmergencyReferralRoutesSection({
  result,
  loading,
  error,
  orgSelected = false,
}: Props) {
  const orgId = useOrgId();
  const bm = result?.benchmark?.metrics as
    | Record<string, BenchmarkMetricValues>
    | undefined;
  const [detailOpen, setDetailOpen] = useState(false);

  // Re-use the consultations endpoint for per-year sample sizes so the
  // live cards can show "n = ..." placeholders alongside the
  // "Awaiting data" message.
  const { liveYears } = useAuditYearWindows<AuditConsultations>(
    fetchAuditConsultations,
    { orgId },
  );

  const baselineRoute0 = bm
    ? resolveBenchmarkValue(
        bm,
        "emergency_referral_routes.route_0_pct",
        orgSelected,
      )
    : null;

  return (
    <SectionCard
      id="section-emergency-routes"
      title="Emergency Referral Routes"
      description="For patients referred by emergency route, the route subtype (self-referred to A&E, GP-referred to A&E, awaiting prior referral, etc.). Each card covers a Jan-Dec calendar year and counts episodes by year of diagnosis or benign closure. Requires structured data entry."
      availability="manual_entry"
      loading={loading}
      loadingSkeletonVariant="cardGrid"
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
              baselineRoute0 != null
                ? `${Math.round(baselineRoute0 * 10) / 10}%`
                : null
            }
            headlineSubLabel="route 0 (self-referred A&E)"
            isBaseline
            baselineFootnote="2018 NCDA only publishes route 0. Open detail for the full 8-route reference table."
            onZoom={() => setDetailOpen(true)}
            zoomAriaLabel="Open 2018 NCDA emergency-route reference table"
          />
        </Grid>
        {liveYears.map((state) => (
          <Grid key={state.year} size={{ xs: 12, sm: 6, md: 3 }}>
            <EvolutionYearCard
              yearLabel={String(state.year)}
              loading={state.loading}
              error={state.error}
              totalN={state.data?.total_episodes ?? 0}
              headlineValue={null}
              headlineSubLabel="route mix not captured"
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
                Route subtype requires structured GP/A&E entry, which has not
                yet been turned on.
              </Typography>
            </EvolutionYearCard>
          </Grid>
        ))}
      </Grid>

      <EvolutionDetailDialog
        open={detailOpen}
        onClose={() => setDetailOpen(false)}
        title="Emergency referral route reference - 2018 NCDA"
        subtitle="Only route 0 has published national / alliance values. The full eight-route definition is shown for clinical reference."
      >
        <Box sx={{ overflowX: "auto" }}>
          <Table size="small" aria-label="Emergency referral route key">
            <TableHead>
              <TableRow>
                <TableCell
                  sx={{ fontWeight: 700, fontSize: "0.78rem", width: 60 }}
                >
                  Route
                </TableCell>
                <TableCell sx={{ fontWeight: 700, fontSize: "0.78rem" }}>
                  Description
                </TableCell>
                <TableCell
                  align="center"
                  sx={{
                    fontWeight: 700,
                    fontSize: "0.78rem",
                    whiteSpace: "nowrap",
                  }}
                >
                  National %
                </TableCell>
                <TableCell
                  align="center"
                  sx={{
                    fontWeight: 700,
                    fontSize: "0.78rem",
                    whiteSpace: "nowrap",
                  }}
                >
                  Alliance %
                </TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {ROUTES.map((r) => {
                const natVal = r.metricKey
                  ? (bm?.[r.metricKey]?.national ?? null)
                  : null;
                const alVal = r.metricKey
                  ? (bm?.[r.metricKey]?.alliance ?? null)
                  : null;
                return (
                  <TableRow key={r.key} hover>
                    <TableCell sx={{ fontWeight: 700, fontSize: "0.8rem" }}>
                      {r.key}
                    </TableCell>
                    <TableCell sx={{ fontSize: "0.78rem" }}>{r.label}</TableCell>
                    <TableCell align="center" sx={{ fontSize: "0.8rem" }}>
                      {natVal != null ? `${natVal}%` : "--"}
                    </TableCell>
                    <TableCell align="center" sx={{ fontSize: "0.8rem" }}>
                      {alVal != null ? `${alVal}%` : "--"}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </Box>
      </EvolutionDetailDialog>
    </SectionCard>
  );
}
