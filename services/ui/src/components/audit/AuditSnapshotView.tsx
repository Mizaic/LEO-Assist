"use client";

/**
 * View 2 — Insight Snapshot
 *
 * Three zones following the user's job-to-be-done:
 *
 *   Zone 1 — AWARENESS: Where do I stand relative to 2018?
 *     → Hero scorecard cards with directional glow
 *     → Collapsible NCDA summary detail (quiet, subordinate)
 *
 *   Zone 2 — DIAGNOSIS: What's changed, and what's driving it?
 *     → Deviation table ranked by largest drift from baseline
 *
 *   Zone 3 — ACTION: Where should I focus effort?
 *     → Top 3 worsened metrics with narrative + drill-down
 *
 * Information hierarchy: summary → deviation → drill-down.
 */

import { useState } from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Grid from "@mui/material/Grid";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Table from "@mui/material/Table";
import TableHead from "@mui/material/TableHead";
import TableBody from "@mui/material/TableBody";
import TableRow from "@mui/material/TableRow";
import TableCell from "@mui/material/TableCell";
import Button from "@mui/material/Button";
import Skeleton from "@mui/material/Skeleton";
import Alert from "@mui/material/Alert";
import Chip from "@mui/material/Chip";
import Paper from "@mui/material/Paper";
import Collapse from "@mui/material/Collapse";
import OpenInNewIcon from "@mui/icons-material/OpenInNew";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import VisibilityOutlinedIcon from "@mui/icons-material/VisibilityOutlined";
import TroubleshootOutlinedIcon from "@mui/icons-material/TroubleshootOutlined";
import TrackChangesOutlinedIcon from "@mui/icons-material/TrackChangesOutlined";
import WarningAmberIcon from "@mui/icons-material/WarningAmber";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
import Tooltip from "@mui/material/Tooltip";
import DirectionChip, { computeDirection, type Direction } from "./DirectionChip";
import { resolveBenchmarkValue } from "./BenchmarkLegend";

import type {
  AuditSummary,
  AuditSectionResult,
  AuditCancerStageRow,
  AuditCancerTypeRow,
  AuditConsultations,
  AuditDemographics,
  AuditInvestigations,
  AuditPlaceRow,
  AuditReferralRow,
  AuditIntervals,
  AuditSafetyNetting,
  AuditAvoidableDelays,
} from "@/lib/analyticsApi";

// ─── Types & helpers ──────────────────────────────────────────────────────────

/**
 * Minimum episodes before we trust a 0% metric as a genuine clinical signal.
 * Below this, zero values are likely a data capture gap, not a clinical outcome.
 */
const MIN_EPISODES_FOR_ZERO = 5;

/**
 * Absolute pp drift (percentage points) above which a metric gets a data-quality
 * caveat alongside the clinical flag in Zone 3.
 */
const LARGE_DRIFT_THRESHOLD = 30;

/**
 * A metric can be in one of three quality states:
 *   ok          — live value present and plausible; include in all zones.
 *   insufficient — no data at all (null); show "No data" card, exclude from Z2/Z3.
 *   suspect      — live === 0 on a metric where 0 is clinically implausible given
 *                  the episode count; show a "Check data capture" warning card,
 *                  include in Z2 with a flag, exclude from Z3 action priorities.
 */
type MetricQuality = "ok" | "insufficient" | "suspect";

interface MetricDef {
  id: string;
  label: string;
  unit: string;
  sectionId: string;
  higherIsBetter: boolean;
  threshold?: number;
  live: number | null;
  baseline: number | null;
}

type BmRecord = Record<string, { practice?: number | null; alliance?: number | null; national?: number | null }>;

function mergeBenchmarkMetrics(...results: Array<{ benchmark?: { metrics?: BmRecord | null } | null } | null>): BmRecord | null {
  const merged: BmRecord = {};
  let any = false;
  for (const r of results) {
    const m = r?.benchmark?.metrics;
    if (m) { Object.assign(merged, m); any = true; }
  }
  return any ? merged : null;
}

function fmtPct(v: number | null | undefined): string {
  return v == null ? "—" : `${Math.round(v * 10) / 10}%`;
}

function fmtN(v: number | null | undefined): string {
  return v == null ? "—" : String(Math.round(v));
}

/**
 * Classify a metric's data quality. "suspect" only triggers for higherIsBetter
 * metrics where live === 0 — because 0% safety-netting or 0% investigations with
 * real episodes almost always means "not recorded", not "genuinely zero".
 */
function getMetricQuality(m: MetricDef, totalEpisodes: number | null): MetricQuality {
  if (m.live === null) return "insufficient";
  if (
    m.live === 0 &&
    m.higherIsBetter &&
    totalEpisodes != null &&
    totalEpisodes >= MIN_EPISODES_FOR_ZERO
  ) return "suspect";
  return "ok";
}

