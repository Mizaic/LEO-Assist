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
 * View 2 — Insight Snapshot
 *
 * Two zones following the clinician's job-to-be-done:
 *
 *   Zone 1 — WHAT DO I NEED TO KNOW?
 *     -> 8 scorecard cards with mini line charts (2019 -> Y-2 -> Y-1 -> Y)
 *     -> Dashed reference line at NHS/NICE target value where applicable
 *     -> Per-year value and trend markers
 *
 *   Zone 2 — WHAT DO I NEED TO DO ABOUT IT?
 *     -> Top 3 measures furthest from target / most worsened, with narrative + drill-down
 *     -> Collapsible NCDA summary detail (quiet, subordinate)
 *
 * Information hierarchy: trend -> action -> drill-down.
 */

import { useState } from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Grid from "@mui/material/Grid";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Button from "@mui/material/Button";
import Skeleton from "@mui/material/Skeleton";
import Alert from "@mui/material/Alert";
import Chip from "@mui/material/Chip";
import Paper from "@mui/material/Paper";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import OpenInNewIcon from "@mui/icons-material/OpenInNew";
import VisibilityOutlinedIcon from "@mui/icons-material/VisibilityOutlined";
import TrackChangesOutlinedIcon from "@mui/icons-material/TrackChangesOutlined";
import WarningAmberIcon from "@mui/icons-material/WarningAmber";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
import FlagOutlinedIcon from "@mui/icons-material/FlagOutlined";
import Tooltip from "@mui/material/Tooltip";
import {
  LineChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  XAxis,
} from "recharts";
import { computeDirection, type Direction } from "./DirectionChip";
import { resolveBenchmarkValue } from "./BenchmarkLegend";

import type {
  AuditSummary,
  AuditSectionResult,
  AuditCancerStageSummary,
  AuditCancerTypeRow,
  AuditConsultations,
  AuditDemographics,
  AuditInvestigations,
  AuditPlaceRow,
  AuditReferralRow,
  AuditIntervals,
  AuditSafetyNetting,
  AuditAvoidableDelays,
  AuditCareObstruction,
} from "@/lib/analyticsApi";

// ─── NHS National Targets ────────────────────────────────────────────────────

/**
 * By 2035: early stage diagnosis should rise by at least 20 percentage points
 * above the 2019 NCDA benchmark level.
 */
const NHS_TARGET_EARLY_STAGE_INCREASE_PP = 20;
const NHS_TARGET_EARLY_STAGE_YEAR = 2035;

/**
 * By March 2029: 28-day Faster Diagnosis Standard — patients receive a
 * cancer diagnosis or all-clear within 28 days of urgent referral.
 * (Note: our DI metric is the median diagnostic interval in days, which is
 * directionally aligned but not the same as the % within 28 days.)
 */
const NHS_TARGET_DI_DAYS = 28;
const NHS_TARGET_DI_DEADLINE = "March 2029";

/**
 * NICE NG12: referral for suspected cancer should be sent within 1 working day
 * of suspicion of cancer (Primary Care Interval target).
 */
const NHS_TARGET_PCI_DAYS = 1;

// ─── Types & helpers ──────────────────────────────────────────────────────────

/**
 * Per-year summary values for the 3 live calendar years (Y-2, Y-1, Y).
 * Used by the trend table and scorecard trend arrows.
 * The 2019 benchmark values come from the existing `bm` record (benchmark envelope).
 */
export interface YearSummaryPoint {
  year: number;
  earlyStage: number | null;
  pciMedian: number | null;
  diMedian: number | null;
  twwPct: number | null;
  emergencyPct: number | null;
  multipleConsultationsPct: number | null;
  safetyNettingPct: number | null;
  /** Legacy GP-flagged "avoidable delay" rate. Kept for back-compat
   * but no longer surfaced on the snapshot — the snapshot now shows
   * `careObstructionPct` because GP-assessed avoidable delays are
   * almost always 0% in our data (the field is rarely filled in). */
  avoidableDelayPct: number | null;
  /** % of confirmed-cancer pathways with a recorded obstruction
   * (rejection / DNA / cancellation / access barrier) in the
   * milestone window — see libs/oncology/care_obstruction.py. */
  careObstructionPct: number | null;
}

