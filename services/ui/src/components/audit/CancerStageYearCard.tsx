/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-EF5F7455
 *   DI: DI-38AE4EA1
 *   Risk: R-E00F9C3C
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-EF5F7455")
 */
"use client";

/**
 * Single-year card for the Cancer Stage at Diagnosis evolution view.
 *
 * Live mode renders a horizontal segmented bar split into:
 *   |== green early ==|== orange late ==|.. grey unstaged ..|
 * with an n-badge in the header and a dashed 2018 reference tick
 * positioned at the published baseline early-stage % (R-E00F9C3C anchor).
 *
 * Baseline mode (isBaseline) renders only the green early-stage segment,
 * with the rest grey-hatched, captioned that the 2018 NCDA baseline does
 * not publish late% or unstaged%. This makes the baseline visually
 * distinct from live cards so it is never misread as a full stage split.
 *
 * Sparse-data states (R-E00F9C3C mitigations):
 *   loading           -> caption "Loading..."
 *   live with n == 0  -> "No data yet for {year}"
 *   live with 0<n<20  -> "Limited sample - treat as indicative, not representative."
 *   coverage_pct < 50 -> "Stage recorded for {coverage_pct}% of cases"
 */

import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Typography from "@mui/material/Typography";

const C_EARLY = "#16A34A";
const C_LATE = "#EA580C";
const C_GREY = "#CBD5E1";
const C_BENCH18 = "#92400E";

const TRACK_H = 22;
const TICK_EXT = 6;

const LOW_SAMPLE_THRESHOLD = 20;
const LOW_COVERAGE_THRESHOLD = 50;

export interface CancerStageYearCardProps {
  yearLabel: string;
  earlyPct: number | null;
  latePct: number | null;
  totalN: number;
  coveragePct: number | null;
  /** Published 2018 NCDA early-stage % drawn as a dashed reference tick on live cards. */
  baseline2018Early: number | null;
  loading?: boolean;
  isBaseline?: boolean;
}

interface BaselineTickProps {
  pct: number;
}

function BaselineTick({ pct }: BaselineTickProps) {
  const x = Math.min(Math.max(pct, 0), 100);
  return (
    <Box
      aria-hidden="true"
      sx={{
        position: "absolute",
        left: `${x}%`,
        top: -TICK_EXT,
        transform: "translateX(-50%)",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        zIndex: 2,
        pointerEvents: "none",
      }}
    >
      <Box
        sx={{
          width: 0,
          height: TRACK_H + TICK_EXT * 2,
          borderLeft: `2px dashed ${C_BENCH18}`,
        }}
      />
      <Typography
        component="div"
        sx={{
          fontSize: "0.58rem",
          fontWeight: 700,
          color: C_BENCH18,
          lineHeight: 1.1,
          mt: 0.25,
          whiteSpace: "nowrap",
        }}
      >
        2018 {pct}%
      </Typography>
    </Box>
  );
}

