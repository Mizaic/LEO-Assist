/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-7F2A9C41
 *   DI: DI-C65FD45B
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-7F2A9C41")
 */
"use client";

/**
 * Multiple Consultations -- NCDA Section 7 "why" view.
 *
 * Headline per card: top NCDA factor code label + %.
 * Sub-value: n episodes contributing to that factor.
 *
 * Drill-down dialog:
 *   (a) Grouped factor bar chart (by NCDA pro-forma category)
 *   (b) Per-cancer-type x factor count heatmap
 *   (c) Evidence drawer -- collapsible accordion per episode (quotes placeholder)
 */

import { Fragment, useMemo, useState } from "react";
import Box from "@mui/material/Box";
import Grid from "@mui/material/Grid";
import Dialog from "@mui/material/Dialog";
import DialogTitle from "@mui/material/DialogTitle";
import DialogContent from "@mui/material/DialogContent";
import DialogActions from "@mui/material/DialogActions";
import Button from "@mui/material/Button";
import Typography from "@mui/material/Typography";
import Alert from "@mui/material/Alert";
import Accordion from "@mui/material/Accordion";
import AccordionSummary from "@mui/material/AccordionSummary";
import AccordionDetails from "@mui/material/AccordionDetails";
import Chip from "@mui/material/Chip";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";

import {
  fetchAuditConsultations,
  type AuditConsultations,
  type AuditSectionResult,
  type AuditConsultationEpisodeEvidence,
} from "@/lib/analyticsApi";
import { useOrgId } from "@/context/OrgContext";
import {
  FACTOR_LABELS,
  FACTOR_TO_CATEGORY,
  NCDA_CATEGORIES,
} from "./_consultationConsts";

import SectionCard from "./SectionCard";
import EvolutionYearCard from "./EvolutionYearCard";
import { useAuditYearWindows } from "./_useAuditYearWindows";

const ACCENT = "#7C3AED";
const CATEGORY_COLOURS: Record<string, string> = {
  "Complexity of presentation": "#0369A1",
  "Patient factors":            "#B45309",
  "GP factors":                 "#15803D",
  "Diagnostic process":         "#7C3AED",
  "Other":                      "#6B7280",
};

// ---------------------------------------------------------------------------
// Factor bar chart -- one horizontal bar per factor, grouped by category
// ---------------------------------------------------------------------------