/**
 * Minimum episodes before we trust a 0% metric as a genuine clinical signal.
 * Below this, zero values are likely a data capture gap, not a clinical outcome.
 */
const MIN_EPISODES_FOR_ZERO = 5;

/**
 * Absolute pp drift (percentage points) above which a metric gets a data-quality
 * caveat alongside the clinical flag in the action zone.
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
  /** NHS or NICE hard target for this metric, in the same unit. */
  target?: number | null;
  /** Short label for the target badge shown on the scorecard. */
  targetLabel?: string;
  /** Deadline year / string for the target (e.g. "2035" or "March 2029"). */
  targetDeadline?: string;
  /** Plain note shown on the card when the comparator uses a different source. */
  comparisonNote?: string;
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
  cancerStage:         AuditSectionResult<AuditCancerStageSummary> | null;
  demographics:        AuditSectionResult<AuditDemographics>      | null;
  placeOfPresentation: AuditSectionResult<AuditPlaceRow[]>        | null;
  consultations:       AuditSectionResult<AuditConsultations>     | null;
  investigations:      AuditSectionResult<AuditInvestigations>    | null;
  referrals:           AuditSectionResult<AuditReferralRow[]>     | null;
  intervals:           AuditSectionResult<AuditIntervals>         | null;
  safetyNetting:       AuditSectionResult<AuditSafetyNetting>     | null;
  avoidableDelays:     AuditSectionResult<AuditAvoidableDelays>   | null;
  careObstructions:    AuditSectionResult<AuditCareObstruction>   | null;
  onViewInReport: (sectionId: string) => void;
  /** Human-readable label for the audit cohort window (e.g. "2024-2026"). */
  cohortWindowLabel?: string;
  /**
   * Per-year summary for the 3 live calendar years (Y-2, Y-1, Y) used to
   * populate the trend table and scorecard trend arrows. The 2019 benchmark
   * column is sourced from the benchmark envelope, not this prop.
   */
  yearSummary?: YearSummaryPoint[];
}

// ─── Derive 8 key metrics ────────────────────────────────────────────────────

