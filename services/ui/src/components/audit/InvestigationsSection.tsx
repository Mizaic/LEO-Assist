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
 * Investigations -- year-on-year evolution of primary-care investigation rates
 * against the 2018 NCDA baseline.
 */

import { useMemo, useState } from "react";
import Box from "@mui/material/Box";
import Grid from "@mui/material/Grid";
import Typography from "@mui/material/Typography";
import {
  fetchAuditInvestigations,
  type AuditInvestigations,
  type AuditSectionResult,
} from "@/lib/analyticsApi";
import { useOrgId } from "@/context/OrgContext";
import { resolveBenchmarkValue } from "./BenchmarkLegend";

import SectionCard from "./SectionCard";
import EvolutionYearCard, { EvolutionLegendSwatch } from "./EvolutionYearCard";
import EvolutionDetailDialog from "./EvolutionDetailDialog";
import { useAuditYearWindows, BASELINE_YEAR } from "./_useAuditYearWindows";

const ACCENT = "#0369A1";
const C_BENCH18 = "#92400E";


/** Strip verbose SNOMED qualifiers that slip through the backend cleaner. */
function cleanLabel(label: string): string {
  return label
    .replace(/\s*\([^)]*(?:observable entity|finding|disorder|procedure)[^)]*\)\s*/gi, "")
    .replace(/\s+level\s*$/i, "")
    .trim();
}

interface Props {
  result: AuditSectionResult<AuditInvestigations> | null;
  loading: boolean;
  error?: string | null;
  orgSelected?: boolean;
}

function formatPct(v: number | null | undefined): string | null {
  if (v == null) return null;
  return `${Math.round(v * 10) / 10}%`;
}

export default function InvestigationsSection({
  result,
  loading,
  error,
  orgSelected = false,
}: Props) {
  const orgId = useOrgId();
  const bm = result?.benchmark?.metrics;

  const { liveYears } = useAuditYearWindows<AuditInvestigations>(
    fetchAuditInvestigations,
    { orgId },
  );

  const [zoomYear, setZoomYear] = useState<number | null>(null);

  const baselinePct = useMemo(
    () => resolveBenchmarkValue(bm, "investigations.at_least_one_pct", orgSelected),
    [bm, orgSelected],
  );

  const zoomState = useMemo(
    () => liveYears.find((s) => s.year === zoomYear),
    [liveYears, zoomYear],
  );

  const topProcedures = useMemo(
    () => zoomState?.data?.top_procedures ?? [],
    [zoomState],
  );


  return (
    <SectionCard
      id="section-investigations"
      title="Investigations"
      description="Tests ordered by the GP before referring the patient to a specialist. Each card covers a Jan-Dec calendar year."
      availability="pipeline_pending"
      loading={loading}
      loadingSkeletonVariant="cardGrid"
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
            headlineSubLabel=">= 1 investigation"
            isBaseline
            baselineFootnote={
              baselinePct == null
                ? "No published 2018 NCDA value for the selected scope."
                : "Click the expand icon on any live year card for the per-type breakdown."
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
              headlineValue={formatPct(state.data?.has_investigation_pct)}
              headlineSubLabel=">= 1 investigation"
              accentColor={ACCENT}
              onZoom={() => setZoomYear(state.year)}
              zoomAriaLabel={`Open per-type investigation breakdown for ${state.year}`}
            />
          </Grid>
        ))}
      </Grid>

      <EvolutionDetailDialog
        open={zoomYear != null}
        onClose={() => setZoomYear(null)}
        title={`Investigations - ${zoomYear ?? ""}`}
        subtitle={`Coded investigations recorded in cancer episode encounters for ${zoomYear}.`}
      >
        {/* Ranked list of SNOMED-coded procedures/tests – primary data source */}
        {topProcedures.length > 0 ? (
          <Box>
            <Typography variant="subtitle2" sx={{ mb: 0.5 }}>
              Coded investigations
            </Typography>
            <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 1.5 }}>
              SNOMED-coded procedures and tests from cancer episode encounters (% of episodes, ranked by frequency).
            </Typography>
            <Box
              component="ol"
              sx={{ m: 0, p: 0, listStyle: "none", display: "flex", flexDirection: "column", gap: 0.25 }}
            >
              {topProcedures.map((proc, i) => (
                <Box
                  key={proc.name}
                  component="li"
                  sx={{
                    display: "flex",
                    alignItems: "center",
                    gap: 1.5,
                    px: 1,
                    py: 0.75,
                    borderRadius: 1,
                    bgcolor: i % 2 === 0 ? "action.hover" : "transparent",
                  }}
                >
                  <Typography
                    variant="caption"
                    sx={{
                      minWidth: 20,
                      textAlign: "right",
                      color: "text.disabled",
                      fontVariantNumeric: "tabular-nums",
                    }}
                  >
                    {i + 1}
                  </Typography>
                  <Typography variant="body2" sx={{ flex: 1 }}>
                    {cleanLabel(proc.name)}
                  </Typography>
                  <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                    <Box
                      sx={{
                        height: 6,
                        width: Math.max(4, Math.round((proc.pct / (topProcedures[0]?.pct || 1)) * 80)),
                        bgcolor: ACCENT,
                        borderRadius: 1,
                        opacity: 0.75,
                      }}
                    />
                    <Typography
                      variant="caption"
                      sx={{
                        minWidth: 38,
                        textAlign: "right",
                        color: "text.secondary",
                        fontVariantNumeric: "tabular-nums",
                      }}
                    >
                      {proc.pct}%
                    </Typography>
                    <Typography
                      variant="caption"
                      sx={{
                        minWidth: 32,
                        textAlign: "right",
                        color: "text.disabled",
                        fontVariantNumeric: "tabular-nums",
                      }}
                    >
                      n={proc.n}
                    </Typography>
                  </Box>
                </Box>
              ))}
            </Box>
          </Box>
        ) : (
          <Box sx={{ p: 2, fontSize: "0.85rem", color: "text.secondary" }}>
            No coded investigations found for this year.
          </Box>
        )}

      </EvolutionDetailDialog>

    </SectionCard>
  );
}
