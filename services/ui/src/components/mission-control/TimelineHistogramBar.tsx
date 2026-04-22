/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-5312F884, DO-17AF3E5E
 *   DI: DI-AA1F5F5B, DI-8ECE2DAE
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-5312F884")
 */
"use client";

import { type KeyboardEvent } from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { motion as fm } from "framer-motion";
import type { TimelineBin } from "./timelineBins";
import { shortDate } from "./encounterTextUtils";

// Stacked-bar histogram primitive used by EncounterTimelineScrubber.
// Pure presentation: no state, no observers, no data-fetching.
//
// Design Controls: UN-LEO-AI-077, DI-LEO-AI-179, DO-LEO-AI-178,
// R-LEO-AI-174, VT-LEO-AI-173.

const COLOR_LINKED = "#2563eb";
const COLOR_OTHER = "#cbd5e1";
const COLOR_OTHER_HOVER = "#94a3b8";
const COLOR_ACTIVE_RING = "#1d4ed8";
// Amber outline used when free-text search has matches inside this
// bin. Mirrors the amber palette of milestone markers so the two
// overlays feel like the same family.
const COLOR_SEARCH_MATCH_RING = "#d97706";
const SEARCH_DIMMED_OPACITY = 0.25;
// Emerald underline drawn along the bottom edge of any bin that
// contains at least one coded encounter (coded_count > 0). Opacity
// is scaled to the coded fraction so a fully-coded month is solid
// and a partially-coded month is faint, but always visible above a
// minimum so single-coded bins are not lost. DI-8ECE2DAE.
const COLOR_CODED_UNDERLINE = "#059669";
const CODED_UNDERLINE_MIN_OPACITY = 0.25;
const CODED_UNDERLINE_HEIGHT_PX = 3;

function codedUnderlineOpacity(codedFraction: number): number {
  if (!Number.isFinite(codedFraction) || codedFraction <= 0) return 0;
  return Math.max(CODED_UNDERLINE_MIN_OPACITY, Math.min(1, codedFraction));
}

export interface BarRect {
  bin: TimelineBin;
  centerPct: number;
  widthPct: number;
}

function ariaLabelForBin(bin: TimelineBin, searchMatchCount = 0): string {
  const start = shortDate(new Date(bin.startMs).toISOString());
  const end = shortDate(new Date(bin.endMs - 1).toISOString());
  const linkedPart =
    bin.linked > 0 ? ` (${bin.linked} linked to focused episode)` : "";
  const noun = bin.total === 1 ? "encounter" : "encounters";
  const matchPart =
    searchMatchCount > 0 ? `, ${searchMatchCount} match search` : "";
  const codedPart =
    bin.codedCount > 0 ? `, ${bin.codedCount} of ${bin.total} coded` : "";
  return `Bin ${bin.label}, ${bin.total} ${noun}${linkedPart}${codedPart}${matchPart}, from ${start} to ${end}`;
}

interface HoverPreviewProps {
  bar: BarRect;
  trackHeight: number;
}

export function HoverPreview({ bar, trackHeight }: HoverPreviewProps) {
  const start = shortDate(new Date(bar.bin.startMs).toISOString());
  const end = shortDate(new Date(bar.bin.endMs - 1).toISOString());
  return (
    <fm.div
      key={`preview-${bar.bin.label}`}
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: 4 }}
      transition={{ duration: 0.15, ease: "easeOut" }}
      style={{
        position: "absolute",
        bottom: trackHeight - 4,
        left: `${bar.centerPct}%`,
        transform: "translateX(-50%)",
        background: "white",
        border: "1px solid #e2e8f0",
        borderRadius: 8,
        boxShadow: "0 6px 18px rgba(15, 23, 42, 0.10)",
        padding: "8px 10px",
        minWidth: 180,
        maxWidth: 260,
        zIndex: 5,
        pointerEvents: "none",
      }}
    >
      <Typography
        variant="caption"
        sx={{ display: "block", fontWeight: 700, color: "#0f172a" }}
      >
        {bar.bin.label}
      </Typography>
      <Typography
        variant="caption"
        sx={{ display: "block", color: "#475569", mb: 0.25 }}
      >
        {bar.bin.total} {bar.bin.total === 1 ? "encounter" : "encounters"}
        {bar.bin.linked > 0 ? ` - ${bar.bin.linked} linked` : ""}
      </Typography>
      {bar.bin.codedCount > 0 && (
        <Typography
          data-testid="timeline-coded-hover-line"
          variant="caption"
          sx={{
            display: "block",
            color: COLOR_CODED_UNDERLINE,
            fontWeight: 600,
            mb: 0.25,
          }}
        >
          {bar.bin.codedCount} of {bar.bin.total} coded
        </Typography>
      )}
      <Typography
        variant="caption"
        sx={{ display: "block", color: "#94a3b8", fontSize: "0.66rem" }}
      >
        {start} - {end}
      </Typography>
    </fm.div>
  );
}