export default function CancerStageYearCard({
  yearLabel,
  earlyPct,
  latePct,
  totalN,
  coveragePct,
  baseline2018Early,
  loading = false,
  isBaseline = false,
}: CancerStageYearCardProps) {
  const early = earlyPct ?? 0;
  const late = latePct ?? 0;
  const unstaged = Math.max(0, 100 - early - late);

  const hasData = !loading && totalN > 0 && (earlyPct != null || latePct != null);
  const isEmpty = !loading && !isBaseline && totalN === 0;
  const isLowSample =
    !loading &&
    !isBaseline &&
    totalN > 0 &&
    totalN < LOW_SAMPLE_THRESHOLD;
  const isLowCoverage =
    !loading &&
    !isBaseline &&
    coveragePct != null &&
    coveragePct < LOW_COVERAGE_THRESHOLD &&
    totalN > 0;

  const headerCaption = loading
    ? "Loading..."
    : isBaseline
      ? "Baseline"
      : isEmpty
        ? "No data yet"
        : isLowSample
          ? "Limited sample"
          : "Live";

  const showBaselineTick =
    !isBaseline && baseline2018Early != null && hasData;

  const showEarlyHeroOnly = isBaseline && earlyPct != null;

  return (
    <Box
      role="group"
      aria-label={`Cancer stage card for ${yearLabel}`}
      sx={{
        display: "flex",
        flexDirection: "column",
        border: "1px solid",
        borderColor: "divider",
        borderRadius: 2,
        p: 1.75,
        bgcolor: "background.paper",
        height: "100%",
        gap: 1,
      }}
    >
      <Box
        sx={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 1,
        }}
      >
        <Box sx={{ minWidth: 0 }}>
          <Typography
            component="h3"
            sx={{ fontSize: "0.95rem", fontWeight: 700, color: "text.primary" }}
          >
            {yearLabel}
          </Typography>
          <Typography
            variant="caption"
            sx={{ color: "text.secondary", fontSize: "0.7rem" }}
          >
            {headerCaption}
          </Typography>
        </Box>
        {!isBaseline && (
          <Chip
            label={`n = ${totalN}`}
            size="small"
            variant="outlined"
            sx={{ fontWeight: 600, fontSize: "0.72rem" }}
            aria-label={`Sample size for ${yearLabel}: ${totalN} confirmed cancer cases`}
          />
        )}
        {isBaseline && (
          <Chip
            label="2018 NCDA"
            size="small"
            sx={{
              fontWeight: 600,
              fontSize: "0.7rem",
              bgcolor: "#FEF3C7",
              color: C_BENCH18,
              border: `1px solid ${C_BENCH18}33`,
            }}
          />
        )}
      </Box>

      <Box sx={{ position: "relative", height: TRACK_H + TICK_EXT + 22 }}>
        <Box
          sx={{
            position: "absolute",
            top: TICK_EXT,
            left: 0,
            right: 0,
            height: TRACK_H,
            bgcolor: C_GREY,
            borderRadius: "5px",
            backgroundImage: isBaseline
              ? `repeating-linear-gradient(45deg, ${C_GREY} 0, ${C_GREY} 4px, #E2E8F0 4px, #E2E8F0 8px)`
              : undefined,
          }}
        />

        {!isBaseline && hasData && late > 0 && (
          <Box
            sx={{
              position: "absolute",
              top: TICK_EXT,
              left: `${early}%`,
              width: `${late}%`,
              height: TRACK_H,
              bgcolor: C_LATE,
              opacity: 0.85,
              transition: "width 0.4s ease, left 0.4s ease",
            }}
          />
        )}

        {!isBaseline && hasData && early > 0 && (
          <Box
            sx={{
              position: "absolute",
              top: TICK_EXT,
              left: 0,
              width: `${early}%`,
              height: TRACK_H,
              bgcolor: C_EARLY,
              borderRadius: "5px 0 0 5px",
              opacity: 0.85,
              transition: "width 0.4s ease",
              zIndex: 1,
            }}
          />
        )}

        {showEarlyHeroOnly && (
          <Box
            sx={{
              position: "absolute",
              top: TICK_EXT,
              left: 0,
              width: `${early}%`,
              height: TRACK_H,
              bgcolor: C_EARLY,
              borderRadius: "5px",
              opacity: 0.85,
              zIndex: 1,
            }}
          />
        )}

        {showBaselineTick && <BaselineTick pct={baseline2018Early as number} />}
      </Box>

      <Box
        sx={{
          display: "flex",
          flexWrap: "wrap",
          gap: 1.5,
          alignItems: "baseline",
          mt: 0.25,
        }}
      >
        <Box>
          <Typography
            component="span"
            sx={{
              fontWeight: 800,
              fontSize: "1.4rem",
              color: C_EARLY,
              lineHeight: 1,
            }}
          >
            {earlyPct != null ? `${Math.round(early)}%` : "--"}
          </Typography>
          <Typography
            component="span"
            variant="caption"
            color="text.secondary"
            sx={{ ml: 0.5 }}
          >
            early
          </Typography>
        </Box>
        {!isBaseline && (
          <Box>
            <Typography
              component="span"
              sx={{
                fontWeight: 700,
                fontSize: "1rem",
                color: C_LATE,
                lineHeight: 1,
              }}
            >
              {latePct != null ? `${Math.round(late)}%` : "--"}
            </Typography>
            <Typography
              component="span"
              variant="caption"
              color="text.secondary"
              sx={{ ml: 0.5 }}
            >
              late
            </Typography>
          </Box>
        )}
        {!isBaseline && hasData && unstaged > 0.5 && (
          <Box>
            <Typography
              component="span"
              sx={{
                fontWeight: 600,
                fontSize: "0.95rem",
                color: "text.disabled",
                lineHeight: 1,
              }}
            >
              {Math.round(unstaged)}%
            </Typography>
            <Typography
              component="span"
              variant="caption"
              color="text.disabled"
              sx={{ ml: 0.5 }}
            >
              not staged
            </Typography>
          </Box>
        )}
      </Box>

      {isBaseline && (
        <Typography
          variant="caption"
          sx={{
            color: "text.secondary",
            fontStyle: "italic",
            fontSize: "0.7rem",
            display: "block",
          }}
        >
          Late and unstaged are not published in the 2018 NCDA baseline.
        </Typography>
      )}

      {isEmpty && (
        <Typography
          variant="caption"
          sx={{
            color: "text.secondary",
            fontStyle: "italic",
            fontSize: "0.72rem",
            display: "block",
          }}
        >
          No data yet for {yearLabel}.
        </Typography>
      )}

      {isLowSample && (
        <Typography
          variant="caption"
          sx={{
            color: "text.secondary",
            fontStyle: "italic",
            fontSize: "0.7rem",
            display: "block",
          }}
        >
          Limited sample (n = {totalN}) - treat as indicative, not
          representative.
        </Typography>
      )}

      {isLowCoverage && coveragePct != null && (
        <Typography
          variant="caption"
          sx={{
            color: "text.secondary",
            fontSize: "0.7rem",
            display: "block",
          }}
        >
          Stage recorded for {Math.round(coveragePct)}% of cases - the rest are
          unstaged.
        </Typography>
      )}
    </Box>
  );
}