function FactorBarSection({
  title,
  colour,
  factors,
}: {
  title: string;
  colour: string;
  factors: Array<{ factor: string; n: number }>;
}) {
  if (factors.length === 0) return null;
  const maxN = Math.max(...factors.map((f) => f.n), 1);
  return (
    <Box sx={{ mb: 2 }}>
      <Typography
        sx={{ fontSize: "0.75rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: 0.5, color: colour, mb: 0.75 }}
      >
        {title}
      </Typography>
      {factors.map((f) => {
        const pct = (f.n / maxN) * 100;
        return (
          <Box key={f.factor} sx={{ mb: 1 }}>
            <Box sx={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", mb: 0.4 }}>
              <Typography sx={{ fontSize: "0.8rem", color: "text.primary" }}>
                {FACTOR_LABELS[f.factor] ?? f.factor}
              </Typography>
              <Typography sx={{ fontSize: "0.85rem", fontWeight: 700, color: colour, ml: 1, whiteSpace: "nowrap" }}>
                {f.n}
              </Typography>
            </Box>
            <Box sx={{ height: 5, borderRadius: 2, bgcolor: "grey.100", overflow: "hidden" }}>
              <Box sx={{ height: "100%", width: `${pct}%`, bgcolor: colour, transition: "width 200ms ease-out" }} />
            </Box>
          </Box>
        );
      })}
    </Box>
  );
}

// ---------------------------------------------------------------------------
// Cancer-type x factor heatmap (compact table)
// ---------------------------------------------------------------------------

function FactorHeatmap({
  factorsByCancerType,
  topFactorCodes,
}: {
  factorsByCancerType: Record<string, Record<string, number>>;
  topFactorCodes: string[];
}) {
  const cancerTypes = Object.keys(factorsByCancerType);
  if (cancerTypes.length === 0 || topFactorCodes.length === 0) return null;
  const maxN = Math.max(
    ...cancerTypes.flatMap((ct) =>
      topFactorCodes.map((code) => factorsByCancerType[ct]?.[code] ?? 0)
    ),
    1,
  );
  return (
    <Box sx={{ mt: 3, overflowX: "auto" }}>
      <Typography
        variant="subtitle2"
        sx={{ fontSize: "0.78rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: 0.5, color: "text.secondary", mb: 1 }}
      >
        Factor frequency by cancer type (top 6 factors)
      </Typography>
      <Box
        sx={{
          display: "grid",
          gridTemplateColumns: `120px repeat(${Math.min(topFactorCodes.length, 6)}, 1fr)`,
          gap: 0.5,
          minWidth: "520px",
        }}
      >
        <Box sx={{ fontSize: "0.65rem", fontWeight: 700, color: "text.secondary", pb: 0.5 }} />
        {topFactorCodes.slice(0, 6).map((code) => (
          <Box
            key={code}
            sx={{
              fontSize: "0.68rem",
              fontWeight: 600,
              color: "text.secondary",
              pb: 0.5,
              textAlign: "center",
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
              title: FACTOR_LABELS[code] ?? code,
            }}
          >
            {(FACTOR_LABELS[code] ?? code).substring(0, 20)}
          </Box>
        ))}
        {cancerTypes.map((ct) => (
          <Fragment key={ct}>
            <Typography
              sx={{ fontSize: "0.75rem", fontWeight: 600, pr: 1, alignSelf: "center" }}
            >
              {ct}
            </Typography>
            {topFactorCodes.slice(0, 6).map((code) => {
              const n = factorsByCancerType[ct]?.[code] ?? 0;
              const intensity = n / maxN;
              return (
                <Box
                  key={`${ct}-${code}`}
                  title={`${FACTOR_LABELS[code] ?? code} / ${ct}: ${n}`}
                  sx={{
                    borderRadius: 0.75,
                    bgcolor: n > 0 ? `rgba(124, 58, 237, ${0.12 + intensity * 0.7})` : "grey.100",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    minHeight: 28,
                  }}
                >
                  <Typography sx={{ fontSize: "0.8rem", fontWeight: n > 0 ? 700 : 400, color: n > 0 ? "text.primary" : "text.disabled" }}>
                    {n > 0 ? n : ""}
                  </Typography>
                </Box>
              );
            })}
          </Fragment>
        ))}
      </Box>
    </Box>
  );
}

// ---------------------------------------------------------------------------
// Evidence accordion per episode
// ---------------------------------------------------------------------------

function EvidenceDrawer({ episodes }: { episodes: AuditConsultationEpisodeEvidence[] }) {
  const withFactors = episodes.filter((e) => e.factors.length > 0);
  if (withFactors.length === 0) {
    return (
      <Typography variant="body2" sx={{ mt: 2, color: "text.secondary", fontSize: "0.82rem" }}>
        No episodes with NCDA factors in the selected window.
      </Typography>
    );
  }
  return (
    <Box sx={{ mt: 2 }}>
      <Typography
        variant="subtitle2"
        sx={{ fontSize: "0.78rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: 0.5, color: "text.secondary", mb: 1 }}
      >
        Episode evidence ({withFactors.length} episode{withFactors.length === 1 ? "" : "s"})
      </Typography>
      {withFactors.map((ep) => (
        <Accordion key={ep.episode_id} disableGutters elevation={0} sx={{ border: "1px solid", borderColor: "divider", mb: 0.5 }}>
          <AccordionSummary expandIcon={<ExpandMoreIcon />} sx={{ py: 0.5 }}>
            <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, flexWrap: "wrap" }}>
              <Typography sx={{ fontWeight: 600, fontSize: "0.82rem" }}>
                {ep.cancer_type}
              </Typography>
              <Chip label={`${ep.n ?? "?"} consultations`} size="small" sx={{ height: 18, fontSize: "0.72rem" }} />
              {ep.factors.map((code) => (
                <Chip
                  key={code}
                  label={FACTOR_LABELS[code] ?? code}
                  size="small"
                  sx={{ height: 18, fontSize: "0.7rem", bgcolor: `${CATEGORY_COLOURS[FACTOR_TO_CATEGORY[code] ?? "Other"]}22`, border: "none" }}
                />
              ))}
            </Box>
          </AccordionSummary>
          <AccordionDetails sx={{ pb: 1.5 }}>
            {ep.evidence_quotes != null ? (
              <Typography variant="body2" sx={{ fontSize: "0.82rem" }}>
                {ep.evidence_quotes}
              </Typography>
            ) : (
              <Alert severity="info" sx={{ fontSize: "0.8rem", py: 0.5 }}>
                Evidence quotes will be populated in a future enrichment pass.
              </Alert>
            )}
          </AccordionDetails>
        </Accordion>
      ))}
    </Box>
  );
}

// ---------------------------------------------------------------------------
// Dialog content
// ---------------------------------------------------------------------------

function MultipleConsultationsDialogContent({
  data,
  year,
}: {
  data: AuditConsultations;
  year: number;
}) {
  const topFactors = data.top_factors ?? [];
  const factorsByCancerType = data.factors_by_cancer_type ?? {};
  const episodes = data.episode_evidence ?? [];
  const topFactorCodes = topFactors.map((f) => f.factor);

  const grouped = useMemo(() => {
    const out: Record<string, typeof topFactors> = {};
    for (const cat of NCDA_CATEGORIES) out[cat] = [];
    for (const f of topFactors) {
      const cat = FACTOR_TO_CATEGORY[f.factor] ?? "Other";
      out[cat].push(f);
    }
    return out;
  }, [topFactors]);

  const hasAnyFactor = topFactors.length > 0;

  if (!hasAnyFactor) {
    return (
      <Alert severity="info" sx={{ fontSize: "0.85rem" }}>
        No multiple-consultation NCDA factors recorded for confirmed-cancer episodes closed in {year}.
      </Alert>
    );
  }

  return (
    <Box>
      {/* Bar chart -- grouped by NCDA category */}
      <Typography
        variant="subtitle2"
        sx={{ fontSize: "0.78rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: 0.5, color: "text.secondary", mb: 1.5 }}
      >
        Factors by NCDA category
      </Typography>
      {NCDA_CATEGORIES.map((cat) => (
        <FactorBarSection
          key={cat}
          title={cat}
          colour={CATEGORY_COLOURS[cat]}
          factors={grouped[cat]}
        />
      ))}

      {/* Heatmap */}
      <FactorHeatmap
        factorsByCancerType={factorsByCancerType}
        topFactorCodes={topFactorCodes}
      />

      {/* Evidence accordion */}
      <EvidenceDrawer episodes={episodes} />

      {/* Footer */}
      <Box sx={{ mt: 3, p: 1.5, borderRadius: 1.5, bgcolor: "grey.50", border: "1px solid", borderColor: "divider" }}>
        <Typography variant="caption" sx={{ display: "block", fontSize: "0.78rem", color: "text.secondary" }}>
          Factors proposed by Claude Haiku 4.5 for {data.enriched_n ?? 0} of {data.total_episodes ?? 0} enriched episodes.
          Cost: <strong>${(data.llm_cost_usd ?? 0).toFixed(4)}</strong>.
          NCDA categories match the published 2019 GP audit pro forma.
        </Typography>
      </Box>
    </Box>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

interface Props {
  result: AuditSectionResult<AuditConsultations> | null;
  loading: boolean;
  error?: string | null;
  orgSelected?: boolean;
}

export default function MultipleConsultationsSection({
  loading,
  error,
  orgSelected = false,
}: Props) {
  const orgId = useOrgId();

  const { liveYears } = useAuditYearWindows<AuditConsultations>(
    fetchAuditConsultations,
    { orgId },
  );

  const [detailYear, setDetailYear] = useState<number | null>(null);
  const detailState = liveYears.find((y) => y.year === detailYear) ?? null;

  return (
    <SectionCard
      id="section-multiple-consultations"
      title="Reasons for Multiple Consultations"
      description="NCDA Section 7: for episodes with 3 or more cancer-related consultations before referral, what factors explain the multiple contacts? Classified by Claude Haiku 4.5 using the NCDA 2019 GP audit pro forma. Each card covers a Jan-Dec calendar year."
      availability="ready"
      loading={loading}
      loadingSkeletonVariant="cardGrid"
      error={error}
    >
      <Grid container spacing={2}>
        {liveYears.map((state) => {
          const topFactor = state.data?.top_factors?.[0];
          const topLabel = topFactor ? (FACTOR_LABELS[topFactor.factor] ?? topFactor.factor) : null;
          const topN = topFactor?.n ?? null;
          const multiN = state.data?.three_or_more_n ?? null;
          const topPct =
            topN != null && multiN != null && multiN > 0
              ? `${((topN / multiN) * 100).toFixed(0)}% of multiple-consultation episodes`
              : null;
          return (
            <Grid key={state.year} size={{ xs: 12, sm: 6, md: 3 }}>
              <EvolutionYearCard
                yearLabel={String(state.year)}
                loading={state.loading}
                error={state.error}
                totalN={state.data?.three_or_more_n ?? 0}
                headlineValue={topLabel ?? "--"}
                headlineSubLabel="Top NCDA factor"
                secondaryValue={topPct}
                accentColor={ACCENT}
                onZoom={
                  state.data?.top_factors != null
                    ? () => setDetailYear(state.year)
                    : undefined
                }
                zoomAriaLabel={`Open ${state.year} multiple consultations factors breakdown`}
              />
            </Grid>
          );
        })}
      </Grid>

      {/* Breakdown dialog */}
      <Dialog
        open={detailState != null}
        onClose={() => setDetailYear(null)}
        maxWidth="md"
        fullWidth
        aria-labelledby="multi-consult-dialog-title"
      >
        <DialogTitle id="multi-consult-dialog-title">
          Multiple Consultations -- {detailState?.year} factor breakdown
        </DialogTitle>
        <DialogContent dividers>
          {detailState?.data ? (
            <MultipleConsultationsDialogContent
              data={detailState.data}
              year={detailState.year}
            />
          ) : (
            <Alert severity="info">Loading...</Alert>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDetailYear(null)}>Close</Button>
        </DialogActions>
      </Dialog>
    </SectionCard>
  );
}