const GLOW: Record<Direction | "suspect" | "insufficient", { border: string; borderStyle?: string; shadow: string; bg: string }> = {
  better:       { border: "#16a34a", shadow: "0 0 12px 0 rgba(22,163,74,0.20)",  bg: "rgba(22,163,74,0.04)"  },
  worse:        { border: "#dc2626", shadow: "0 0 12px 0 rgba(220,38,38,0.20)",  bg: "rgba(220,38,38,0.04)"  },
  unchanged:    { border: "#d97706", shadow: "0 0 10px 0 rgba(217,119,6,0.14)",  bg: "rgba(217,119,6,0.03)"  },
  unknown:      { border: "#94a3b8", shadow: "0 0 0 1px rgba(148,163,184,0.5)",  bg: "transparent"           },
  suspect:      { border: "#d97706", borderStyle: "dashed", shadow: "none",      bg: "rgba(217,119,6,0.03)"  },
  insufficient: { border: "#cbd5e1", borderStyle: "dashed", shadow: "none",      bg: "rgba(241,245,249,0.6)" },
};

// ─── Props ────────────────────────────────────────────────────────────────────

interface Props {
  orgSelected: boolean;
  loading: boolean;
  summary:             AuditSummary | null;
  cancerType:          AuditSectionResult<AuditCancerTypeRow[]>   | null;
  cancerStage:         AuditSectionResult<AuditCancerStageRow[]>  | null;
  demographics:        AuditSectionResult<AuditDemographics>      | null;
  placeOfPresentation: AuditSectionResult<AuditPlaceRow[]>        | null;
  consultations:       AuditSectionResult<AuditConsultations>     | null;
  investigations:      AuditSectionResult<AuditInvestigations>    | null;
  referrals:           AuditSectionResult<AuditReferralRow[]>     | null;
  intervals:           AuditSectionResult<AuditIntervals>         | null;
  safetyNetting:       AuditSectionResult<AuditSafetyNetting>     | null;
  avoidableDelays:     AuditSectionResult<AuditAvoidableDelays>   | null;
  onViewInReport: (sectionId: string) => void;
}

// ─── Derive 8 key metrics ────────────────────────────────────────────────────

function deriveMetrics(
  cancerStage: Props["cancerStage"],
  consultations: Props["consultations"],
  referrals: Props["referrals"],
  intervals: Props["intervals"],
  safetyNetting: Props["safetyNetting"],
  avoidableDelays: Props["avoidableDelays"],
  bm: BmRecord | null,
  orgSelected: boolean,
): MetricDef[] {
  const earlyRow        = cancerStage?.scopes.practice?.find((r) => r.stage_group === "early");
  const consultPractice = consultations?.scopes.practice;
  const refPractice     = referrals?.scopes.practice ?? [];
  const twwRow          = refPractice.find((r) => { const rr = r.referral_route?.toLowerCase() ?? ""; return rr === "tww" || rr.includes("two_week") || rr.includes("two-week"); });
  const emgRow          = refPractice.find((r) => r.referral_route?.toLowerCase() === "emergency");
  const intervalPractice = intervals?.scopes.practice;
  const snPractice       = safetyNetting?.scopes.practice;
  const delayPractice    = avoidableDelays?.scopes.practice;

  return [
    { id: "early_stage",        label: "Early stage diagnosis",       unit: "%",     sectionId: "section-cancer-stage",     higherIsBetter: true,  live: earlyRow?.pct ?? null,                     baseline: resolveBenchmarkValue(bm, "cancer_stage.early_stage_pct", orgSelected) },
    { id: "fewer_than_3",       label: "Fewer than 3 consultations",  unit: "%",     sectionId: "section-consultations",    higherIsBetter: true,  live: consultPractice?.fewer_than_3_pct ?? null, baseline: resolveBenchmarkValue(bm, "consultations.fewer_than_3_pct", orgSelected) },
    { id: "tww_referral",       label: "TWW referral rate",           unit: "%",     sectionId: "section-referrals",        higherIsBetter: true,  live: twwRow?.pct ?? null,                       baseline: resolveBenchmarkValue(bm, "referrals.tww_pct", orgSelected) },
    { id: "emergency_referral", label: "Emergency referral rate",     unit: "%",     sectionId: "section-referrals",        higherIsBetter: false, live: emgRow?.pct ?? null,                       baseline: resolveBenchmarkValue(bm, "referrals.emergency_pct", orgSelected) },
    { id: "pci_days",           label: "Median primary care interval",unit: " days", sectionId: "section-pci",              higherIsBetter: false, threshold: 1, live: intervalPractice?.pci.median ?? null, baseline: resolveBenchmarkValue(bm, "primary_care_interval.median_pci_days", orgSelected) },
    { id: "di_days",            label: "Median diagnostic interval",  unit: " days", sectionId: "section-di",               higherIsBetter: false, threshold: 3, live: intervalPractice?.di.median ?? null,  baseline: resolveBenchmarkValue(bm, "diagnostic_interval.median_di_days", orgSelected) },
    { id: "safety_netting",     label: "Safety netting recorded",     unit: "%",     sectionId: "section-safety-netting",   higherIsBetter: true,  live: snPractice?.recorded_pct ?? null,          baseline: resolveBenchmarkValue(bm, "safety_netting.recorded_pct", orgSelected) },
    { id: "avoidable_delay",    label: "GP-assessed avoidable delay", unit: "%",     sectionId: "section-avoidable-delays", higherIsBetter: false, live: delayPractice?.avoidable_delay_pct ?? null, baseline: resolveBenchmarkValue(bm, "avoidable_delays.avoidable_delay_pct", orgSelected) },
  ];
}