interface HistogramBarProps {
  bar: BarRect;
  isActive: boolean;
  isHovered: boolean;
  isOutOfFocus: boolean;
  maxTotal: number;
  hoverDuration: number;
  // Free-text search overlay state. When `searchActive` is true the
  // bar dims to SEARCH_DIMMED_OPACITY unless `hasSearchMatch` is
  // also true, in which case the bar keeps full opacity and grows an
  // amber outline so the reviewer can see at a glance which date
  // bins contain hits.
  searchActive?: boolean;
  hasSearchMatch?: boolean;
  searchMatchCount?: number;
  onActivate: () => void;
  onArrow: (direction: -1 | 1) => void;
  onHoverChange: (hovered: boolean) => void;
}

export default function HistogramBar({
  bar,
  isActive,
  isHovered,
  isOutOfFocus,
  maxTotal,
  hoverDuration,
  searchActive = false,
  hasSearchMatch = false,
  searchMatchCount = 0,
  onActivate,
  onArrow,
  onHoverChange,
}: HistogramBarProps) {
  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onActivate();
      return;
    }
    if (event.key === "ArrowLeft") {
      event.preventDefault();
      onArrow(-1);
      return;
    }
    if (event.key === "ArrowRight") {
      event.preventDefault();
      onArrow(1);
    }
  };
  const totalRatio = maxTotal > 0 ? bar.bin.total / maxTotal : 0;
  const totalHeightPct = bar.bin.total === 0 ? 0 : Math.max(8, totalRatio * 100);
  const linkedShare = bar.bin.total > 0 ? bar.bin.linked / bar.bin.total : 0;
  const linkedHeightPct = totalHeightPct * linkedShare;
  const otherHeightPct = totalHeightPct - linkedHeightPct;
  // When a free-text search is active, dim non-matching bars so the
  // matching bars pop. Out-of-focus (zoom) dimming wins so the
  // reviewer always sees the brush window.
  const dimmedBySearch = searchActive && !hasSearchMatch;
  const baseOpacity = isOutOfFocus
    ? 0.35
    : dimmedBySearch
      ? SEARCH_DIMMED_OPACITY
      : 1;
  return (
    <Box
      role="button"
      tabIndex={bar.bin.total > 0 ? 0 : -1}
      aria-label={ariaLabelForBin(bar.bin, searchMatchCount)}
      aria-pressed={isActive}
      data-bin-label={bar.bin.label}
      data-total-count={bar.bin.total}
      data-linked-count={bar.bin.linked}
      data-other-count={bar.bin.other}
      data-active={isActive ? "true" : "false"}
      data-in-focus={isOutOfFocus ? "false" : "true"}
      data-search-active={searchActive ? "true" : "false"}
      data-search-match={hasSearchMatch ? "true" : "false"}
      data-search-match-count={searchMatchCount}
      data-coded-count={bar.bin.codedCount}
      data-coded-fraction={bar.bin.codedFraction.toFixed(3)}
      onClick={() => bar.bin.total > 0 && onActivate()}
      onKeyDown={handleKeyDown}
      onMouseEnter={() => onHoverChange(true)}
      onMouseLeave={() => onHoverChange(false)}
      onFocus={() => onHoverChange(true)}
      onBlur={() => onHoverChange(false)}
      sx={{
        position: "absolute",
        bottom: 0,
        height: "100%",
        left: `calc(${bar.centerPct}% - ${bar.widthPct / 2}%)`,
        width: `${bar.widthPct}%`,
        display: "flex",
        flexDirection: "column",
        justifyContent: "flex-end",
        cursor: bar.bin.total > 0 ? "pointer" : "default",
        outline: "none",
        "&:focus-visible": {
          background: "rgba(37, 99, 235, 0.08)",
          borderRadius: 4,
        },
      }}
    >
      <fm.div
        whileHover={{ y: -1 }}
        transition={{ duration: hoverDuration / 1000, ease: "easeOut" }}
        style={{
          position: "relative",
          width: "78%",
          marginLeft: "11%",
          height: `${totalHeightPct}%`,
          minHeight: bar.bin.total > 0 ? 4 : 0,
          opacity: baseOpacity,
          transition: "opacity 0.15s ease-out",
        }}
      >
        {bar.bin.other > 0 && (
          <Box
            data-segment="other"
            sx={{
              position: "absolute",
              left: 0,
              right: 0,
              top: 0,
              height: `${(otherHeightPct / Math.max(0.001, totalHeightPct)) * 100}%`,
              bgcolor: isHovered ? COLOR_OTHER_HOVER : COLOR_OTHER,
              borderTopLeftRadius: 3,
              borderTopRightRadius: 3,
              transition: "background 0.15s ease-out",
            }}
          />
        )}
        {bar.bin.linked > 0 && (
          <Box
            data-segment="linked"
            sx={{
              position: "absolute",
              left: 0,
              right: 0,
              bottom: 0,
              height: `${(linkedHeightPct / Math.max(0.001, totalHeightPct)) * 100}%`,
              bgcolor: COLOR_LINKED,
              borderTopLeftRadius: bar.bin.other > 0 ? 0 : 3,
              borderTopRightRadius: bar.bin.other > 0 ? 0 : 3,
            }}
          />
        )}
        {searchActive && hasSearchMatch && (
          <Box
            data-testid="timeline-search-match-ring"
            aria-hidden="true"
            sx={{
              position: "absolute",
              inset: -2,
              border: `1.5px solid ${COLOR_SEARCH_MATCH_RING}`,
              borderRadius: "4px",
              boxShadow: `0 0 0 1px rgba(217, 119, 6, 0.18)`,
              pointerEvents: "none",
            }}
          />
        )}
        {isActive && (
          // NOTE: previously used framer-motion `layoutId="timeline-active-bin"`
          // for a shared-element transition between bars. The shared
          // layout animation could feed back into the React render
          // cycle when the active bin flipped rapidly (e.g. as the
          // IntersectionObserver above the encounter list updated
          // `visibleEncounterId`), producing
          // "Maximum update depth exceeded" inside `bars.map`.
          // A static ring is sufficient -- the active bar is already
          // visually distinct via colour and opacity.
          <Box
            data-testid="timeline-active-ring"
            aria-hidden="true"
            sx={{
              position: "absolute",
              inset: -3,
              border: `2px solid ${COLOR_ACTIVE_RING}`,
              borderRadius: "5px",
              pointerEvents: "none",
            }}
          />
        )}
      </fm.div>
      {bar.bin.total > 0 && bar.bin.codedCount > 0 && (
        // Bottom-edge coded-data indicator. Sits inside the bar root
        // (so it spans the column width) but outside the inner
        // motion.div (so its opacity stays decoupled from the
        // bar's height/dim animation). Anchored 1px above the axis
        // line so a fully-coded month reads as a solid emerald bar
        // hugging the timeline. DI-8ECE2DAE.
        <Box
          data-testid="timeline-coded-underline"
          aria-hidden="true"
          sx={{
            position: "absolute",
            left: "11%",
            width: "78%",
            bottom: 1,
            height: `${CODED_UNDERLINE_HEIGHT_PX}px`,
            bgcolor: COLOR_CODED_UNDERLINE,
            opacity: codedUnderlineOpacity(bar.bin.codedFraction),
            borderRadius: "2px",
            pointerEvents: "none",
          }}
        />
      )}
    </Box>
  );
}
