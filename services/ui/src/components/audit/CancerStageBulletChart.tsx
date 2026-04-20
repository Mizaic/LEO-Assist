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
 * Cancer Stage at Diagnosis -- segmented bullet chart.
 *
 * One 100%-wide track split into three colour bands:
 *
 *   |===== GREEN (early%) ======|=== ORANGE (late%) ===|.. GREY (unstaged) ..|
 *                                ^ 2018 national       ^ Eng 24/25  ^ LTP
 *
 * Reference ticks sit at their % position along the "early" axis:
 *   Brown  -- 2018 NCDA national early-stage baseline
 *   Cyan   -- England 2024/25 (58.7%, all cancers)
 *   Blue dashed -- NHS Long Term Plan 2028 target (75%)
 */

import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import MuiLink from "@mui/material/Link";
import Tooltip from "@mui/material/Tooltip";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";

// -- Published reference values ----------------------------------------------

/** NHS England early-stage rate 2024/25 (stages 1+2, all tumours). */
const NATIONAL_2024_25 = 58.7;

/** NHS Long Term Plan 2028 target: 75% at stages 1 and 2. */
const LTP_TARGET = 75;

// -- Colours -----------------------------------------------------------------

const C_EARLY   = "#16A34A";   // green-600
const C_LATE    = "#EA580C";   // orange-600
const C_GREY    = "#CBD5E1";   // slate-300 (unstaged)
const C_BENCH18 = "#92400E";   // amber-900 (2018 NCDA)
const C_NAT24   = "#0E7490";   // cyan-700  (England 24/25)
const C_LTP     = "#1D4ED8";   // blue-700  (NHS LTP)

const TRACK_H  = 24;   // px
const TICK_EXT = 8;    // px the tick extends above/below the track

// -- Tick mark (vertical reference line) ------------------------------------

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
            width: dashed ? "1px" : "2.5px",
            height: TRACK_H + TICK_EXT * 2,
            bgcolor: dashed ? "transparent" : color,
            borderLeft: dashed ? `2.5px dashed ${color}` : "none",
            borderRadius: dashed ? 0 : "2px",
          }}
        />
        <Box sx={{ textAlign: "center", mt: 0.5 }}>
          <Typography
            component="div"
            sx={{ fontSize: "0.62rem", fontWeight: 700, color, lineHeight: 1.2, whiteSpace: "nowrap" }}
          >
            {label}
          </Typography>
          <Typography
            component="div"
            sx={{ fontSize: "0.58rem", color: "text.disabled", lineHeight: 1.2, whiteSpace: "nowrap" }}
          >
            {sublabel}
          </Typography>
        </Box>
      </Box>
    </Tooltip>
  );
}

// -- Delta chip -------------------------------------------------------------

interface DeltaChipProps {
  refValue: number;
  current: number | null;
}

function DeltaChip({ refValue, current }: DeltaChipProps) {
  if (current == null) return null;
  const diff = Math.round((current - refValue) * 10) / 10;
  if (diff === 0) return null;
  return (
    <Typography
      component="span"
      sx={{ fontSize: "0.68rem", fontWeight: 700, color: diff > 0 ? "success.main" : "error.main", ml: 0.5 }}
    >
      {diff > 0 ? `+${diff}` : diff}pp
    </Typography>
  );
}

// -- Legend -----------------------------------------------------------------

function Legend() {
  return (
    <Box sx={{ display: "flex", flexWrap: "wrap", gap: 2, mb: 1 }}>
      {[
        { color: C_EARLY,   label: "Early (stage 0-2)",    dash: false },
        { color: C_LATE,    label: "Late (stage 3-4)",      dash: false },
        { color: C_GREY,    label: "Not staged / unknown",  dash: false },
        { color: C_BENCH18, label: "2018 NCDA baseline",    dash: false },
        { color: C_NAT24,   label: "England 2024/25",       dash: false },
        { color: C_LTP,     label: "NHS LTP target (75%)",  dash: true  },
      ].map(({ color, label, dash }) => (
        <Box key={label} sx={{ display: "flex", alignItems: "center", gap: 0.75 }}>
          {dash ? (
            <Box sx={{ width: 16, height: 2, bgcolor: color, borderRadius: 1 }} />
          ) : (
            <Box sx={{ width: 10, height: 10, borderRadius: "2px", bgcolor: color }} />
          )}
          <Typography variant="caption" sx={{ fontSize: "0.72rem", color: "text.secondary" }}>
            {label}
          </Typography>
        </Box>
      ))}
    </Box>
  );
}

