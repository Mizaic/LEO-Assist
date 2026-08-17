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
 * Consultations -- NCDA Section 7 "how many" view.
 *
 * Headline per card: median cancer-related consultations (from Haiku
 * enrichment, not raw encounter count).  Sub-value: % with 3+ contacts
 * (NCDA "multiple consultations" threshold) -- lower is better.
 *
 * Drill-down dialog: consultation-count bucket distribution (horizontal
 * bars), box-and-whisker median + IQR vs the 2018 baseline, and
 * contact-type means.
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

import {
  fetchAuditConsultations,
  type AuditConsultations,
  type AuditSectionResult,
} from "@/lib/analyticsApi";
import { useOrgId } from "@/context/OrgContext";
import { useAuditBenchmarkOverlay } from "@/context/AuditBenchmarkOverlayContext";
import { resolveBenchmarkValue } from "./BenchmarkLegend";
import {
  BUCKET_ORDER,
  BUCKET_LABELS,
  BUCKET_COLOURS,
  CONTACT_META,
  FACTOR_LABELS,
  type BucketKey,
} from "./_consultationConsts";

import SectionCard from "./SectionCard";
import EvolutionYearCard, { EvolutionLegendSwatch } from "./EvolutionYearCard";
import { useAuditYearWindows, BASELINE_YEAR } from "./_useAuditYearWindows";

const ACCENT = "#9338ff";
const C_BENCH18 = "#92400E";

// ---------------------------------------------------------------------------
// Tumour site × NCDA reason heatmap -- shown inside the per-year dialog
// ---------------------------------------------------------------------------

function TumourReasonHeatmap({
  factorsByCancerType,
  topFactors,
}: {
  factorsByCancerType: Record<string, Record<string, number>>;
  topFactors: Array<{ factor: string; n: number }>;
}) {
  const cancerTypes = Object.keys(factorsByCancerType);
  const topCodes = topFactors.slice(0, 7).map((f) => f.factor);

  if (cancerTypes.length === 0 || topCodes.length === 0) return null;

  const maxN = Math.max(
    ...cancerTypes.flatMap((ct) =>
      topCodes.map((code) => factorsByCancerType[ct]?.[code] ?? 0)
    ),
    1,
  );

  return (
    <Box sx={{ mt: 3, overflowX: "auto" }}>
      <Typography
        variant="subtitle2"
        sx={{
          fontSize: "0.78rem",
          fontWeight: 700,
          textTransform: "uppercase",
          letterSpacing: 0.5,
          color: "text.secondary",
          mb: 1.25,
        }}
      >
        Multiple consultations: tumour site &times; reason
      </Typography>
      <Box
        sx={{
          display: "grid",
          gridTemplateColumns: `110px repeat(${topCodes.length}, 1fr)`,
          gap: "3px",
          minWidth: 480,
        }}
      >
        {/* Header row */}
        <Box />
        {topCodes.map((code) => (
          <Box
            key={code}
            sx={{
              fontSize: "0.64rem",
              fontWeight: 600,
              color: "text.secondary",
              pb: 0.5,
              textAlign: "center",
              whiteSpace: "normal",
              wordBreak: "break-word",
              lineHeight: 1.3,
            }}
          >
            {FACTOR_LABELS[code] ?? code}
          </Box>
        ))}

        {/* Data rows */}
        {cancerTypes.map((ct) => (
          <Fragment key={ct}>
            <Typography
              sx={{
                fontSize: "0.75rem",
                fontWeight: 600,
                pr: 0.5,
                alignSelf: "center",
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              }}
            >
              {ct}
            </Typography>
            {topCodes.map((code) => {
              const n = factorsByCancerType[ct]?.[code] ?? 0;
              const intensity = n / maxN;
              return (
                <Box
                  key={`${ct}-${code}`}
                  title={`${ct} / ${FACTOR_LABELS[code] ?? code}: ${n} episode${n !== 1 ? "s" : ""}`}
                  sx={{
                    borderRadius: 0.75,
                    bgcolor:
                      n > 0
                        ? `rgba(15, 118, 110, ${0.1 + intensity * 0.8})`
                        : "grey.100",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    minHeight: 28,
                    cursor: n > 0 ? "default" : "default",
                  }}
                >
                  <Typography
                    sx={{
                      fontSize: "0.78rem",
                      fontWeight: n > 0 ? 700 : 400,
                      color: n > 0 ? (intensity > 0.6 ? "white" : "text.primary") : "text.disabled",
                    }}
                  >
                    {n > 0 ? n : ""}
                  </Typography>
                </Box>
              );
            })}
          </Fragment>
        ))}
      </Box>
      <Typography
        variant="caption"
        sx={{ display: "block", mt: 1, fontSize: "0.7rem", color: "text.secondary" }}
      >
        Darker = more episodes. Top 7 NCDA factors shown.
      </Typography>
    </Box>
  );
}

