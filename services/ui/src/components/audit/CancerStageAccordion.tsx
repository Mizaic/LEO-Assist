"use client";

/**
 * Collapsible accordion listing one segmented bar row per cancer type
 * present in the live data, sorted worst early-diagnosis % first.
 *
 * Each row uses the same green/orange/grey segmented style as the aggregate
 * CancerStageBulletChart, with a brown tick for the 2018 national baseline
 * and a blue dashed tick for the NHS LTP 75% target.
 *
 * The England 2024/25 aggregate (58.7%) is NOT repeated per cancer type --
 * it is only shown on the aggregate chart above.
 */

import { useMemo } from "react";
import Accordion from "@mui/material/Accordion";
import AccordionSummary from "@mui/material/AccordionSummary";
import AccordionDetails from "@mui/material/AccordionDetails";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import TrendingUpIcon from "@mui/icons-material/TrendingUp";
import TrendingDownIcon from "@mui/icons-material/TrendingDown";
import TrendingFlatIcon from "@mui/icons-material/TrendingFlat";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Tooltip from "@mui/material/Tooltip";
import {
  normaliseLiveKey,
  cancerTypeLabel,
  resolveBaseline2019,
  EXCLUDED_CANCER_TYPES,
} from "@/lib/cancerTypeKeys";

// -- Types -------------------------------------------------------------------

interface ByCancerTypeRow {
  cancer_type: string;
  stage_group: "early" | "late" | "unknown";
  n: number;
  pct: number;
}

type BmMetrics = Record<
  string,
  { practice?: number | null; alliance?: number | null; national?: number | null }
>;

export interface CancerStageAccordionProps {
  byCancerType: ByCancerTypeRow[];
  bm: BmMetrics | null | undefined;
  orgSelected: boolean;
}

// -- Colours -----------------------------------------------------------------

const C_EARLY   = "#16A34A";   // green-600
const C_LATE    = "#EA580C";   // orange-600
const C_GREY    = "#CBD5E1";   // slate-300 (unstaged)
const C_BENCH18 = "#92400E";   // amber-900 (2018 NCDA)
const C_LTP     = "#1D4ED8";   // blue-700  (NHS LTP)

const LTP_TARGET = 75;
const TRACK_H  = 16;
const TICK_EXT = 6;

/** Minimum pp difference to be called improving or declining (not stable). */
const TREND_THRESHOLD = 3;

// -- Trend indicator ---------------------------------------------------------

type Trend = "improving" | "stable" | "declining" | "none";

function getTrend(earlyPct: number | null, baseline: number | null): Trend {
  if (earlyPct == null || baseline == null) return "none";
  const diff = earlyPct - baseline;
  if (diff > TREND_THRESHOLD) return "improving";
  if (diff < -TREND_THRESHOLD) return "declining";
  return "stable";
}

const TREND_META = {
  improving: {
    Icon: TrendingUpIcon,
    color: "#16A34A",
    bg: "#DCFCE7",
    label: "Improving",
    tip: (pp: number) => `Early diagnosis is up ${pp}pp vs 2018 national baseline — improving`,
  },
  stable: {
    Icon: TrendingFlatIcon,
    color: "#92400E",
    bg: "#FEF3C7",
    label: "Stable",
    tip: (pp: number) => `Early diagnosis is ${pp >= 0 ? "+" : ""}${pp}pp vs 2018 national baseline — broadly stable`,
  },
  declining: {
    Icon: TrendingDownIcon,
    color: "#DC2626",
    bg: "#FEE2E2",
    label: "Declining",
    tip: (pp: number) => `Early diagnosis is ${pp}pp vs 2018 national baseline — declining`,
  },
  none: null,
} as const;

interface TrendIndicatorProps {
  earlyPct: number | null;
  baseline: number | null;
}