function deriveMetrics(
  summary: Props["summary"],
  cancerStage: Props["cancerStage"],
  consultations: Props["consultations"],
  referrals: Props["referrals"],
  placeOfPresentation: Props["placeOfPresentation"],
  intervals: Props["intervals"],
  safetyNetting: Props["safetyNetting"],
  avoidableDelays: Props["avoidableDelays"],
  careObstructions: Props["careObstructions"],
  bm: BmRecord | null,
  orgSelected: boolean,
): MetricDef[] {
  const stageRows        = cancerStage?.scopes.practice?.rows ?? [];
  const earlyRow         = stageRows.find((r) => r.stage_group === "early");
  const consultPractice  = consultations?.scopes.practice;

  // Fast-track rate excludes diagnoses whose place of presentation is the
  // Screening Programme. The API owns this denominator so cohort 1a
  // screening-triggered referrals are not counted as GP fast-track referrals.
  const cohort1a = summary?.cohort_1a_n ?? null;
  const cohort3  = summary?.cohort_3_n  ?? null;
  const confirmedTotal = cohort1a != null && cohort3 != null ? cohort1a + cohort3 : null;
  const fastTrackPct = summary?.confirmed_cancers_via_2ww_excluding_screening_pct ?? null;

  // Emergency rate = (Cohort 3 − Screening) / (1A + 3) × 100
  // Screening count comes from place_of_presentation "Screening Programme" row.
  const popPracticeMetrics = placeOfPresentation?.scopes.practice ?? [];
  const screeningRow = popPracticeMetrics.find((r) => r.place?.toLowerCase().includes("screening"));
  const screeningN   = screeningRow?.n ?? 0;
  const emergencyN   = cohort3 != null ? Math.max(0, cohort3 - screeningN) : null;
  const emergencyPct = confirmedTotal != null && confirmedTotal > 0 && emergencyN != null
    ? Math.round((emergencyN / confirmedTotal) * 1000) / 10
    : null;

  // Referrals kept as last-resort fallback if cohort data is absent.
  const refPractice = referrals?.scopes.practice ?? [];
  const emgRefRow   = refPractice.find((r) => r.referral_route?.toLowerCase() === "emergency");
  const intervalPractice = intervals?.scopes.practice;
  const snPractice       = safetyNetting?.scopes.practice;
  const delayPractice    = avoidableDelays?.scopes.practice;
  const coPractice       = careObstructions?.scopes.practice;
  // Acknowledge intentionally unused legacy variable so TS strict mode
  // doesn't flag it. Keeps the data wiring intact in case the section
  // table starts surfacing the GP-flagged number again.
  void delayPractice;

  const baselineEarlyStage = resolveBenchmarkValue(bm, "cancer_stage.early_stage_pct", orgSelected);
  const earlyStageTarget   = baselineEarlyStage != null
    ? Math.round((baselineEarlyStage + NHS_TARGET_EARLY_STAGE_INCREASE_PP) * 10) / 10
    : null;

  return [
    {
      id: "early_stage",
      label: "Early stage diagnosis",
      unit: "%",
      sectionId: "section-cancer-stage",
      higherIsBetter: true,
      live: earlyRow?.pct ?? null,
      baseline: baselineEarlyStage,
      target: earlyStageTarget,
      targetLabel: `+${NHS_TARGET_EARLY_STAGE_INCREASE_PP}pp above 2019`,
      targetDeadline: String(NHS_TARGET_EARLY_STAGE_YEAR),
    },
    {
      id: "multiple_consultations",
      label: "Multiple consultations (3+)",
      unit: "%",
      sectionId: "section-consultations",
      higherIsBetter: false,
      live: consultPractice?.three_or_more_pct ?? null,
      baseline:
        resolveBenchmarkValue(bm, "consultations.three_or_more_pct", orgSelected) ??
        (() => {
          const f = resolveBenchmarkValue(bm, "consultations.fewer_than_3_pct", orgSelected);
          return f != null ? Math.round((100 - f) * 10) / 10 : null;
        })(),
    },
    {
      id: "tww_referral",
      label: "Fast Track Referrals",
      unit: "%",
      sectionId: "section-ftr-types",
      higherIsBetter: true,
      live: fastTrackPct,
      baseline: resolveBenchmarkValue(bm, "referrals.tww_pct", orgSelected),
    },
    {
      id: "emergency_referral",
      label: "Emergency referral rate",
      unit: "%",
      sectionId: "section-ftr-types",
      higherIsBetter: false,
      live: emergencyPct ?? emgRefRow?.pct ?? null,
      baseline: resolveBenchmarkValue(bm, "referrals.emergency_pct", orgSelected),
    },
    {
      id: "pci_days",
      label: "Median time to referral",
      unit: " days",
      sectionId: "section-pci",
      higherIsBetter: false,
      threshold: 1,
      live: intervalPractice?.pci.median ?? null,
      baseline: resolveBenchmarkValue(bm, "primary_care_interval.median_pci_days", orgSelected),
      target: NHS_TARGET_PCI_DAYS,
      targetLabel: "NICE NG12: \u22641 day",
      targetDeadline: "Ongoing",
    },
    {
      id: "di_days",
      label: "Median time to diagnosis",
      unit: " days",
      sectionId: "section-di",
      higherIsBetter: false,
      threshold: 3,
      live: intervalPractice?.di.median ?? null,
      baseline: resolveBenchmarkValue(bm, "diagnostic_interval.median_di_days", orgSelected),
      target: NHS_TARGET_DI_DAYS,
      targetLabel: `28-day FDS`,
      targetDeadline: NHS_TARGET_DI_DEADLINE,
    },
    {
      id: "safety_netting",
      label: "Safety netting recorded",
      unit: "%",
      sectionId: "section-safety-netting",
      higherIsBetter: true,
      live: snPractice?.recorded_pct ?? null,
      baseline: resolveBenchmarkValue(bm, "safety_netting.recorded_pct", orgSelected),
    },
    {
      // The live signal is automatic from the record. The 2019 NCDA
      // comparator is the closest published measure: GP-confirmed
      // avoidable delay.
      id: "care_obstruction",
      label: "Avoidable delays",
      unit: "%",
      sectionId: "section-avoidable-delays",
      higherIsBetter: false,
      live: coPractice?.recorded_pct ?? null,
      baseline: resolveBenchmarkValue(bm, "avoidable_delays.avoidable_delay_pct", orgSelected),
      comparisonNote: "2019 is GP-confirmed. Live years are potentially avoidable -- detected automatically, not clinician-reviewed.",
    },
  ];
}