interface Props {
  result: AuditSectionResult<AuditConsultations> | null;
  loading: boolean;
  error?: string | null;
  orgSelected?: boolean;
}

function formatMedianDisplay(
  v: number | null | undefined,
  low: number | null | undefined,
  high: number | null | undefined,
): string | null {
  if (v == null) return null;
  const med = Number.isInteger(v) ? `${v}` : v.toFixed(1);
  if (low != null && high != null) {
    return `${med} (IQR ${low}-${high})`;
  }
  return med;
}

function formatPct(v: number | null | undefined): string | null {
  if (v == null) return null;
  return `${Math.round(v * 10) / 10}%`;
}

// ---------------------------------------------------------------------------
// Mini horizontal bar row (bucket histogram + contact-type breakdown)
// ---------------------------------------------------------------------------

function BucketRow({
  label,
  count,
  pct,
  total,
  colour,
  emphasis,
}: {
  label: string;
  count: number;
  pct: number;
  total: number;
  colour: string;
  emphasis?: boolean;
}) {
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
          sx={{ fontSize: "0.82rem", fontWeight: emphasis ? 700 : 500, color: "text.primary" }}
        >
          {label}
        </Typography>
        <Typography
          variant="body2"
          sx={{ fontSize: "0.85rem", fontWeight: 700, color: colour, whiteSpace: "nowrap" }}
        >
          {count}{" "}
          <Box component="span" sx={{ color: "text.secondary", fontWeight: 500 }}>
            ({pct.toFixed(1)}%)
          </Box>
        </Typography>
      </Box>
      <Box
        sx={{
          height: 6,
          borderRadius: 3,
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

// ---------------------------------------------------------------------------
// Box-and-whisker (inline SVG, no recharts)
// ---------------------------------------------------------------------------

function BoxWhisker({
  median,
  q1,
  q3,
  baselineMedian,
}: {
  median: number | null;
  q1: number | null;
  q3: number | null;
  baselineMedian: number | null;
}) {
  const allVals = [median, q1, q3, baselineMedian].filter((v): v is number => v != null);
  if (allVals.length === 0) return null;
  const max = Math.max(...allVals);
  const scale = (v: number) => (max > 0 ? (v / max) * 280 : 0);
  return (
    <Box sx={{ mt: 2, mb: 1 }}>
      <Typography
        variant="caption"
        sx={{
          display: "block",
          fontSize: "0.72rem",
          fontWeight: 700,
          textTransform: "uppercase",
          letterSpacing: 0.5,
          color: "text.secondary",
          mb: 1,
        }}
      >
        Median + IQR vs 2018 baseline
      </Typography>
      <svg width={340} height={56} style={{ overflow: "visible" }}>
        {/* Live year box + whisker */}
        {median != null && q1 != null && q3 != null && (
          <g>
            <rect
              x={scale(q1)}
              y={8}
              width={scale(q3) - scale(q1)}
              height={20}
              rx={2}
              fill={ACCENT}
              opacity={0.18}
              stroke={ACCENT}
              strokeWidth={1.5}
            />
            <line
              x1={scale(median)}
              y1={4}
              x2={scale(median)}
              y2={32}
              stroke={ACCENT}
              strokeWidth={2.5}
            />
            <text x={scale(median)} y={44} textAnchor="middle" fontSize={10} fill={ACCENT}>
              {Number.isInteger(median) ? median : median.toFixed(1)}
            </text>
            <text x={scale(q1)} y={44} textAnchor="middle" fontSize={9} fill="#64748b">
              Q1 {Number.isInteger(q1) ? q1 : q1.toFixed(1)}
            </text>
            <text x={scale(q3)} y={44} textAnchor="middle" fontSize={9} fill="#64748b">
              Q3 {Number.isInteger(q3) ? q3 : q3.toFixed(1)}
            </text>
          </g>
        )}
        {/* 2018 baseline tick */}
        {baselineMedian != null && (
          <g>
            <line
              x1={scale(baselineMedian)}
              y1={0}
              x2={scale(baselineMedian)}
              y2={32}
              stroke={C_BENCH18}
              strokeWidth={1.5}
              strokeDasharray="4 3"
            />
            <text x={scale(baselineMedian)} y={44} textAnchor="middle" fontSize={9} fill={C_BENCH18}>
              2018: {Number.isInteger(baselineMedian) ? baselineMedian : baselineMedian.toFixed(1)}
            </text>
          </g>
        )}
      </svg>
    </Box>
  );
}

// ---------------------------------------------------------------------------
// Breakdown dialog content
// ---------------------------------------------------------------------------

function ConsultationsBreakdownContent({
  data,
  baselineMedian,
  year,
}: {
  data: AuditConsultations;
  baselineMedian: number | null;
  year: number;
}) {
  const total = data.total_episodes ?? 0;
  const buckets = data.buckets ?? { "0": 0, "1": 0, "2": 0, "3-4": 0, "5-7": 0, "8+": 0 };
  const bucketsPct = data.buckets_pct ?? { "0": 0, "1": 0, "2": 0, "3-4": 0, "5-7": 0, "8+": 0 };
  const meanByType = data.mean_per_episode;

  if (total === 0) {
    return (
      <Alert severity="info" sx={{ fontSize: "0.85rem" }}>
        No confirmed-cancer episodes closed in {year} yet.
      </Alert>
    );
  }

  return (
    <Box>
      {/* Headline tiles */}
      <Box
        sx={{
          display: "grid",
          gridTemplateColumns: { xs: "1fr", sm: "1fr 1fr" },
          gap: 2,
          mb: 2.5,
        }}
      >
        {[
          {
            label: "3+ consultations (NCDA multiple)",
            value: `${(data.three_or_more_pct ?? 0).toFixed(1)}%`,
            sub: `${data.three_or_more_n ?? 0} of ${total} episodes`,
          },
          {
            label: "Median cancer-related contacts",
            value: data.median_consultations != null
              ? (Number.isInteger(data.median_consultations)
                  ? `${data.median_consultations}`
                  : data.median_consultations.toFixed(1))
              : "--",
            sub: data.iqr_low != null && data.iqr_high != null
              ? `IQR ${data.iqr_low}--${data.iqr_high}`
              : `${data.enriched_n ?? 0} episodes enriched`,
          },
        ].map((tile) => (
          <Box
            key={tile.label}
            sx={{ border: "1px solid", borderColor: "divider", borderRadius: 1.5, px: 2, py: 1.5 }}
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
              {tile.label}
            </Typography>
            <Typography sx={{ fontSize: "1.4rem", fontWeight: 700, color: ACCENT, lineHeight: 1.1, mt: 0.25 }}>
              {tile.value}
            </Typography>
            <Typography variant="caption" sx={{ color: "text.secondary", fontSize: "0.78rem" }}>
              {tile.sub}
            </Typography>
          </Box>
        ))}
      </Box>

      {/* Distribution histogram */}
      <Typography
        variant="subtitle2"
        sx={{ fontSize: "0.78rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: 0.5, color: "text.secondary", mb: 1 }}
      >
        Distribution -- consultations per episode
      </Typography>
      {BUCKET_ORDER.map((b) => (
        <BucketRow
          key={b}
          label={BUCKET_LABELS[b]}
          count={buckets[b as BucketKey] ?? 0}
          pct={bucketsPct[b as BucketKey] ?? 0}
          total={total}
          colour={BUCKET_COLOURS[b as BucketKey]}
          emphasis={b !== "0" && b !== "1"}
        />
      ))}

      {/* Box-and-whisker */}
      <BoxWhisker
        median={data.median_consultations ?? null}
        q1={data.iqr_low ?? null}
        q3={data.iqr_high ?? null}
        baselineMedian={baselineMedian}
      />

      {/* Contact-type means */}
      {meanByType && (
        <Box sx={{ mt: 3 }}>
          <Typography
            variant="subtitle2"
            sx={{ fontSize: "0.78rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: 0.5, color: "text.secondary", mb: 1 }}
          >
            Mean per-episode by contact type
          </Typography>
          <Box
            sx={{
              display: "grid",
              gridTemplateColumns: { xs: "1fr 1fr", md: "1fr 1fr 1fr 1fr" },
              gap: 1.5,
            }}
          >
            {CONTACT_META.map((c) => (
              <Box
                key={c.key}
                sx={{ px: 1.25, py: 1, border: "1px solid", borderColor: "divider", borderRadius: 1 }}
              >
                <Typography variant="caption" sx={{ display: "block", fontSize: "0.7rem", color: "text.secondary", fontWeight: 600 }}>
                  {c.label}
                </Typography>
                <Typography sx={{ fontSize: "1.05rem", fontWeight: 700, color: "text.primary" }}>
                  {(meanByType[c.key] ?? 0).toFixed(2)}
                </Typography>
              </Box>
            ))}
          </Box>
        </Box>
      )}

      {/* LLM telemetry footer */}
      <Box sx={{ mt: 3, p: 1.5, borderRadius: 1.5, bgcolor: "grey.50", border: "1px solid", borderColor: "divider" }}>
        <Typography variant="caption" sx={{ display: "block", fontSize: "0.72rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: 0.5, color: "text.secondary", mb: 0.5 }}>
          LLM enrichment
        </Typography>
        <Typography variant="caption" sx={{ display: "block", fontSize: "0.78rem", color: "text.primary" }}>
          Claude Haiku 4.5 classified <strong>{data.enriched_n ?? 0}</strong> of {total} episodes.
          {(data.unrelated_filtered_total ?? 0) > 0 && (
            <> <strong>{data.unrelated_filtered_total}</strong> encounter{(data.unrelated_filtered_total ?? 0) === 1 ? " was" : "s were"} filtered as unrelated.</>
          )}{" "}
          Cost: <strong>${(data.llm_cost_usd ?? 0).toFixed(4)}</strong> ({(data.llm_input_tokens ?? 0).toLocaleString()} in / {(data.llm_output_tokens ?? 0).toLocaleString()} out tokens).
        </Typography>
      </Box>

      {/* Tumour site × NCDA reason heatmap */}
      {data.factors_by_cancer_type && (data.top_factors?.length ?? 0) > 0 && (
        <TumourReasonHeatmap
          factorsByCancerType={data.factors_by_cancer_type}
          topFactors={data.top_factors ?? []}
        />
      )}

      <Typography variant="caption" sx={{ display: "block", mt: 2, fontSize: "0.74rem", color: "text.secondary", fontStyle: "italic" }}>
        Window: 365 days before the FTR.  Contacts must be F2F, telephone, nurse, email, specialist clinic, or home visit to count toward the NCDA tally.  Auto-filed results and phlebotomy are reported separately.
      </Typography>
    </Box>
  );
}

// ---------------------------------------------------------------------------
// Main section component
// ---------------------------------------------------------------------------

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

  // 2018 baseline: % with 3+ consultations (NCDA "multiple consultations").
  // Falls back to derived value (100 - fewer_than_3) if three_or_more not seeded.
  const baselineThreeOrMore = useMemo(
    () => resolveBenchmarkValue(bm, "consultations.three_or_more_pct", orgSelected),
    [bm, orgSelected],
  );
  const baselineFewerThan3 = useMemo(
    () => resolveBenchmarkValue(bm, "consultations.fewer_than_3_pct", orgSelected),
    [bm, orgSelected],
  );
  const baselineThreeOrMoreDerived =
    baselineThreeOrMore ??
    (baselineFewerThan3 != null ? Math.round((100 - baselineFewerThan3) * 10) / 10 : null);

  // 2018 median consultations for the box-and-whisker.
  const baselineMedian = useMemo(
    () => resolveBenchmarkValue(bm, "consultations.median_consultations", orgSelected),
    [bm, orgSelected],
  );

  const [detailYear, setDetailYear] = useState<number | null>(null);
  const detailState = liveYears.find((y) => y.year === detailYear) ?? null;

  return (
    <SectionCard
      id="section-consultations"
      title="Consultations"
      description="How many cancer-related GP consultations occurred in the year before referral, classified by Claude Haiku 4.5. Lower 'multiple consultations' rates are better -- they mean most patients were referred promptly. Each card covers a Jan-Dec calendar year, counted by year of diagnosis or benign closure."
      availability="ready"
      loading={loading}
      loadingSkeletonVariant="cardGrid"
      error={error}
    >
      <Box sx={{ display: "flex", gap: 2, mb: 1.5, flexWrap: "wrap" }}>
        <EvolutionLegendSwatch colour={C_BENCH18} label="2018 NCDA baseline" dashed />
        <EvolutionLegendSwatch colour={ACCENT} label="Live year (Haiku-classified)" />
      </Box>

      <Grid container spacing={2}>
        <Grid size={{ xs: 12, sm: 6, md: 3 }}>
          <EvolutionYearCard
            yearLabel={String(BASELINE_YEAR)}
            headlineValue={baselineThreeOrMoreDerived != null ? `${baselineThreeOrMoreDerived}%` : null}
            headlineSubLabel="3+ consultations"
            secondaryValue={
              baselineMedian != null ? `${baselineMedian} median` : null
            }
            isBaseline
            baselineFootnote={
              baselineThreeOrMoreDerived == null
                ? "No published 2018 NCDA value for the selected scope."
                : "2018 NCDA: GP-confirmed count of pre-referral consultations. Higher rate = more delayed referrals."
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
              headlineValue={formatPct(state.data?.three_or_more_pct)}
              headlineSubLabel="3+ consultations (NCDA multiple)"
              secondaryValue={
                state.data
                  ? formatMedianDisplay(
                      state.data.median_consultations,
                      state.data.iqr_low,
                      state.data.iqr_high,
                    )
                  : null
              }
              accentColor={ACCENT}
              onZoom={
                state.data?.buckets != null
                  ? () => setDetailYear(state.year)
                  : undefined
              }
              zoomAriaLabel={`Open ${state.year} consultation breakdown`}
            />
          </Grid>
        ))}
      </Grid>


      {/* Breakdown dialog */}
      <Dialog
        open={detailState != null}
        onClose={() => setDetailYear(null)}
        maxWidth="md"
        fullWidth
        aria-labelledby="consult-breakdown-title"
      >
        <DialogTitle id="consult-breakdown-title">
          Consultations -- {detailState?.year} breakdown
        </DialogTitle>
        <DialogContent dividers>
          {detailState?.data ? (
            <ConsultationsBreakdownContent
              data={detailState.data}
              baselineMedian={baselineMedian ?? null}
              year={detailState.year}
            />
          ) : (
            <Alert severity="info">Loading breakdown...</Alert>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDetailYear(null)}>Close</Button>
        </DialogActions>
      </Dialog>
    </SectionCard>
  );
}