function TrendIndicator({ earlyPct, baseline }: TrendIndicatorProps) {
  const trend = getTrend(earlyPct, baseline);
  const meta = TREND_META[trend];
  if (!meta) return null;

  const diff = earlyPct != null && baseline != null
    ? Math.round((earlyPct - baseline) * 10) / 10
    : 0;

  const { Icon, color, bg, label, tip } = meta;

  return (
    <Tooltip title={tip(diff)} placement="top" arrow>
      <Box
        component="span"
        sx={{
          display: "inline-flex",
          alignItems: "center",
          gap: 0.3,
          px: 0.6,
          py: 0.15,
          borderRadius: "4px",
          bgcolor: bg,
          color,
          ml: 1,
          verticalAlign: "middle",
          cursor: "default",
          userSelect: "none",
        }}
      >
        <Icon sx={{ fontSize: "0.85rem" }} />
        <Typography
          component="span"
          sx={{ fontSize: "0.6rem", fontWeight: 700, color, lineHeight: 1 }}
        >
          {label}
        </Typography>
      </Box>
    </Tooltip>
  );
}

// -- Tick --------------------------------------------------------------------

interface TickProps {
  pct: number;
  color: string;
  label: string;
  sublabel: string;
  dashed?: boolean;
  tip: string;
}

function Tick({ pct, color, label, sublabel, dashed = false, tip }: TickProps) {
  const x = Math.min(Math.max(pct, 0), 100);
  return (
    <Tooltip title={tip} placement="top" arrow>
      <Box
        sx={{
          position: "absolute",
          left: `${x}%`,
          top: -TICK_EXT,
          transform: "translateX(-50%)",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          cursor: "default",
          zIndex: 2,
        }}
      >
        <Box
          sx={{
            width: dashed ? "1px" : "2px",
            height: TRACK_H + TICK_EXT * 2,
            bgcolor: dashed ? "transparent" : color,
            borderLeft: dashed ? `2px dashed ${color}` : "none",
            borderRadius: dashed ? 0 : "2px",
          }}
        />
        <Box sx={{ textAlign: "center", mt: 0.4 }}>
          <Typography
            component="div"
            sx={{ fontSize: "0.58rem", fontWeight: 700, color, lineHeight: 1.1, whiteSpace: "nowrap" }}
          >
            {label}
          </Typography>
          <Typography
            component="div"
            sx={{ fontSize: "0.55rem", color: "text.disabled", lineHeight: 1.1, whiteSpace: "nowrap" }}
          >
            {sublabel}
          </Typography>
        </Box>
      </Box>
    </Tooltip>
  );
}

// -- Single cancer-type row --------------------------------------------------

interface RowData {
  label: string;
  earlyPct: number | null;
  earlyN: number | null;
  latePct: number | null;
  lateN: number | null;
  baseline2019: number | null;
  fromFallback: boolean;
  hasData: boolean;
}

