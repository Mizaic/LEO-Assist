/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-4DADBA3F
 *   DI: DI-87D92943
 *   Risk: R-27CCE37C
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-4DADBA3F")
 */
"use client";

/**
 * Single-year ethnicity card for the Demographics evolution view.
 *
 * Mirrors CancerStageYearCard's segmented-bar pattern: a horizontal track
 * split into:
 *   |== green % white ==|.. grey % non-white ..|
 * with an n-badge in the header and a dashed 2018 NCDA reference tick at
 * the published baseline white-ethnicity % on live cards (R-27CCE37C
 * anchor; R-05B6DDA7 sparse-data anchor for the n badge).
 *
 * Baseline mode (isBaseline) renders only the green white-ethnicity
 * segment, with the rest grey-hatched, captioned that the 2018 NCDA
 * baseline only publishes white-ethnicity %.
 *
 * Sparse-data states:
 *   loading                   -> "Loading..."
 *   live with totalN == 0     -> "No data yet for {year}"
 *   live with 0 < n < 20      -> "Limited sample"
 *   live with whitePct == null
 *     -> "Ethnicity not yet linked"
 */

import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Typography from "@mui/material/Typography";

const C_WHITE = "#16A34A";
const C_GREY = "#CBD5E1";
const C_BENCH18 = "#92400E";

const TRACK_H = 22;
const TICK_EXT = 6;

const LOW_SAMPLE_THRESHOLD = 20;

export interface EthnicityYearCardProps {
  yearLabel: string;
  whitePct: number | null;
  totalN: number;
  /** Published 2018 NCDA white-ethnicity % drawn as a dashed reference tick on live cards. */
  baseline2018White: number | null;
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

export default function EthnicityYearCard({
  yearLabel,
  whitePct,
  totalN,
  baseline2018White,
  loading = false,
  isBaseline = false,
}: EthnicityYearCardProps) {
  const white = whitePct ?? 0;
  const nonWhite = whitePct == null ? 0 : Math.max(0, 100 - white);

  const hasData = !loading && totalN > 0 && whitePct != null;
  const isEmpty = !loading && !isBaseline && totalN === 0;
  const isLowSample =
    !loading &&
    !isBaseline &&
    totalN > 0 &&
    totalN < LOW_SAMPLE_THRESHOLD;
  const isUnlinked =
    !loading && !isBaseline && totalN > 0 && whitePct == null;

  const headerCaption = loading
    ? "Loading..."
    : isBaseline
      ? "Baseline"
      : isEmpty
        ? "No data yet"
        : isUnlinked
          ? "Ethnicity not linked"
          : isLowSample
            ? "Limited sample"
            : "Live";

  const showBaselineTick =
    !isBaseline && baseline2018White != null && hasData;

  const showWhiteHeroOnly = isBaseline && whitePct != null;

  return (
    <Box
      role="group"
      aria-label={`Ethnicity card for ${yearLabel}`}
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

        {!isBaseline && hasData && white > 0 && (
          <Box
            sx={{
              position: "absolute",
              top: TICK_EXT,
              left: 0,
              width: `${white}%`,
              height: TRACK_H,
              bgcolor: C_WHITE,
              borderRadius: "5px 0 0 5px",
              opacity: 0.85,
              transition: "width 0.4s ease",
              zIndex: 1,
            }}
          />
        )}

        {showWhiteHeroOnly && (
          <Box
            sx={{
              position: "absolute",
              top: TICK_EXT,
              left: 0,
              width: `${white}%`,
              height: TRACK_H,
              bgcolor: C_WHITE,
              borderRadius: "5px",
              opacity: 0.85,
              zIndex: 1,
            }}
          />
        )}

        {showBaselineTick && (
          <BaselineTick pct={baseline2018White as number} />
        )}
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
              color: C_WHITE,
              lineHeight: 1,
            }}
          >
            {whitePct != null ? `${Math.round(white)}%` : "--"}
          </Typography>
          <Typography
            component="span"
            variant="caption"
            color="text.secondary"
            sx={{ ml: 0.5 }}
          >
            white
          </Typography>
        </Box>
        {!isBaseline && hasData && nonWhite > 0.5 && (
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
              {Math.round(nonWhite)}%
            </Typography>
            <Typography
              component="span"
              variant="caption"
              color="text.disabled"
              sx={{ ml: 0.5 }}
            >
              non-white
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
          2018 NCDA baseline publishes white ethnicity % only.
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

      {isUnlinked && (
        <Typography
          variant="caption"
          sx={{
            color: "text.secondary",
            fontStyle: "italic",
            fontSize: "0.72rem",
            display: "block",
          }}
        >
          Ethnicity not yet linked to patient records for {yearLabel}.
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

      <Typography
        variant="caption"
        sx={{
          color: "text.secondary",
          fontSize: "0.68rem",
          display: "block",
          mt: "auto",
        }}
      >
        Non-white categories (Asian, Black, Mixed, Other) are aggregated for
        this card -- the per-cancer-type drill-down is out of scope this
        iteration.
      </Typography>
    </Box>
  );
}