// -- Public component --------------------------------------------------------

export interface CancerStageBulletChartProps {
  earlyPct: number | null;
  earlyN: number | null;
  latePct: number | null;
  lateN: number | null;
  /** Total patients in scope (used to compute unstaged count). */
  totalN: number | null;
  /** 2018 NCDA benchmark: practice when org selected, national otherwise. */
  benchmark2018Early: number | null;
  orgSelected: boolean;
}

export default function CancerStageBulletChart({
  earlyPct,
  earlyN,
  latePct,
  lateN,
  totalN,
  benchmark2018Early,
  orgSelected,
}: CancerStageBulletChartProps) {
  const early = earlyPct ?? 0;
  const late  = latePct ?? 0;
  const unstaged = Math.max(0, 100 - early - late);
  const hasData = earlyPct != null || latePct != null;

  const bench18Label = orgSelected ? "Practice 2018" : "National 2018";

  const unstagedN =
    totalN != null && earlyN != null && lateN != null
      ? Math.max(0, totalN - earlyN - lateN)
      : null;

  return (
    <Box>
      {/* Legend + source link row */}
      <Box
        sx={{
          display: "flex",
          alignItems: "flex-start",
          justifyContent: "space-between",
          flexWrap: "wrap",
          gap: 1,
          mb: 1.5,
        }}
      >
        <Legend />
        <Tooltip
          title="England 2024/25: NHS England Cancer Early Diagnosis Statistics. LTP target: NHS Long Term Plan 2019. 2018 baseline: NCDA."
          placement="top"
          arrow
        >
          <MuiLink
            href="https://www.cancerdata.nhs.uk/incidence_and_mortality"
            target="_blank"
            rel="noopener noreferrer"
            aria-label="Source: NHS cancer data"
            sx={{
              display: "flex",
              alignItems: "center",
              gap: 0.5,
              color: "text.secondary",
              fontSize: "0.72rem",
              textDecoration: "none",
              flexShrink: 0,
            }}
          >
            <InfoOutlinedIcon sx={{ fontSize: 14 }} />
            Sources
          </MuiLink>
        </Tooltip>
      </Box>

      {/* Segmented track area -- extra bottom padding for tick labels */}
      <Box sx={{ position: "relative", height: TRACK_H + TICK_EXT + 40, mb: 0.5 }}>

        {/* Grey background (100%) */}
        <Box
          sx={{
            position: "absolute",
            top: TICK_EXT,
            left: 0,
            right: 0,
            height: TRACK_H,
            bgcolor: C_GREY,
            borderRadius: "6px",
          }}
        />

        {/* Orange late segment (right of early) */}
        {hasData && late > 0 && (
          <Box
            sx={{
              position: "absolute",
              top: TICK_EXT,
              left: `${early}%`,
              width: `${late}%`,
              height: TRACK_H,
              bgcolor: C_LATE,
              opacity: 0.85,
              transition: "width 0.55s ease, left 0.55s ease",
            }}
          />
        )}

        {/* Green early segment (left) */}
        {hasData && early > 0 && (
          <Box
            sx={{
              position: "absolute",
              top: TICK_EXT,
              left: 0,
              width: `${early}%`,
              height: TRACK_H,
              bgcolor: C_EARLY,
              borderRadius: `6px ${late > 0 ? "0 0" : "6px 6px"} 6px`,
              opacity: 0.85,
              transition: "width 0.55s ease",
              zIndex: 1,
            }}
          />
        )}

        {/* Reference ticks (all on the early axis) */}
        {benchmark2018Early != null && (
          <Tick
            pct={benchmark2018Early}
            color={C_BENCH18}
            label={`${benchmark2018Early}%`}
            sublabel={bench18Label}
            tip={`2018 NCDA national: ${benchmark2018Early}% diagnosed early (stage 1 or 2)`}
          />
        )}

        <Tick
          pct={NATIONAL_2024_25}
          color={C_NAT24}
          label={`${NATIONAL_2024_25}%`}
          sublabel="Eng 24/25"
          tip={`England 2024/25: ${NATIONAL_2024_25}% of all cancers diagnosed early (stages 1+2). Source: NHS England.`}
        />

        <Tick
          pct={LTP_TARGET}
          color={C_LTP}
          label={`${LTP_TARGET}%`}
          sublabel="LTP target"
          dashed
          tip={`NHS Long Term Plan 2028 target: ${LTP_TARGET}% of cancers diagnosed at stage 1 or 2`}
        />
      </Box>

      {/* Stat row */}
      <Box
        sx={{
          display: "flex",
          flexWrap: "wrap",
          gap: 3,
          mt: 0.5,
          alignItems: "baseline",
        }}
      >
        <Box>
          <Typography
            component="span"
            sx={{ fontWeight: 800, fontSize: "1.25rem", color: C_EARLY, lineHeight: 1 }}
          >
            {earlyPct != null ? `${Math.round(early)}%` : "--"}
          </Typography>
          <Typography component="span" variant="caption" color="text.secondary" sx={{ ml: 0.75 }}>
            early{earlyN != null ? ` (n=${earlyN})` : ""}
          </Typography>
        </Box>

        <Box>
          <Typography
            component="span"
            sx={{ fontWeight: 800, fontSize: "1.25rem", color: C_LATE, lineHeight: 1 }}
          >
            {latePct != null ? `${Math.round(late)}%` : "--"}
          </Typography>
          <Typography component="span" variant="caption" color="text.secondary" sx={{ ml: 0.75 }}>
            late{lateN != null ? ` (n=${lateN})` : ""}
          </Typography>
        </Box>

        {unstaged > 0.5 && (
          <Box>
            <Typography
              component="span"
              sx={{ fontWeight: 700, fontSize: "1.05rem", color: "text.disabled", lineHeight: 1 }}
            >
              {Math.round(unstaged)}%
            </Typography>
            <Typography component="span" variant="caption" color="text.disabled" sx={{ ml: 0.75 }}>
              not staged{unstagedN != null ? ` (n=${unstagedN})` : ""}
            </Typography>
          </Box>
        )}
      </Box>

      {/* Comparison row vs benchmarks */}
      <Box sx={{ display: "flex", flexWrap: "wrap", gap: 2, mt: 1.25 }}>
        {benchmark2018Early != null && (
          <Box sx={{ display: "flex", alignItems: "center", gap: 0.25 }}>
            <Box sx={{ width: 8, height: 8, borderRadius: "50%", bgcolor: C_BENCH18, flexShrink: 0 }} />
            <Typography variant="caption" color="text.secondary" sx={{ fontSize: "0.72rem" }}>
              vs 2018: {benchmark2018Early}%
            </Typography>
            <DeltaChip refValue={benchmark2018Early} current={earlyPct} />
          </Box>
        )}

        <Box sx={{ display: "flex", alignItems: "center", gap: 0.25 }}>
          <Box sx={{ width: 8, height: 8, borderRadius: "50%", bgcolor: C_NAT24, flexShrink: 0 }} />
          <Typography variant="caption" color="text.secondary" sx={{ fontSize: "0.72rem" }}>
            vs England 24/25: {NATIONAL_2024_25}%
          </Typography>
          <DeltaChip refValue={NATIONAL_2024_25} current={earlyPct} />
        </Box>

        <Box sx={{ display: "flex", alignItems: "center", gap: 0.25 }}>
          <Box sx={{ width: 12, height: 2, bgcolor: C_LTP, flexShrink: 0, borderRadius: 1 }} />
          <Typography variant="caption" color="text.secondary" sx={{ fontSize: "0.72rem" }}>
            vs LTP target: {LTP_TARGET}%
          </Typography>
          <DeltaChip refValue={LTP_TARGET} current={earlyPct} />
        </Box>
      </Box>
    </Box>
  );
}