function CancerTypeRow({ row }: { row: RowData }) {
  const early    = row.earlyPct ?? 0;
  const late     = row.latePct ?? 0;
  const unstaged = Math.max(0, 100 - early - late);

  if (!row.hasData) {
    return (
      <Box
        sx={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          py: 0.75,
          px: 1,
          borderRadius: 1,
          bgcolor: "action.hover",
        }}
      >
        <Typography variant="body2" color="text.secondary" sx={{ fontWeight: 600 }}>
          {row.label}
        </Typography>
        <Typography variant="caption" color="text.disabled">
          No stage data
        </Typography>
      </Box>
    );
  }

  return (
    <Box sx={{ py: 0.75 }}>
      {/* Label + headline numbers */}
      <Box
        sx={{
          display: "flex",
          alignItems: "baseline",
          justifyContent: "space-between",
          mb: 0.5,
          flexWrap: "wrap",
          gap: 0.5,
        }}
      >
        <Box sx={{ display: "flex", alignItems: "center", flexWrap: "wrap", gap: 0 }}>
          <Typography component="span" variant="body2" sx={{ fontWeight: 700, color: "text.primary" }}>
            {row.label}
          </Typography>
          <TrendIndicator earlyPct={row.earlyPct} baseline={row.baseline2019} />
          {row.fromFallback && (
            <Typography
              component="span"
              variant="caption"
              color="text.disabled"
              sx={{ ml: 0.75, fontStyle: "italic" }}
            >
              (published estimate)
            </Typography>
          )}
        </Box>

        <Box sx={{ display: "flex", gap: 2, alignItems: "baseline", flexShrink: 0 }}>
          <Box sx={{ display: "flex", alignItems: "baseline", gap: 0.4 }}>
            <Typography
              component="span"
              sx={{ fontWeight: 800, fontSize: "0.95rem", color: C_EARLY, lineHeight: 1 }}
            >
              {row.earlyPct != null ? `${Math.round(early)}%` : "--"}
            </Typography>
            <Typography component="span" variant="caption" color="text.secondary">
              early
            </Typography>
            {row.earlyN != null && (
              <Typography component="span" variant="caption" color="text.disabled">
                n={row.earlyN}
              </Typography>
            )}
          </Box>
          <Box sx={{ display: "flex", alignItems: "baseline", gap: 0.4 }}>
            <Typography
              component="span"
              sx={{ fontWeight: 800, fontSize: "0.95rem", color: C_LATE, lineHeight: 1 }}
            >
              {row.latePct != null ? `${Math.round(late)}%` : "--"}
            </Typography>
            <Typography component="span" variant="caption" color="text.secondary">
              late
            </Typography>
            {row.lateN != null && (
              <Typography component="span" variant="caption" color="text.disabled">
                n={row.lateN}
              </Typography>
            )}
          </Box>
          {unstaged > 0.5 && (
            <Box sx={{ display: "flex", alignItems: "baseline", gap: 0.4 }}>
              <Typography
                component="span"
                sx={{ fontWeight: 600, fontSize: "0.85rem", color: "text.disabled", lineHeight: 1 }}
              >
                {Math.round(unstaged)}%
              </Typography>
              <Typography component="span" variant="caption" color="text.disabled">
                unstaged
              </Typography>
            </Box>
          )}
        </Box>
      </Box>

      {/* Segmented bar track */}
      <Box sx={{ position: "relative", height: TRACK_H + TICK_EXT + 34 }}>
        {/* Grey background */}
        <Box
          sx={{
            position: "absolute",
            top: TICK_EXT,
            left: 0,
            right: 0,
            height: TRACK_H,
            bgcolor: C_GREY,
            borderRadius: "4px",
          }}
        />

        {/* Orange late */}
        {late > 0 && (
          <Box
            sx={{
              position: "absolute",
              top: TICK_EXT,
              left: `${early}%`,
              width: `${late}%`,
              height: TRACK_H,
              bgcolor: C_LATE,
              opacity: 0.82,
            }}
          />
        )}

        {/* Green early */}
        {early > 0 && (
          <Box
            sx={{
              position: "absolute",
              top: TICK_EXT,
              left: 0,
              width: `${early}%`,
              height: TRACK_H,
              bgcolor: C_EARLY,
              borderRadius: `4px ${late > 0 ? "0 0" : "4px 4px"} 4px`,
              opacity: 0.82,
              zIndex: 1,
            }}
          />
        )}

        {/* 2018 baseline tick */}
        {row.baseline2019 != null && (
          <Tick
            pct={row.baseline2019}
            color={C_BENCH18}
            label={`${row.baseline2019}%`}
            sublabel="2018"
            tip={`2018/19 national early-stage rate for ${row.label}: ${row.baseline2019}%${row.fromFallback ? " (published NDRS estimate)" : ""}`}
          />
        )}

        {/* LTP 75% target */}
        <Tick
          pct={LTP_TARGET}
          color={C_LTP}
          label={`${LTP_TARGET}%`}
          sublabel="Target"
          dashed
          tip={`NHS Long Term Plan 2028 target: ${LTP_TARGET}% of cancers diagnosed at stage 1 or 2`}
        />
      </Box>
    </Box>
  );
}

// -- Data processing ---------------------------------------------------------

