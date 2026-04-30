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
 * Investigations -- year-on-year evolution section.
 *
 * Headline metric per card is `has_investigation_pct` (% of patients
 * with at least one primary-care investigation before referral). The
 * "Open detail" zoom dialog renders the full per-type breakdown for
 * the chosen year, mirroring the pre-migration full chart but scoped
 * to that calendar window.
 */

import { useMemo, useState } from "react";
import Box from "@mui/material/Box";
import Grid from "@mui/material/Grid";

import {
  fetchAuditInvestigations,
  type AuditInvestigations,
  type AuditSectionResult,
} from "@/lib/analyticsApi";
import { useOrgId } from "@/context/OrgContext";
import { useAuditBenchmarkOverlay } from "@/context/AuditBenchmarkOverlayContext";
import { resolveBenchmarkValue } from "./BenchmarkLegend";

import SectionCard from "./SectionCard";
import CancerTypeBenchmarkGrid from "./CancerTypeBenchmarkGrid";
import EvolutionYearCard, { EvolutionLegendSwatch } from "./EvolutionYearCard";
import EvolutionDetailDialog from "./EvolutionDetailDialog";
import ComparisonBarChart, { type ComparisonDataRow } from "./ComparisonBarChart";
import { useAuditYearWindows, BASELINE_YEAR } from "./_useAuditYearWindows";

const ACCENT = "#0369A1";
const C_BENCH18 = "#92400E";

const INV_DISPLAY: Record<string, string> = {
  blood_test: "Blood test",
  imaging: "Imaging",
  urinalysis: "Urinary test",
  urinary_test: "Urinary test",
  biopsy: "Biopsy",
  endoscopy: "Endoscopy",
  symptomatic_fit: "Symptomatic FIT",
  other_investigation: "Other",
  investigation: "Other",
};

const INV_BM_KEY: Record<string, string> = {
  blood_test: "investigations.blood_test_pct",
  imaging: "investigations.imaging_pct",
  urinalysis: "investigations.urinary_test_pct",
  urinary_test: "investigations.urinary_test_pct",
  endoscopy: "investigations.endoscopy_pct",
  symptomatic_fit: "investigations.symptomatic_fit_pct",
  other_investigation: "investigations.other_investigation_pct",
  investigation: "investigations.other_investigation_pct",
};

const BM_TYPES = [
  { type: "blood_test", bmKey: "blood_test_pct" },
  { type: "imaging", bmKey: "imaging_pct" },
  { type: "urinary_test", bmKey: "urinary_test_pct" },
  { type: "endoscopy", bmKey: "endoscopy_pct" },
  { type: "symptomatic_fit", bmKey: "symptomatic_fit_pct" },
  { type: "other_investigation", bmKey: "other_investigation_pct" },
];

const INV_BM_METRICS = BM_TYPES.map(({ type, bmKey }) => ({
  metricKey: bmKey,
  label: INV_DISPLAY[type] ?? type,
}));

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
  const { showCancerAlliance, showAllPatients } = useAuditBenchmarkOverlay();
  const bm = result?.benchmark?.metrics;

  const { liveYears } = useAuditYearWindows<AuditInvestigations>(
    fetchAuditInvestigations,
    { orgId },
  );

  const [zoomYear, setZoomYear] = useState<number | null>(null);

  const baselinePct = useMemo(
    () =>
      resolveBenchmarkValue(bm, "investigations.at_least_one_pct", orgSelected),
    [bm, orgSelected],
  );

  const detailRows: ComparisonDataRow[] = useMemo(() => {
    if (zoomYear == null) return [];
    const state = liveYears.find((s) => s.year === zoomYear);
    const data = state?.data;
    if (!data) return [];
    return BM_TYPES.map(({ type, bmKey }) => {
      const live = (data.types ?? []).find((t) => t.type === type);
      return {
        category: INV_DISPLAY[type] ?? type,
        practice: live?.pct ?? 0,
        national: resolveBenchmarkValue(
          bm,
          `investigations.${bmKey}`,
          orgSelected,
        ),
      } satisfies ComparisonDataRow;
    });
  }, [zoomYear, liveYears, bm, orgSelected]);

  const visibleKeys = ["practice", "national"] as const;

  return (
    <SectionCard
      id="section-investigations"
      title="Investigations"
      description="Tests ordered by the GP (family doctor) before referring the patient to a specialist. Each card covers a Jan-Dec calendar year and counts episodes by year of diagnosis or benign closure."
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
                : "Per-type breakdown shown below in the cancer-type grid."
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

      <Box sx={{ mt: 3 }}>
        <CancerTypeBenchmarkGrid
          bm={bm}
          section="investigations"
          metrics={INV_BM_METRICS}
          orgSelected={orgSelected}
          heading="2018 Investigation Types by Cancer Type"
          showAlliance2018={orgSelected ? showCancerAlliance : undefined}
          showNational2018={orgSelected ? showAllPatients : undefined}
        />
      </Box>

      <EvolutionDetailDialog
        open={zoomYear != null}
        onClose={() => setZoomYear(null)}
        title={`Investigations by type - ${zoomYear ?? ""}`}
        subtitle="% of patients receiving each investigation type, compared to the 2018 NCDA baseline."
      >
        {detailRows.length > 0 ? (
          <ComparisonBarChart
            data={detailRows}
            unit="percent"
            height={Math.max(280, detailRows.length * 36 + 80)}
            visibleKeys={visibleKeys}
            orgSelected={orgSelected}
            ariaLabel={`Investigations by type for ${zoomYear}`}
          />
        ) : (
          <Box sx={{ p: 2, fontSize: "0.85rem", color: "text.secondary" }}>
            No investigation data captured for this year.
          </Box>
        )}
      </EvolutionDetailDialog>
    </SectionCard>
  );
}