// ─── Helper: get the per-year value for a given metric id ────────────────────

function getYearValue(point: YearSummaryPoint, metricId: string): number | null {
  switch (metricId) {
    case "early_stage":       return point.earlyStage;
    case "pci_days":          return point.pciMedian;
    case "di_days":           return point.diMedian;
    case "tww_referral":      return point.twwPct;
    case "emergency_referral":return point.emergencyPct;
    case "multiple_consultations": return point.multipleConsultationsPct;
    case "safety_netting":    return point.safetyNettingPct;
    case "avoidable_delay":   return point.avoidableDelayPct;
    case "care_obstruction":  return point.careObstructionPct;
    default: return null;
  }
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

// ─── Hex colours matching GLOW keys (for recharts SVG context) ───────────────

const CHART_COLOR: Record<Direction | "suspect" | "insufficient", string> = {
  better:       "#16a34a",
  worse:        "#dc2626",
  unchanged:    "#d97706",
  unknown:      "#94a3b8",
  suspect:      "#d97706",
  insufficient: "#cbd5e1",
};

const YEAR_TREND_THRESHOLD = 0.5;

function getYearPointDirection(
  current: number | null,
  previous: number | null,
  metric: MetricDef,
): Direction {
  return computeDirection(current, previous, metric.higherIsBetter, metric.threshold ?? YEAR_TREND_THRESHOLD);
}

function pointTrendLabel(point: { v: number | null; direction: Direction }, index: number): string {
  if (point.v == null) return "No data";
  if (index === 0) return "Base";
  if (point.direction === "unknown") return "No trend";
  if (point.direction === "unchanged") return "Same";
  return point.direction === "better" ? "Better" : "Worse";
}

function pointTrendColor(direction: Direction, hasValue: boolean): string {
  if (!hasValue || direction === "unknown") return "text.disabled";
  if (direction === "better") return "success.main";
  if (direction === "worse") return "error.main";
  return "text.secondary";
}

function metricCalculationText(metricId: string): string[] {
  const shared = "The 2019 value comes from the benchmark set. Later years use your audit data.";
  switch (metricId) {
    case "early_stage":
      return [
        "We count cancers found at stage 1 or stage 2.",
        "We divide this by all cancers with a recorded stage.",
        shared,
      ];
    case "fewer_than_3":
      return [
        "We count people who had fewer than 3 GP contacts before referral.",
        "We divide this by all pathways with consultation data.",
        shared,
      ];
    case "tww_referral":
      return [
        "We count confirmed cancers sent by fast-track referral.",
        "We leave out cancers first found through the screening programme.",
        "We divide this by confirmed cancers not found through screening.",
        shared,
      ];
    case "emergency_referral":
      return [
        "We count confirmed cancers found after an emergency or urgent care route.",
        "We leave out screening programme cases from this count.",
        "We divide this by all confirmed cancers in the audit.",
        shared,
      ];
    case "pci_days":
      return [
        "For each pathway, we count days from first contact to referral.",
        "We show the middle value, not the average.",
        shared,
      ];
    case "di_days":
      return [
        "For each pathway, we count days from first contact to diagnosis.",
        "We show the middle value, not the average.",
        shared,
      ];
    case "safety_netting":
      return [
        "We count confirmed cancers with a clear safety-net note.",
        "This can include advice on what to do if symptoms get worse.",
        "We divide this by all confirmed cancers.",
        shared,
      ];
    case "care_obstruction":
      return [
        "We count pathways with a potential delay detected in the clinical record.",
        "This includes rejected referrals, missed appointments, cancellations, or access problems. The 2019 figure is GP-confirmed; live years are algorithmically detected and not clinician-reviewed.",
        "We divide this by all confirmed cancers.",
        "The 2019 value is different. It is a GP-confirmed avoidable delay measure.",
        "Later years are potential delay signals found from the record.",
      ];
    default:
      return [
        "We calculate this from the audit records for the selected dates.",
        shared,
      ];
  }
}

function ScorecardSkeleton() {
  return (
    <Card variant="outlined" sx={{ height: "100%", borderRadius: 2 }}>
      <CardContent sx={{ pb: "12px !important", display: "flex", flexDirection: "column" }}>
        <Box sx={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 0.75 }}>
          <Skeleton variant="text" width="48%" height={22} />
          <Skeleton variant="rounded" width={48} height={20} />
        </Box>
        <Box sx={{ position: "relative", height: 58, mx: -1, mt: 1 }}>
          <Skeleton variant="rounded" height={1} width="100%" sx={{ position: "absolute", top: 12, left: 8, right: 8 }} />
          <Skeleton variant="rounded" height={1} width="100%" sx={{ position: "absolute", top: 34, left: 8, right: 8 }} />
          <Skeleton variant="rounded" height={2} width="88%" sx={{ position: "absolute", top: 25, left: 12 }} />
          {[10, 36, 62, 88].map((left) => (
            <Skeleton
              key={left}
              variant="circular"
              width={6}
              height={6}
              sx={{ position: "absolute", left: `${left}%`, top: 22 }}
            />
          ))}
        </Box>
        <Box sx={{ display: "grid", gridTemplateColumns: "repeat(4, minmax(0, 1fr))", gap: 0.5, mt: 0.75 }}>
          {[0, 1, 2, 3].map((idx) => (
            <Box key={idx} sx={{ px: 0.25, py: 0.35, borderRadius: 1, bgcolor: "rgba(148,163,184,0.08)" }}>
              <Skeleton variant="text" width="52%" height={12} />
              <Skeleton variant="text" width="72%" height={14} />
              <Skeleton variant="text" width="58%" height={12} />
            </Box>
          ))}
        </Box>
      </CardContent>
    </Card>
  );
}