// ─── Zone header ─────────────────────────────────────────────────────────────

function ZoneHeader({ zone, title, subtitle, icon }: { zone: number; title: string; subtitle: string; icon: React.ReactNode }) {
  return (
    <Box sx={{ display: "flex", gap: 2, alignItems: "flex-start", mb: 2.5, mt: zone > 1 ? 5 : 0 }}>
      <Box sx={{ width: 40, height: 40, borderRadius: "50%", bgcolor: "primary.main", color: "white", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0, mt: 0.25 }}>
        {icon}
      </Box>
      <Box>
        <Typography variant="overline" sx={{ fontSize: "0.68rem", letterSpacing: 1.5, color: "text.secondary", lineHeight: 1 }}>
          Zone {zone}
        </Typography>
        <Typography variant="h6" component="h2" sx={{ fontWeight: 700, lineHeight: 1.2 }}>
          {title}
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mt: 0.25, fontSize: "0.82rem" }}>
          {subtitle}
        </Typography>
      </Box>
    </Box>
  );
}

// ─── Hero scorecard card with directional glow ───────────────────────────────

function ScorecardCard({
  metric,
  quality,
  onViewInReport,
}: {
  metric: MetricDef;
  quality: MetricQuality;
  onViewInReport: (id: string) => void;
}) {
  const direction = quality === "ok"
    ? computeDirection(metric.live, metric.baseline, metric.higherIsBetter, metric.threshold)
    : "unknown";
  const glowKey = quality === "ok" ? direction : quality;
  const glow = GLOW[glowKey];
  const fmtVal = (v: number | null) => (v == null ? "—" : `${Math.round(v)}${metric.unit}`);
  const diff = quality === "ok" && metric.live != null && metric.baseline != null
    ? metric.live - metric.baseline
    : null;

  return (
    <Card
      variant="outlined"
      sx={{
        height: "100%",
        cursor: "pointer",
        borderColor: glow.border,
        borderStyle: glow.borderStyle ?? "solid",
        boxShadow: glow.shadow,
        bgcolor: glow.bg,
        transition: "box-shadow 0.2s, transform 0.15s",
        "&:hover": { transform: "translateY(-2px)" },
      }}
      onClick={() => onViewInReport(metric.sectionId)}
      role="button"
      aria-label={`${metric.label}: ${quality === "insufficient" ? "no data" : fmtVal(metric.live)}`}
    >
      <CardContent sx={{ pb: "12px !important" }}>
        <Typography variant="caption" sx={{ color: "text.secondary", fontWeight: 600, fontSize: "0.7rem", textTransform: "uppercase", letterSpacing: 0.4 }}>
          {metric.label}
        </Typography>

        {quality === "insufficient" ? (
          <>
            <Box sx={{ display: "flex", alignItems: "center", gap: 0.75, mt: 1 }}>
              <InfoOutlinedIcon sx={{ fontSize: "1rem", color: "text.disabled" }} />
              <Typography variant="body2" sx={{ color: "text.disabled", fontStyle: "italic", fontSize: "0.82rem" }}>
                No data recorded
              </Typography>
            </Box>
            <Typography variant="caption" sx={{ color: "text.disabled", display: "block", mt: 0.75, fontSize: "0.7rem" }}>
              Excluded from trend analysis
            </Typography>
          </>
        ) : quality === "suspect" ? (
          <>
            <Box sx={{ display: "flex", alignItems: "baseline", gap: 1, mt: 0.5 }}>
              <Typography variant="h4" sx={{ fontWeight: 800, lineHeight: 1, color: "warning.main" }}>
                {fmtVal(metric.live)}
              </Typography>
            </Box>
            <Box sx={{ display: "flex", alignItems: "center", gap: 0.5, mt: 1 }}>
              <WarningAmberIcon sx={{ fontSize: "0.9rem", color: "warning.main" }} />
              <Typography variant="caption" sx={{ color: "warning.main", fontWeight: 600, fontSize: "0.7rem" }}>
                Check data capture
              </Typography>
            </Box>
            <Typography variant="caption" sx={{ color: "text.disabled", display: "block", mt: 0.5, fontSize: "0.7rem" }}>
              2018 baseline: {fmtVal(metric.baseline)} — excluded from priorities
            </Typography>
          </>
        ) : (
          <>
            <Box sx={{ display: "flex", alignItems: "baseline", gap: 1, mt: 0.5 }}>
              <Typography variant="h4" sx={{ fontWeight: 800, lineHeight: 1, color: direction === "worse" ? "error.main" : direction === "better" ? "success.main" : "text.primary" }}>
                {fmtVal(metric.live)}
              </Typography>
            </Box>
            <Box sx={{ display: "flex", gap: 1, alignItems: "center", mt: 1 }}>
              <DirectionChip direction={direction} size="small" />
              {diff != null && (
                <Chip
                  label={`${diff > 0 ? "+" : ""}${Math.round(diff * 10) / 10}${metric.unit}`}
                  size="small"
                  color={direction === "worse" ? "error" : direction === "better" ? "success" : "default"}
                  variant="outlined"
                  sx={{ fontSize: "0.66rem", height: 20, fontWeight: 600 }}
                />
              )}
            </Box>
            <Typography variant="caption" sx={{ color: "text.disabled", display: "block", mt: 0.75, fontSize: "0.7rem" }}>
              2018 baseline: {fmtVal(metric.baseline)}
            </Typography>
          </>
        )}
      </CardContent>
    </Card>
  );
}