function buildRows(
  byCancerType: ByCancerTypeRow[],
  bm: BmMetrics | null | undefined,
): RowData[] {
  const aggregated: Map<string, { earlyPct: number | null; earlyN: number | null; latePct: number | null; lateN: number | null }> = new Map();

  for (const row of byCancerType) {
    const key = normaliseLiveKey(row.cancer_type);
    if (EXCLUDED_CANCER_TYPES.has(key)) continue;

    if (!aggregated.has(key)) {
      aggregated.set(key, { earlyPct: null, earlyN: null, latePct: null, lateN: null });
    }
    const entry = aggregated.get(key)!;

    if (row.stage_group === "early") {
      entry.earlyPct = row.pct;
      entry.earlyN   = row.n;
    } else if (row.stage_group === "late") {
      entry.latePct = row.pct;
      entry.lateN   = row.n;
    }
  }

  const rows: RowData[] = [];

  for (const [key, data] of aggregated.entries()) {
    const bmKey = `cancer_stage.by_cancer_type.${key}.early_stage_pct`;
    const bmNational = bm?.[bmKey]?.national ?? null;
    const fromFallback = bmNational == null;
    const baseline2019 = resolveBaseline2019(key, bm);

    rows.push({
      label: cancerTypeLabel(key),
      earlyPct:  data.earlyPct,
      earlyN:    data.earlyN,
      latePct:   data.latePct,
      lateN:     data.lateN,
      baseline2019,
      fromFallback,
      hasData:   data.earlyPct != null || data.latePct != null,
    });
  }

  // Sort: no-data types last, then worst early-diagnosis % first
  rows.sort((a, b) => {
    if (!a.hasData && b.hasData) return 1;
    if (a.hasData && !b.hasData) return -1;
    const aEarly = a.earlyPct ?? 100;
    const bEarly = b.earlyPct ?? 100;
    return aEarly - bEarly;
  });

  return rows;
}

// -- Legend strip for accordion details -------------------------------------

function MiniLegend() {
  return (
    <Box sx={{ display: "flex", flexWrap: "wrap", gap: 2, mb: 2 }}>
      {[
        { color: C_EARLY,   label: "Early (stage 0-2)", dash: false },
        { color: C_LATE,    label: "Late (stage 3-4)",   dash: false },
        { color: C_GREY,    label: "Not staged",         dash: false },
        { color: C_BENCH18, label: "2018 national",      dash: false },
        { color: C_LTP,     label: "LTP target (75%)",   dash: true  },
      ].map(({ color, label, dash }) => (
        <Box key={label} sx={{ display: "flex", alignItems: "center", gap: 0.6 }}>
          {dash ? (
            <Box sx={{ width: 14, height: 2, bgcolor: color, borderRadius: 1 }} />
          ) : (
            <Box sx={{ width: 9, height: 9, borderRadius: "2px", bgcolor: color }} />
          )}
          <Typography variant="caption" sx={{ fontSize: "0.68rem", color: "text.secondary" }}>
            {label}
          </Typography>
        </Box>
      ))}
    </Box>
  );
}

// -- Main export -------------------------------------------------------------

export default function CancerStageAccordion({
  byCancerType,
  bm,
  orgSelected: _orgSelected,
}: CancerStageAccordionProps) {
  const rows = useMemo(
    () => buildRows(byCancerType, bm),
    [byCancerType, bm],
  );

  const typesWithData = rows.filter((r) => r.hasData).length;

  if (rows.length === 0) {
    return (
      <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
        No cancer type breakdown available for the selected period.
      </Typography>
    );
  }

  return (
    <Accordion defaultExpanded={false} disableGutters elevation={0} sx={{ border: "1px solid", borderColor: "divider", borderRadius: "8px !important", "&:before": { display: "none" } }}>
      <AccordionSummary
        expandIcon={<ExpandMoreIcon />}
        sx={{ px: 2, minHeight: 48 }}
      >
        <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
          Stage at Diagnosis by Cancer Type
        </Typography>
        <Typography
          variant="caption"
          color="text.secondary"
          sx={{ ml: 1.5, alignSelf: "center" }}
        >
          {typesWithData} cancer type{typesWithData !== 1 ? "s" : ""}
        </Typography>
      </AccordionSummary>

      <AccordionDetails sx={{ px: 2, pt: 0, pb: 2 }}>
        <MiniLegend />

        {rows.map((row, i) => (
          <Box
            key={row.label}
            sx={{
              borderTop: i > 0 ? "1px solid" : "none",
              borderColor: "divider",
            }}
          >
            <CancerTypeRow row={row} />
          </Box>
        ))}
      </AccordionDetails>
    </Accordion>
  );
}