// ─── Hero scorecard card — line chart showing year-on-year progression ────────

function ScorecardCard({
  metric,
  quality,
  yearSummary,
  onViewInReport,
}: {
  metric: MetricDef;
  quality: MetricQuality;
  yearSummary?: YearSummaryPoint[];
  onViewInReport: (id: string) => void;
}) {
  const [explanationOpen, setExplanationOpen] = useState(false);
  const direction = quality === "ok"
    ? computeDirection(metric.live, metric.baseline, metric.higherIsBetter, metric.threshold)
    : "unknown";
  const glowKey = quality === "ok" ? direction : quality;
  const glow    = GLOW[glowKey];
  const color   = CHART_COLOR[glowKey];

  const fmtVal = (v: number | null) => v == null ? "—" : `${Math.round(v)}${metric.unit}`;

  // Build chart data: 2019 benchmark -> Y-2 -> Y-1 -> Y (current).
  // Keep null years so the x-axis still shows all four years and the line
  // breaks rather than bridging over missing data.
  type ChartPoint = { label: string; v: number | null; direction: Direction };
  const rawChartPoints: Array<Omit<ChartPoint, "direction">> = [{ label: "2019", v: metric.baseline }];
  if (yearSummary?.length) {
    for (const yp of yearSummary) {
      rawChartPoints.push({ label: String(yp.year), v: getYearValue(yp, metric.id) });
    }
  } else if (metric.live != null) {
    rawChartPoints.push({ label: "Now", v: metric.live });
  }
  const chartPoints: ChartPoint[] = rawChartPoints.map((point, index) => ({
    ...point,
    direction: index === 0
      ? "unknown"
      : getYearPointDirection(point.v, rawChartPoints[index - 1]?.v ?? null, metric),
  }));
  const hasChart = quality === "ok" && chartPoints.some((p) => p.v != null);

  const explanationId = `metric-explanation-${metric.id}`;

  return (
    <>
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
        <CardContent sx={{ pb: "12px !important", display: "flex", flexDirection: "column" }}>
          <Box sx={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 0.75 }}>
            <Typography variant="caption" sx={{ color: "text.secondary", fontWeight: 600, fontSize: "0.7rem", textTransform: "uppercase", letterSpacing: 0.4 }}>
              {metric.label}
            </Typography>
            <Tooltip title="How we calculated this">
              <Button
                aria-label={`How we calculated ${metric.label}`}
                size="small"
                variant="text"
                startIcon={<InfoOutlinedIcon sx={{ fontSize: "0.82rem !important" }} />}
                onClick={(event) => {
                  event.stopPropagation();
                  setExplanationOpen(true);
                }}
                sx={{
                  mt: -0.5,
                  mr: -0.75,
                  minWidth: 0,
                  px: 0.5,
                  py: 0,
                  fontSize: "0.64rem",
                  fontWeight: 700,
                  textTransform: "none",
                  color: "text.secondary",
                }}
              >
                How?
              </Button>
            </Tooltip>
          </Box>

        {quality === "insufficient" ? (
          <>
            <Box sx={{ display: "flex", alignItems: "center", gap: 0.75, mt: 1 }}>
              <InfoOutlinedIcon sx={{ fontSize: "1rem", color: "text.disabled" }} />
              <Typography variant="body2" sx={{ color: "text.disabled", fontStyle: "italic", fontSize: "0.82rem" }}>
                No data recorded
              </Typography>
            </Box>
            <Typography variant="caption" sx={{ color: "text.disabled", display: "block", mt: 0.75, fontSize: "0.7rem" }}>
              Not included in the trend table
            </Typography>
          </>
        ) : quality === "suspect" ? (
          <>
            <Box sx={{ display: "flex", alignItems: "baseline", gap: 1, mt: 0.5 }}>
              <Typography variant="h5" sx={{ fontWeight: 800, lineHeight: 1, color: "warning.main" }}>
                {fmtVal(metric.live)}
              </Typography>
            </Box>
            <Box sx={{ display: "flex", alignItems: "center", gap: 0.5, mt: 1 }}>
              <WarningAmberIcon sx={{ fontSize: "0.9rem", color: "warning.main" }} />
              <Typography variant="caption" sx={{ color: "warning.main", fontWeight: 600, fontSize: "0.7rem" }}>
                Check data recording
              </Typography>
            </Box>
            <Typography variant="caption" sx={{ color: "text.disabled", display: "block", mt: 0.5, fontSize: "0.7rem" }}>
              2019 benchmark: {fmtVal(metric.baseline)} — not included in priority list
            </Typography>
          </>
        ) : (
          <>
            {hasChart && (
              <Box sx={{ height: 58, mx: -1, mt: 1 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={chartPoints} margin={{ top: 6, right: 8, left: 8, bottom: 0 }}>
                    <XAxis
                      dataKey="label"
                      tick={{ fontSize: 9, fill: "#94a3b8" }}
                      axisLine={false}
                      tickLine={false}
                      interval={0}
                    />
                    {metric.target != null && (
                      <ReferenceLine
                        y={metric.target}
                        stroke={color}
                        strokeDasharray="3 3"
                        strokeOpacity={0.55}
                        strokeWidth={1}
                      />
                    )}
                    <Line
                      type="monotone"
                      dataKey="v"
                      stroke={color}
                      strokeWidth={1.5}
                      fill="none"
                      dot={{ r: 2, fill: color, strokeWidth: 0 }}
                      activeDot={false}
                      connectNulls={false}
                      isAnimationActive={false}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </Box>
            )}

            <Box
              sx={{
                display: "grid",
                gridTemplateColumns: `repeat(${chartPoints.length}, minmax(0, 1fr))`,
                gap: 0.5,
                mt: hasChart ? 0.75 : 1,
              }}
            >
              {chartPoints.map((point, index) => {
                const trendText = pointTrendLabel(point, index);
                const hasValue = point.v != null;
                return (
                  <Box
                    key={point.label}
                    aria-label={`${point.label}: ${hasValue ? fmtVal(point.v) : "no data"}. ${trendText}`}
                    sx={{
                      minWidth: 0,
                      px: 0.25,
                      py: 0.35,
                      borderRadius: 1,
                      bgcolor: hasValue ? "rgba(255,255,255,0.55)" : "rgba(148,163,184,0.08)",
                    }}
                  >
                    <Typography variant="caption" sx={{ display: "block", color: "text.disabled", fontSize: "0.62rem", lineHeight: 1.1 }}>
                      {point.label}
                    </Typography>
                    <Typography
                      variant="caption"
                      sx={{
                        display: "block",
                        color: hasValue ? "text.primary" : "text.disabled",
                        fontSize: "0.68rem",
                        fontWeight: 700,
                        lineHeight: 1.15,
                        whiteSpace: "nowrap",
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                      }}
                    >
                      {hasValue ? fmtVal(point.v) : "No data"}
                    </Typography>
                    <Typography
                      variant="caption"
                      sx={{
                        display: "block",
                        color: pointTrendColor(point.direction, hasValue),
                        fontSize: "0.62rem",
                        fontWeight: 700,
                        lineHeight: 1.1,
                      }}
                    >
                      {trendText}
                    </Typography>
                  </Box>
                );
              })}
            </Box>
            {metric.targetLabel && metric.target != null && (
              <Box sx={{ display: "flex", alignItems: "center", gap: 0.5, mt: 0.5 }}>
                <FlagOutlinedIcon sx={{ fontSize: "0.75rem", color: "primary.light" }} />
                <Typography variant="caption" sx={{ color: "primary.main", fontSize: "0.68rem", fontWeight: 600 }}>
                  {metric.targetLabel}
                  {metric.targetDeadline ? ` by ${metric.targetDeadline}` : ""}
                </Typography>
              </Box>
            )}
            {metric.comparisonNote && (
              <Typography variant="caption" sx={{ color: "text.secondary", display: "block", mt: 0.5, fontSize: "0.66rem", lineHeight: 1.25 }}>
                {metric.comparisonNote}
              </Typography>
            )}
          </>
        )}
        </CardContent>
      </Card>
      <Dialog
        open={explanationOpen}
        onClose={() => setExplanationOpen(false)}
        aria-labelledby={explanationId}
        maxWidth="xs"
        fullWidth
      >
        <DialogTitle id={explanationId} sx={{ fontSize: "1rem", fontWeight: 700 }}>
          How we calculated {metric.label}
        </DialogTitle>
        <DialogContent>
          <Box component="ul" sx={{ pl: 2.25, my: 0 }}>
            {metricCalculationText(metric.id).map((line) => (
              <Typography key={line} component="li" variant="body2" sx={{ mb: 1, fontSize: "0.88rem" }}>
                {line}
              </Typography>
            ))}
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setExplanationOpen(false)} size="small" variant="contained">
            Close
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
}

// ─── Action card (Zone 2) ────────────────────────────────────────────────────

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
            <strong>{Math.round(metric.baseline!)}{metric.unit}</strong> (2019 benchmark) to{" "}
            <strong>{Math.round(metric.live!)}{metric.unit}</strong> today.
          </Typography>
          {metric.target != null && metric.targetLabel && (
            <Box sx={{ display: "flex", alignItems: "center", gap: 0.5, mt: 0.75 }}>
              <FlagOutlinedIcon sx={{ fontSize: "0.85rem", color: "primary.light" }} />
              <Typography variant="caption" sx={{ color: "primary.main", fontSize: "0.75rem", fontWeight: 600 }}>
                {metric.targetLabel}{metric.targetDeadline ? ` by ${metric.targetDeadline}` : ""}
              </Typography>
            </Box>
          )}
          {largeDrift && (
            <Box sx={{ display: "flex", alignItems: "center", gap: 0.5, mt: 1, p: 1, borderRadius: 1, bgcolor: "rgba(217,119,6,0.07)", border: "1px solid", borderColor: "warning.light" }}>
              <WarningAmberIcon sx={{ fontSize: "0.9rem", color: "warning.main", flexShrink: 0 }} />
              <Typography variant="caption" sx={{ color: "warning.dark", fontSize: "0.75rem", lineHeight: 1.4 }}>
                <strong>Large change from the 2019 figure.</strong> Check that data recording is complete before treating this as a confirmed finding.
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
  intervals, safetyNetting, avoidableDelays, careObstructions, onViewInReport,
  cohortWindowLabel, yearSummary,
}: Props) {
  if (loading) {
    return (
      <Box sx={{ mt: 2 }}>
        <Skeleton variant="rounded" height={42} sx={{ mb: 2, borderRadius: 1 }} />
        <Grid container spacing={2} sx={{ mb: 3 }}>
          {Array.from({ length: 8 }).map((_, i) => (
            <Grid key={i} size={{ xs: 12, sm: 6, md: 4, lg: 3 }}>
              <ScorecardSkeleton />
            </Grid>
          ))}
        </Grid>
      </Box>
    );
  }

  const bm = mergeBenchmarkMetrics(
    cancerStage, consultations, referrals, intervals,
    safetyNetting, avoidableDelays, careObstructions, demographics,
    placeOfPresentation, investigations, cancerType,
  );
  const metrics = deriveMetrics(summary, cancerStage, consultations, referrals, placeOfPresentation, intervals, safetyNetting, avoidableDelays, careObstructions, bm, orgSelected);
  const totalEpisodes = summary?.total_episodes ?? null;

  const qualities = new Map<string, MetricQuality>(
    metrics.map((m) => [m.id, getMetricQuality(m, totalEpisodes)])
  );
  const okMetrics = metrics.filter((m) => qualities.get(m.id) === "ok");

  const hasBaseline   = metrics.some((m) => m.baseline != null);
  const betterCount   = okMetrics.filter((m) => computeDirection(m.live, m.baseline, m.higherIsBetter, m.threshold) === "better").length;
  const worseCount    = okMetrics.filter((m) => computeDirection(m.live, m.baseline, m.higherIsBetter, m.threshold) === "worse").length;

  return (
    <Box sx={{ mt: 1 }}>
      {!hasBaseline && (
        <Alert severity="warning" sx={{ mb: 3 }}>
          No 2019 comparison data loaded. Choose a benchmark set in the filter bar above to compare your figures against the 2019 NCDA benchmark.
        </Alert>
      )}

      {totalEpisodes != null && (
        <Box sx={{ mb: 3, display: "flex", alignItems: "center", gap: 1.5, flexWrap: "wrap" }}>
          <Chip label={`${totalEpisodes} pathway${totalEpisodes !== 1 ? "s" : ""} audited`} size="small" color="primary" variant="outlined" />
          {cohortWindowLabel && (
            <Chip
              label={`Diagnosis / benign close in ${cohortWindowLabel}`}
              size="small"
              color="default"
              variant="outlined"
            />
          )}
          {hasBaseline && betterCount > 0 && <Chip label={`${betterCount} improved vs 2019`} size="small" color="success" variant="outlined" />}
          {hasBaseline && worseCount > 0 && <Chip label={`${worseCount} worsened vs 2019`} size="small" color="error" variant="outlined" />}
        </Box>
      )}

      {/* ══════════ ZONE 1 — WHAT TO KNOW ══════════ */}

      <ZoneHeader
        zone={1}
        title="What do I need to know?"
        subtitle={
          yearSummary?.length
            ? `Year-on-year progression from the 2019 NCDA benchmark through ${yearSummary.map((p) => p.year).join(", ")}. Dashed line = NHS / NICE target where applicable. Click any card to open the full section.`
            : cohortWindowLabel
            ? `Key measures compared to the 2019 NCDA benchmark. Pathways where diagnosis or benign close occurred in ${cohortWindowLabel}.`
            : "Key measures compared to the 2019 NCDA benchmark. Green = improved, red = worsened."
        }
        icon={<VisibilityOutlinedIcon fontSize="small" />}
      />

      <Grid container spacing={2} sx={{ mb: 3 }}>
        {metrics.map((m) => (
          <Grid key={m.id} size={{ xs: 12, sm: 6, md: 4, lg: 3 }}>
            <ScorecardCard
              metric={m}
              quality={qualities.get(m.id) ?? "ok"}
              yearSummary={yearSummary}
              onViewInReport={onViewInReport}
            />
          </Grid>
        ))}
      </Grid>

      {/* ══════════ ZONE 2 — WHAT TO DO ══════════ */}

      {(() => {
        const actionMetrics = okMetrics
          .filter((m) => m.live != null && m.baseline != null && computeDirection(m.live, m.baseline, m.higherIsBetter, m.threshold) === "worse")
          .sort((a, b) => Math.abs(b.live! - b.baseline!) - Math.abs(a.live! - a.baseline!))
          .slice(0, 3);

        return (
          <>
            <ZoneHeader
              zone={2}
              title="What do I need to do about it?"
              subtitle={
                actionMetrics.length > 0
                  ? `${actionMetrics.length} confirmed measure${actionMetrics.length !== 1 ? "s have" : " has"} worsened since 2019. Measures where data recording may be incomplete are excluded.`
                  : "No confirmed measures have worsened since 2019."
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
                All confirmed measures are at or above the 2019 benchmark level. No areas need immediate attention.
              </Alert>
            )}
          </>
        );
      })()}

    </Box>
  );
}