// ─── Compact summary card (readable tables, quiet visual weight) ─────────────

function SummaryCard({
  title,
  rows,
  practiceLabel,
  englandLabel,
  onView,
}: {
  title: string;
  rows: Array<{ label: string; practice: string; england: string }>;
  practiceLabel: string;
  englandLabel: string;
  onView?: () => void;
}) {
  return (
    <Paper
      variant="outlined"
      sx={{
        mb: 2,
        borderRadius: 2,
        overflow: "hidden",
        borderColor: "grey.200",
        bgcolor: "background.paper",
      }}
    >
      <Box
        sx={{
          px: 1.5, py: 0.75,
          borderBottom: "2px solid",
          borderColor: "primary.light",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
        }}
      >
        <Typography variant="subtitle2" sx={{ fontWeight: 700, fontSize: "0.82rem", color: "text.primary" }}>
          {title}
        </Typography>
        {onView && (
          <Button
            size="small"
            endIcon={<OpenInNewIcon sx={{ fontSize: "0.72rem !important" }} />}
            onClick={onView}
            sx={{ textTransform: "none", fontSize: "0.72rem", color: "primary.main", py: 0, minHeight: 0, minWidth: 0 }}
          >
            Full section
          </Button>
        )}
      </Box>
      <Table size="small">
        <TableHead>
          <TableRow>
            <TableCell sx={{ fontWeight: 600, fontSize: "0.75rem", color: "text.secondary", py: 0.5, width: "50%" }} />
            <TableCell align="right" sx={{ fontWeight: 700, fontSize: "0.75rem", color: "primary.main", py: 0.5 }}>
              {practiceLabel}
            </TableCell>
            <TableCell align="right" sx={{ fontWeight: 700, fontSize: "0.75rem", color: "text.secondary", py: 0.5 }}>
              {englandLabel}
            </TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {rows.map((row) => (
            <TableRow key={row.label} sx={{ "&:last-child td": { borderBottom: 0 } }}>
              <TableCell sx={{ fontSize: "0.82rem", py: 0.75, color: "text.primary" }}>{row.label}</TableCell>
              <TableCell align="right" sx={{ fontSize: "0.82rem", py: 0.75, fontWeight: 600 }}>{row.practice}</TableCell>
              <TableCell align="right" sx={{ fontSize: "0.82rem", py: 0.75, color: "text.secondary" }}>{row.england}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </Paper>
  );
}

// ─── Deviation Table ─────────────────────────────────────────────────────────

function DeviationTable({
  metrics,
  qualities,
  onViewInReport,
}: {
  metrics: MetricDef[];
  qualities: Map<string, MetricQuality>;
  onViewInReport: (id: string) => void;
}) {
  // Exclude metrics with no data; include suspect ones with a flag
  const sorted = [...metrics]
    .filter((m) => {
      const q = qualities.get(m.id);
      return q !== "insufficient" && m.live != null && m.baseline != null;
    })
    .sort((a, b) => Math.abs(b.live! - b.baseline!) - Math.abs(a.live! - a.baseline!));

  if (sorted.length === 0) {
    return (
      <Alert severity="info" sx={{ mt: 2 }}>
        No live data available to compare against the 2018 baseline. Ensure audit data is loaded and a benchmark set is selected.
      </Alert>
    );
  }

  const fmtVal = (m: MetricDef, v: number | null) => v == null ? "—" : `${Math.round(v)}${m.unit}`;

  return (
    <Paper variant="outlined" sx={{ borderRadius: 2, overflow: "hidden" }}>
      <Table size="small" aria-label="Deviation from 2018 baseline, ranked by largest difference">
        <TableHead>
          <TableRow sx={{ bgcolor: "grey.50" }}>
            <TableCell sx={{ fontWeight: 700, fontSize: "0.76rem" }}>Metric</TableCell>
            <TableCell align="right" sx={{ fontWeight: 700, fontSize: "0.76rem" }}>Today</TableCell>
            <TableCell align="right" sx={{ fontWeight: 700, fontSize: "0.76rem" }}>2018</TableCell>
            <TableCell align="right" sx={{ fontWeight: 700, fontSize: "0.76rem" }}>Drift</TableCell>
            <TableCell align="center" sx={{ fontWeight: 700, fontSize: "0.76rem" }}>Direction</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {sorted.map((m) => {
            const quality = qualities.get(m.id) ?? "ok";
            const direction = computeDirection(m.live, m.baseline, m.higherIsBetter, m.threshold);
            const diff = m.live! - m.baseline!;
            const absDiff = Math.abs(diff);
            const rowGlow = quality === "suspect" ? GLOW.suspect : GLOW[direction];
            const isLargeDrift = m.unit === "%" && absDiff >= LARGE_DRIFT_THRESHOLD;
            return (
              <TableRow
                key={m.id}
                hover
                sx={{
                  cursor: "pointer",
                  "&:last-child td": { borderBottom: 0 },
                  borderLeft: `3px solid ${rowGlow.border}`,
                  bgcolor: quality === "suspect" ? "rgba(217,119,6,0.03)" : undefined,
                }}
                onClick={() => onViewInReport(m.sectionId)}
              >
                <TableCell sx={{ fontSize: "0.82rem" }}>
                  <Box sx={{ display: "flex", alignItems: "center", gap: 0.75 }}>
                    {m.label}
                    {quality === "suspect" && (
                      <Tooltip title="Value is 0% — verify data capture before treating as a clinical signal">
                        <WarningAmberIcon sx={{ fontSize: "0.9rem", color: "warning.main" }} />
                      </Tooltip>
                    )}
                    {quality === "ok" && isLargeDrift && (
                      <Tooltip title="Large deviation — verify data capture alongside clinical review">
                        <WarningAmberIcon sx={{ fontSize: "0.9rem", color: "warning.light" }} />
                      </Tooltip>
                    )}
                  </Box>
                </TableCell>
                <TableCell align="right" sx={{ fontSize: "0.82rem", fontWeight: 600, color: quality === "suspect" ? "warning.main" : undefined }}>
                  {fmtVal(m, m.live)}
                </TableCell>
                <TableCell align="right" sx={{ fontSize: "0.82rem", color: "text.secondary" }}>{fmtVal(m, m.baseline)}</TableCell>
                <TableCell align="right" sx={{ fontSize: "0.82rem", fontWeight: 600, color: quality === "suspect" ? "warning.main" : direction === "worse" ? "error.main" : direction === "better" ? "success.main" : "text.primary" }}>
                  {diff > 0 ? "+" : ""}{Math.round(diff * 10) / 10}{m.unit}
                </TableCell>
                <TableCell align="center">
                  {quality === "suspect"
                    ? <Chip label="Data?" size="small" color="warning" variant="outlined" sx={{ fontSize: "0.66rem", height: 20 }} />
                    : <DirectionChip direction={direction} size="small" />
                  }
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </Paper>
  );
}

// ─── Action card (Zone 3) ────────────────────────────────────────────────────

function ActionCard({
  metric,
  rank,
  largeDrift,
  onViewInReport,
}: {
  metric: MetricDef;
  rank: number;
  largeDrift: boolean;
  onViewInReport: (id: string) => void;
}) {
  const diff = metric.live! - metric.baseline!;
  const absDiff = Math.abs(Math.round(diff * 10) / 10);
  const verb = diff > 0 ? "Increased" : "Decreased";

  return (
    <Paper
      variant="outlined"
      sx={{
        p: 2, borderLeft: 4, borderColor: "error.main", borderRadius: 2,
        cursor: "pointer", transition: "background-color 0.15s",
        "&:hover": { bgcolor: "rgba(220,38,38,0.03)" },
      }}
      onClick={() => onViewInReport(metric.sectionId)}
    >
      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <Box sx={{ flex: 1 }}>
          <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 0.5, flexWrap: "wrap" }}>
            <Chip label={`Priority ${rank}`} size="small" color="error" sx={{ fontSize: "0.68rem", fontWeight: 700, height: 20 }} />
            <Typography variant="subtitle1" sx={{ fontWeight: 700, lineHeight: 1.3 }}>
              {metric.label}
            </Typography>
          </Box>
          <Typography variant="body2" color="text.secondary" sx={{ fontSize: "0.82rem" }}>
            {verb} by <strong>{absDiff}{metric.unit}</strong> from{" "}
            <strong>{Math.round(metric.baseline!)}{metric.unit}</strong> (2018) to{" "}
            <strong>{Math.round(metric.live!)}{metric.unit}</strong> today.
          </Typography>
          {largeDrift && (
            <Box sx={{ display: "flex", alignItems: "center", gap: 0.5, mt: 1, p: 1, borderRadius: 1, bgcolor: "rgba(217,119,6,0.07)", border: "1px solid", borderColor: "warning.light" }}>
              <WarningAmberIcon sx={{ fontSize: "0.9rem", color: "warning.main", flexShrink: 0 }} />
              <Typography variant="caption" sx={{ color: "warning.dark", fontSize: "0.75rem", lineHeight: 1.4 }}>
                <strong>Large deviation from baseline.</strong> Verify data capture completeness before treating this as a confirmed clinical signal.
              </Typography>
            </Box>
          )}
        </Box>
        <Button
          size="small"
          variant="outlined"
          color="error"
          endIcon={<OpenInNewIcon sx={{ fontSize: "0.85rem !important" }} />}
          onClick={(e) => { e.stopPropagation(); onViewInReport(metric.sectionId); }}
          sx={{ textTransform: "none", fontSize: "0.72rem", whiteSpace: "nowrap", ml: 2, flexShrink: 0, borderRadius: 2 }}
        >
          Investigate
        </Button>
      </Box>
    </Paper>
  );
}

// ─── Main component ──────────────────────────────────────────────────────────

export default function AuditSnapshotView({
  orgSelected, loading, summary, cancerType, cancerStage, demographics,
  placeOfPresentation, consultations, investigations, referrals,
  intervals, safetyNetting, avoidableDelays, onViewInReport,
}: Props) {
  const [detailOpen, setDetailOpen] = useState(false);

  if (loading) {
    return (
      <Box sx={{ mt: 2 }}>
        <Skeleton variant="rectangular" height={60} sx={{ mb: 2, borderRadius: 1 }} />
        <Grid container spacing={2} sx={{ mb: 3 }}>
          {Array.from({ length: 4 }).map((_, i) => (
            <Grid key={i} size={{ xs: 12, sm: 6, md: 3 }}>
              <Skeleton variant="rectangular" height={110} sx={{ borderRadius: 2 }} />
            </Grid>
          ))}
        </Grid>
        <Skeleton variant="rectangular" height={200} sx={{ mb: 2, borderRadius: 1 }} />
      </Box>
    );
  }

  const bm = mergeBenchmarkMetrics(
    cancerStage, consultations, referrals, intervals,
    safetyNetting, avoidableDelays, demographics,
    placeOfPresentation, investigations, cancerType,
  );
  const metrics = deriveMetrics(cancerStage, consultations, referrals, intervals, safetyNetting, avoidableDelays, bm, orgSelected);
  const totalEpisodes = summary?.total_episodes ?? null;

  // Quality gate — classify every metric before rendering
  const qualities = new Map<string, MetricQuality>(
    metrics.map((m) => [m.id, getMetricQuality(m, totalEpisodes)])
  );
  const okMetrics = metrics.filter((m) => qualities.get(m.id) === "ok");

  const hasBaseline   = metrics.some((m) => m.baseline != null);
  const betterCount   = okMetrics.filter((m) => computeDirection(m.live, m.baseline, m.higherIsBetter, m.threshold) === "better").length;
  const worseCount    = okMetrics.filter((m) => computeDirection(m.live, m.baseline, m.higherIsBetter, m.threshold) === "worse").length;

  const practiceLabel = orgSelected ? "This Practice" : "All Patients (today)";
  const englandLabel  = "All Patients (2018)";

  // Data for summary detail
  const demPractice  = demographics?.scopes.practice;
  const sexMaleLive  = demPractice?.sex.find((s) => s.gender?.toLowerCase() === "male")?.pct;
  const ethnicLive   = demPractice?.ethnicity.find((e) => e.ethnicity?.toLowerCase().includes("white"))?.pct;
  const sexMaleBm    = resolveBenchmarkValue(bm, "demographics.sex_male_pct", orgSelected);
  const medAgeBm     = resolveBenchmarkValue(bm, "demographics.median_age", orgSelected);
  const ethnicBm     = resolveBenchmarkValue(bm, "demographics.white_ethnicity_pct", orgSelected);

  const ctPractice   = cancerType?.scopes.practice ?? [];
  const topCancers   = [...ctPractice].sort((a, b) => b.pct - a.pct).slice(0, 4);
  const ctBmKey      = (type: string) => `condition_type.${type.toLowerCase()}`;

  const popPractice  = placeOfPresentation?.scopes.practice ?? [];
  const gpRow        = popPractice.find((r) => r.place?.toLowerCase().includes("gp") || r.place?.toLowerCase().includes("surgery"));
  const aeRow        = popPractice.find((r) => r.place?.toLowerCase().includes("a&e") || r.place?.toLowerCase().includes("emergency"));

  const conPractice  = consultations?.scopes.practice;
  const invPractice  = investigations?.scopes.practice;
  const invBloodLive = invPractice?.types.find((t) => t.type?.toLowerCase().includes("blood"))?.pct;

  const refPractice  = referrals?.scopes.practice ?? [];
  const twwRow       = refPractice.find((r) => { const rr = r.referral_route?.toLowerCase() ?? ""; return rr === "tww" || rr.includes("two_week"); });
  const emgRow       = refPractice.find((r) => r.referral_route?.toLowerCase() === "emergency");

  const intPractice  = intervals?.scopes.practice;
  const snPractice   = safetyNetting?.scopes.practice;
  const adPractice   = avoidableDelays?.scopes.practice;

  return (
    <Box sx={{ mt: 1 }}>
      {!hasBaseline && (
        <Alert severity="warning" sx={{ mb: 3 }}>
          No 2018 benchmark data loaded. Select a benchmark set in the filter bar above to enable baseline comparisons.
        </Alert>
      )}

      {totalEpisodes != null && (
        <Box sx={{ mb: 3, display: "flex", alignItems: "center", gap: 1.5, flexWrap: "wrap" }}>
          <Chip label={`${totalEpisodes} episode${totalEpisodes !== 1 ? "s" : ""} audited`} size="small" color="primary" variant="outlined" />
          {hasBaseline && betterCount > 0 && <Chip label={`${betterCount} improved`} size="small" color="success" variant="outlined" />}
          {hasBaseline && worseCount > 0 && <Chip label={`${worseCount} worsened`} size="small" color="error" variant="outlined" />}
        </Box>
      )}

      {/* ══════════ ZONE 1 — AWARENESS ══════════ */}

      <ZoneHeader
        zone={1}
        title="Awareness — Where do I stand?"
        subtitle="Key metrics compared to the NCDA 2018 baseline. Green = improved, red = worsened."
        icon={<VisibilityOutlinedIcon fontSize="small" />}
      />

      <Grid container spacing={2} sx={{ mb: 3 }}>
        {metrics.map((m) => (
          <Grid key={m.id} size={{ xs: 12, sm: 6, md: 4, lg: 3 }}>
            <ScorecardCard metric={m} quality={qualities.get(m.id) ?? "ok"} onViewInReport={onViewInReport} />
          </Grid>
        ))}
      </Grid>

      {/* ══════════ ZONE 2 — DIAGNOSIS ══════════ */}

      <ZoneHeader
        zone={2}
        title="Diagnosis — What's changed?"
        subtitle="Metrics ranked by drift from the 2018 baseline. Metrics without data are excluded. Click any row to open the full section."
        icon={<TroubleshootOutlinedIcon fontSize="small" />}
      />

      <Box sx={{ overflowX: "auto" }}>
        <DeviationTable metrics={metrics} qualities={qualities} onViewInReport={onViewInReport} />
      </Box>

      {/* ══════════ ZONE 3 — ACTION ══════════ */}

      {(() => {
        // Only promote genuinely-worse, data-complete metrics to Zone 3
        const actionMetrics = okMetrics
          .filter((m) => m.live != null && m.baseline != null && computeDirection(m.live, m.baseline, m.higherIsBetter, m.threshold) === "worse")
          .sort((a, b) => Math.abs(b.live! - b.baseline!) - Math.abs(a.live! - a.baseline!))
          .slice(0, 3);

        return (
          <>
            <ZoneHeader
              zone={3}
              title="Action — Where should I focus?"
              subtitle={
                actionMetrics.length > 0
                  ? `${actionMetrics.length} confirmed metric${actionMetrics.length !== 1 ? "s have" : " has"} worsened since 2018. Suspect values excluded.`
                  : "No confirmed metrics have worsened since 2018."
              }
              icon={<TrackChangesOutlinedIcon fontSize="small" />}
            />

            {actionMetrics.length > 0 ? (
              <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
                {actionMetrics.map((m, i) => {
                  const absDiff = Math.abs(m.live! - m.baseline!);
                  const largeDrift = m.unit === "%" && absDiff >= LARGE_DRIFT_THRESHOLD;
                  return <ActionCard key={m.id} metric={m} rank={i + 1} largeDrift={largeDrift} onViewInReport={onViewInReport} />;
                })}
              </Box>
            ) : (
              <Alert severity="success" sx={{ mt: 1 }}>
                All confirmed metrics are at or above the 2018 baseline. No immediate action items identified.
              </Alert>
            )}
          </>
        );
      })()}

      {/* ══════════ NCDA REPORT DETAIL (after zones, non-interrupting) ══════════ */}
      <Box sx={{ mt: 5, mb: 2 }}>
        <Button
          size="small"
          onClick={() => setDetailOpen((o) => !o)}
          endIcon={
            <ExpandMoreIcon
              fontSize="small"
              sx={{ transition: "transform 0.2s", transform: detailOpen ? "rotate(180deg)" : "rotate(0deg)" }}
            />
          }
          sx={{ textTransform: "none", fontSize: "0.78rem", color: "text.secondary", fontWeight: 600, px: 1 }}
        >
          {detailOpen ? "Hide" : "Show"} NCDA report summary
        </Button>
        <Collapse in={detailOpen}>
          <Box sx={{ mt: 1.5 }}>
            <Grid container spacing={2}>
              <Grid size={{ xs: 12, md: 6 }}>
                <SummaryCard
                  title="Demographics"
                  practiceLabel={practiceLabel} englandLabel={englandLabel}
                  onView={() => onViewInReport("section-demographics")}
                  rows={[
                    { label: "Male / female", practice: sexMaleLive != null ? `${Math.round(sexMaleLive)}% / ${Math.round(100 - sexMaleLive)}%` : "—", england: sexMaleBm != null ? `${sexMaleBm}% / ${100 - sexMaleBm}%` : "—" },
                    { label: "Median age", practice: "—", england: medAgeBm != null ? `${medAgeBm} years` : "—" },
                    { label: "White ethnicity", practice: fmtPct(ethnicLive), england: fmtPct(ethnicBm) },
                  ]}
                />
                {topCancers.length > 0 && (
                  <SummaryCard
                    title="Cancer Type — Top 4"
                    practiceLabel={practiceLabel} englandLabel={englandLabel}
                    onView={() => onViewInReport("section-cancer-type")}
                    rows={topCancers.map((c) => ({
                      label: c.cancer_type.charAt(0).toUpperCase() + c.cancer_type.slice(1),
                      practice: `${fmtPct(c.pct)} (n=${fmtN(c.n)})`,
                      england: (() => { const v = bm?.[ctBmKey(c.cancer_type)]?.national; return v != null ? `${v}%` : "—"; })(),
                    }))}
                  />
                )}
                <SummaryCard
                  title="Place of Presentation"
                  practiceLabel={practiceLabel} englandLabel={englandLabel}
                  onView={() => onViewInReport("section-place-of-presentation")}
                  rows={[
                    { label: "GP surgery", practice: fmtPct(gpRow?.pct), england: fmtPct(resolveBenchmarkValue(bm, "place_of_presentation.gp_surgery_pct", orgSelected)) },
                    { label: "A&E", practice: fmtPct(aeRow?.pct), england: fmtPct(resolveBenchmarkValue(bm, "place_of_presentation.ae_pct", orgSelected)) },
                  ]}
                />
                <SummaryCard
                  title="Consultations"
                  practiceLabel={practiceLabel} englandLabel={englandLabel}
                  onView={() => onViewInReport("section-consultations")}
                  rows={[
                    { label: "Fewer than 3 before referral", practice: fmtPct(conPractice?.fewer_than_3_pct), england: fmtPct(resolveBenchmarkValue(bm, "consultations.fewer_than_3_pct", orgSelected)) },
                    { label: "Median consultations", practice: conPractice?.median_consultations != null ? String(conPractice.median_consultations) : "—", england: (() => { const v = resolveBenchmarkValue(bm, "consultations.median_consultations", orgSelected); return v != null ? String(v) : "—"; })() },
                  ]}
                />
              </Grid>
              <Grid size={{ xs: 12, md: 6 }}>
                <SummaryCard
                  title="Investigations"
                  practiceLabel={practiceLabel} englandLabel={englandLabel}
                  onView={() => onViewInReport("section-investigations")}
                  rows={[
                    { label: "At least one investigation", practice: fmtPct(invPractice?.has_investigation_pct), england: fmtPct(resolveBenchmarkValue(bm, "investigations.at_least_one_pct", orgSelected)) },
                    { label: "Blood test (of investigations)", practice: fmtPct(invBloodLive), england: fmtPct(resolveBenchmarkValue(bm, "investigations.blood_test_pct", orgSelected)) },
                  ]}
                />
                <SummaryCard
                  title="Referrals"
                  practiceLabel={practiceLabel} englandLabel={englandLabel}
                  onView={() => onViewInReport("section-referrals")}
                  rows={[
                    { label: "Two Week Wait (TWW)", practice: fmtPct(twwRow?.pct), england: fmtPct(resolveBenchmarkValue(bm, "referrals.tww_pct", orgSelected)) },
                    { label: "Emergency", practice: fmtPct(emgRow?.pct), england: fmtPct(resolveBenchmarkValue(bm, "referrals.emergency_pct", orgSelected)) },
                  ]}
                />
                <SummaryCard
                  title="Intervals"
                  practiceLabel={practiceLabel} englandLabel={englandLabel}
                  onView={() => onViewInReport("section-pci")}
                  rows={[
                    { label: "Primary care interval (median)", practice: intPractice?.pci.median != null ? `${Math.round(intPractice.pci.median)} days` : "—", england: (() => { const v = resolveBenchmarkValue(bm, "primary_care_interval.median_pci_days", orgSelected); return v != null ? `${v} days` : "—"; })() },
                    { label: "Diagnostic interval (median)", practice: intPractice?.di.median != null ? `${Math.round(intPractice.di.median)} days` : "—", england: (() => { const v = resolveBenchmarkValue(bm, "diagnostic_interval.median_di_days", orgSelected); return v != null ? `${v} days` : "—"; })() },
                  ]}
                />
                <SummaryCard
                  title="Safety Netting"
                  practiceLabel={practiceLabel} englandLabel={englandLabel}
                  onView={() => onViewInReport("section-safety-netting")}
                  rows={[{ label: "Safety netting recorded", practice: fmtPct(snPractice?.recorded_pct), england: fmtPct(resolveBenchmarkValue(bm, "safety_netting.recorded_pct", orgSelected)) }]}
                />
                <SummaryCard
                  title="Avoidable Delays"
                  practiceLabel={practiceLabel} englandLabel={englandLabel}
                  onView={() => onViewInReport("section-avoidable-delays")}
                  rows={[{ label: "GP-assessed avoidable delay", practice: fmtPct(adPractice?.avoidable_delay_pct), england: fmtPct(resolveBenchmarkValue(bm, "avoidable_delays.avoidable_delay_pct", orgSelected)) }]}
                />
              </Grid>
            </Grid>
          </Box>
        </Collapse>
      </Box>

    </Box>
  );
}
