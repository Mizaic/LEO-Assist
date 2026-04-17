"use client";

import { useEffect, useMemo, useState } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Typography from "@mui/material/Typography";
import { AnimatePresence } from "framer-motion";
import { useMotion } from "@leo/design-system";
import {
  buildBins,
  buildDated,
  clampRange,
  pctBetween,
  pickGranularity,
  toTimestamp,
  type ScrubberEncounter,
  type TimelineBin,
} from "./timelineBins";
import TimelineBinPopover from "./TimelineBinPopover";
import TimelineRangeBrush from "./TimelineRangeBrush";
import HistogramBar, {
  HoverPreview,
  type BarRect,
} from "./TimelineHistogramBar";

// Sticky histogram timeline for the Mission Control patient detail
// Encounter text tab. Bars represent date bins (auto-granularity).
// Each bar is a stack of "linked-to-focused-episode" + "other"
// counts so the reviewer sees linked density vs total density at a
// glance. Hover/focus reveals a preview; click jumps directly when
// the bin contains one encounter, or opens a popover otherwise. A
// brush rail below the bars supports zoom; a "Reset zoom" button
// appears when zoomed in.
//
// Design Controls: UN-LEO-AI-077, DI-LEO-AI-179, DO-LEO-AI-178,
// R-LEO-AI-174, VT-LEO-AI-173.

export type { ScrubberEncounter } from "./timelineBins";

interface Props {
  encounters: ScrubberEncounter[];
  linkedEncounterIds: Set<string>;
  episodeFrom: string | null;
  episodeTo: string | null;
  activeEncounterId: string | null;
  onJumpToEncounter: (encounterId: string) => void;
  // Controlled visible range. When null, the scrubber shows the
  // patient's full history. When provided, the parent owns the zoom
  // state (so the encounter list below can be filtered to the same
  // window).
  visibleFromMs?: number | null;
  visibleToMs?: number | null;
  // Called whenever the user drags the brush. Pass nulls when the
  // user clicks "Reset zoom" so the parent can clear the filter.
  onVisibleRangeChange?: (fromMs: number | null, toMs: number | null) => void;
}

const MIN_ENCOUNTERS_FOR_SCRUBBER = 5;

const TRACK_HEIGHT = 64;
const COLOR_LINKED = "#2563eb";
const COLOR_OTHER = "#cbd5e1";
const COLOR_OTHER_HOVER = "#94a3b8";
const COLOR_AXIS = "#e2e8f0";
const COLOR_BAND = "rgba(37, 99, 235, 0.10)";
const COLOR_BAND_BORDER = "rgba(37, 99, 235, 0.28)";
const COLOR_ACTIVE_RING = "#1d4ed8";

interface BarRect {
  bin: TimelineBin;
  centerPct: number;
  widthPct: number;
}

function ariaLabelForBin(bin: TimelineBin): string {
  const start = shortDate(new Date(bin.startMs).toISOString());
  const end = shortDate(new Date(bin.endMs - 1).toISOString());
  const linkedPart = bin.linked > 0 ? ` (${bin.linked} linked to focused episode)` : "";
  return `Bin ${bin.label}, ${bin.total} ${bin.total === 1 ? "encounter" : "encounters"}${linkedPart}, from ${start} to ${end}`;
}

function HoverPreview({
  bar,
  trackHeight,
}: {
  bar: BarRect;
  trackHeight: number;
}) {
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
      <Typography variant="caption" sx={{ display: "block", fontWeight: 700, color: "#0f172a" }}>
        {bar.bin.label}
      </Typography>
      <Typography variant="caption" sx={{ display: "block", color: "#475569", mb: 0.25 }}>
        {bar.bin.total} {bar.bin.total === 1 ? "encounter" : "encounters"}
        {bar.bin.linked > 0 ? ` - ${bar.bin.linked} linked` : ""}
      </Typography>
      <Typography variant="caption" sx={{ display: "block", color: "#94a3b8", fontSize: "0.66rem" }}>
        {start} - {end}
      </Typography>
    </fm.div>
  );
}

interface BarProps {
  bar: BarRect;
  isActive: boolean;
  isHovered: boolean;
  isOutOfFocus: boolean;
  maxTotal: number;
  hoverDuration: number;
  onActivate: () => void;
  onArrow: (direction: -1 | 1) => void;
  onHoverChange: (hovered: boolean) => void;
}

function HistogramBar({
  bar,
  isActive,
  isHovered,
  isOutOfFocus,
  maxTotal,
  hoverDuration,
  onActivate,
  onArrow,
  onHoverChange,
}: BarProps) {
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
  return (
    <Box
      role="button"
      tabIndex={bar.bin.total > 0 ? 0 : -1}
      aria-label={ariaLabelForBin(bar.bin)}
      aria-pressed={isActive}
      data-bin-label={bar.bin.label}
      data-total-count={bar.bin.total}
      data-linked-count={bar.bin.linked}
      data-other-count={bar.bin.other}
      data-active={isActive ? "true" : "false"}
      data-in-focus={isOutOfFocus ? "false" : "true"}
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
          opacity: isOutOfFocus ? 0.35 : 1,
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
        {isActive && (
          <fm.div
            layoutId="timeline-active-bin"
            transition={{ type: "spring", stiffness: 320, damping: 28 }}
            style={{
              position: "absolute",
              inset: -3,
              border: `2px solid ${COLOR_ACTIVE_RING}`,
              borderRadius: 5,
              pointerEvents: "none",
            }}
          />
        )}
      </fm.div>
    </Box>
  );
}

function useStickyShadow(): boolean {
  const [stuck, setStuck] = useState(false);
  useEffect(() => {
    const onScroll = () => {
      const el = document.querySelector('[data-testid="encounter-timeline-scrubber"]');
      if (!el) return;
      const rect = el.getBoundingClientRect();
      setStuck(rect.top <= 1);
    };
    window.addEventListener("scroll", onScroll, true);
    onScroll();
    return () => window.removeEventListener("scroll", onScroll, true);
  }, []);
  return stuck;
}

function findActiveBinIndex(
  bins: TimelineBin[],
  activeEncounterId: string | null
): number {
  if (!activeEncounterId) return -1;
  return bins.findIndex((bin) =>
    bin.encounters.some((e) => String(e.enc.encounter_id) === activeEncounterId)
  );
}

interface OnArrowFromBinArgs {
  bins: TimelineBin[];
  activeEncounterId: string | null;
  direction: -1 | 1;
  onJump: (encounterId: string) => void;
}

function jumpFromBin({ bins, activeEncounterId, direction, onJump }: OnArrowFromBinArgs): void {
  const idx = findActiveBinIndex(bins, activeEncounterId);
  const start = idx >= 0 ? idx : 0;
  let next = start + direction;
  while (next >= 0 && next < bins.length) {
    if (bins[next].total > 0) {
      onJump(String(bins[next].encounters[0].enc.encounter_id));
      return;
    }
    next += direction;
  }
}

export default function EncounterTimelineScrubber({
  encounters,
  linkedEncounterIds,
  episodeFrom,
  episodeTo,
  activeEncounterId,
  onJumpToEncounter,
  visibleFromMs: visibleFromMsProp,
  visibleToMs: visibleToMsProp,
  onVisibleRangeChange,
}: Props) {
  const motionState = useMotion();
  const reducedMotion = motionState.reducedMotion;
  const hoverDuration = motionState.transitions.hover.duration;
  const stuck = useStickyShadow();
  const [hoverBinKey, setHoverBinKey] = useState<string | null>(null);
  const [popoverBinKey, setPopoverBinKey] = useState<string | null>(null);

  const dated = useMemo(
    () => buildDated(encounters, linkedEncounterIds),
    [encounters, linkedEncounterIds]
  );

  const fullMinMs = dated.length > 0 ? dated[0].ts : Number.NaN;
  const fullMaxMs = dated.length > 0 ? dated[dated.length - 1].ts : Number.NaN;

  const [internalZoom, setInternalZoom] = useState<{ fromMs: number; toMs: number } | null>(null);
  const isControlled = onVisibleRangeChange !== undefined;
  const zoom = isControlled
    ? visibleFromMsProp != null && visibleToMsProp != null
      ? { fromMs: visibleFromMsProp, toMs: visibleToMsProp }
      : null
    : internalZoom;

  useEffect(() => {
    if (isControlled) return;
    setInternalZoom(null);
    setPopoverBinKey(null);
    setHoverBinKey(null);
  }, [encounters.length, fullMinMs, fullMaxMs, isControlled]);

  const visibleFromMs = zoom?.fromMs ?? fullMinMs;
  const visibleToMs = zoom?.toMs ?? fullMaxMs;
  const isZoomed = Boolean(
    zoom && (zoom.fromMs > fullMinMs || zoom.toMs < fullMaxMs)
  );

  // The histogram is always rendered at full patient range with a
  // single, stable granularity. The brush below acts purely as a
  // focus-window filter: it draws a band over the bars to mark the
  // selected slice, dims out-of-focus bars, and the parent uses
  // [visibleFromMs, visibleToMs] to filter the encounter list.
  const granularity = useMemo(() => {
    if (!Number.isFinite(fullMinMs) || !Number.isFinite(fullMaxMs)) return "month" as const;
    return pickGranularity(Math.max(0, fullMaxMs - fullMinMs));
  }, [fullMinMs, fullMaxMs]);

  const bins = useMemo(
    () => buildBins(dated, fullMinMs, fullMaxMs, granularity),
    [dated, fullMinMs, fullMaxMs, granularity]
  );

  const maxTotal = useMemo(
    () => bins.reduce((acc, b) => Math.max(acc, b.total), 0),
    [bins]
  );

  const bars: BarRect[] = useMemo(() => {
    if (bins.length === 0) return [];
    const widthPct = 100 / bins.length;
    return bins.map((bin, idx) => ({
      bin,
      centerPct: widthPct * (idx + 0.5),
      widthPct,
    }));
  }, [bins]);

  const windowBand = useMemo(() => {
    if (bars.length === 0) return null;
    const fromTs = toTimestamp(episodeFrom);
    const toTs = toTimestamp(episodeTo);
    if (!Number.isFinite(fromTs) || !Number.isFinite(toTs)) return null;
    if (toTs < fullMinMs || fromTs > fullMaxMs) return null;
    const leftPct = pctBetween(Math.max(fromTs, fullMinMs), fullMinMs, fullMaxMs);
    const rightPct = pctBetween(Math.min(toTs, fullMaxMs), fullMinMs, fullMaxMs);
    return { leftPct, widthPct: Math.max(0.5, rightPct - leftPct) };
  }, [bars.length, fullMinMs, fullMaxMs, episodeFrom, episodeTo]);

  const focusBand = useMemo(() => {
    if (bars.length === 0 || !isZoomed) return null;
    const leftPct = pctBetween(visibleFromMs, fullMinMs, fullMaxMs);
    const rightPct = pctBetween(visibleToMs, fullMinMs, fullMaxMs);
    return { leftPct, widthPct: Math.max(0.5, rightPct - leftPct) };
  }, [bars.length, isZoomed, visibleFromMs, visibleToMs, fullMinMs, fullMaxMs]);

  if (encounters.length < MIN_ENCOUNTERS_FOR_SCRUBBER || bars.length === 0) {
    return null;
  }

  const handleBarActivate = (bar: BarRect) => {
    if (bar.bin.total === 0) return;
    if (bar.bin.total === 1) {
      onJumpToEncounter(String(bar.bin.encounters[0].enc.encounter_id));
      setPopoverBinKey(null);
      return;
    }
    setPopoverBinKey((prev) => (prev === bar.bin.label ? null : bar.bin.label));
  };

  const handleBrushChange = (fromMs: number, toMs: number) => {
    const next = clampRange(fromMs, toMs, fullMinMs, fullMaxMs);
    if (isControlled) onVisibleRangeChange?.(next.fromMs, next.toMs);
    else setInternalZoom(next);
  };

  const handleResetZoom = () => {
    if (isControlled) onVisibleRangeChange?.(null, null);
    else setInternalZoom(null);
  };

  const popoverBar = popoverBinKey ? bars.find((b) => b.bin.label === popoverBinKey) ?? null : null;
  const hoverBar = hoverBinKey ? bars.find((b) => b.bin.label === hoverBinKey) ?? null : null;

  return (
    <Box
      role="group"
      aria-label="Encounter timeline scrubber"
      data-testid="encounter-timeline-scrubber"
      data-zoomed={isZoomed ? "true" : "false"}
      data-granularity={granularity}
      sx={{
        position: "sticky",
        top: 0,
        zIndex: 20,
        border: "1px solid",
        borderColor: "divider",
        borderRadius: "8px",
        bgcolor: "background.paper",
        px: 1.5,
        pt: 1,
        pb: 0.75,
        boxShadow: stuck ? "0 6px 16px rgba(15, 23, 42, 0.08)" : "none",
        transition: reducedMotion ? "none" : "box-shadow 0.18s ease-out",
      }}
    >
      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", mb: 0.5, gap: 1 }}>
        <Typography variant="caption" sx={{ color: "text.secondary", fontWeight: 600 }}>
          Patient timeline ({encounters.length} encounters, by {granularity})
        </Typography>
        <Box sx={{ display: "flex", gap: 1, alignItems: "center" }}>
          {isZoomed && (
            <Button
              size="small"
              variant="text"
              onClick={handleResetZoom}
              sx={{ minWidth: 0, fontSize: "0.7rem", py: 0, px: 0.75 }}
            >
              Reset zoom
            </Button>
          )}
          <Typography variant="caption" sx={{ color: "text.disabled", fontSize: "0.65rem" }}>
            Click a bar to jump - drag the focus band to filter
          </Typography>
        </Box>
      </Box>

      <Box
        sx={{
          position: "relative",
          height: TRACK_HEIGHT,
          width: "100%",
        }}
      >
        <Box
          aria-hidden="true"
          sx={{
            position: "absolute",
            left: 0,
            right: 0,
            bottom: 0,
            height: 1,
            bgcolor: COLOR_AXIS,
          }}
        />
        {windowBand && (
          <Box
            data-testid="timeline-window-band"
            aria-hidden="true"
            sx={{
              position: "absolute",
              top: 0,
              bottom: 0,
              left: `${windowBand.leftPct}%`,
              width: `${windowBand.widthPct}%`,
              bgcolor: COLOR_BAND,
              borderLeft: `1px dashed ${COLOR_BAND_BORDER}`,
              borderRight: `1px dashed ${COLOR_BAND_BORDER}`,
              borderRadius: "2px",
            }}
          />
        )}
        {focusBand && (
          <Box
            data-testid="timeline-focus-band"
            aria-hidden="true"
            sx={{
              position: "absolute",
              top: 0,
              bottom: 0,
              left: `${focusBand.leftPct}%`,
              width: `${focusBand.widthPct}%`,
              bgcolor: "rgba(29, 78, 216, 0.08)",
              borderLeft: "2px solid rgba(29, 78, 216, 0.55)",
              borderRight: "2px solid rgba(29, 78, 216, 0.55)",
              borderRadius: "2px",
              pointerEvents: "none",
            }}
          />
        )}
        {bars.map((bar) => (
          <HistogramBar
            key={`bar-${bar.bin.label}`}
            bar={bar}
            isActive={
              activeEncounterId !== null &&
              bar.bin.encounters.some(
                (e) => String(e.enc.encounter_id) === activeEncounterId
              )
            }
            isHovered={hoverBinKey === bar.bin.label}
            isOutOfFocus={
              isZoomed &&
              (bar.bin.endMs <= visibleFromMs || bar.bin.startMs >= visibleToMs)
            }
            maxTotal={maxTotal}
            hoverDuration={hoverDuration}
            onActivate={() => handleBarActivate(bar)}
            onArrow={(direction) =>
              jumpFromBin({
                bins,
                activeEncounterId,
                direction,
                onJump: onJumpToEncounter,
              })
            }
            onHoverChange={(hovered) =>
              setHoverBinKey((prev) =>
                hovered ? bar.bin.label : prev === bar.bin.label ? null : prev
              )
            }
          />
        ))}
        <AnimatePresence>
          {hoverBar && popoverBinKey === null && (
            <HoverPreview bar={hoverBar} trackHeight={TRACK_HEIGHT} />
          )}
          {popoverBar && (
            <TimelineBinPopover
              key={`popover-${popoverBar.bin.label}`}
              bin={popoverBar.bin}
              anchorPct={popoverBar.centerPct}
              trackHeight={TRACK_HEIGHT}
              reducedMotion={reducedMotion}
              onJump={(encounterId) => {
                onJumpToEncounter(encounterId);
                setPopoverBinKey(null);
              }}
              onClose={() => setPopoverBinKey(null)}
            />
          )}
        </AnimatePresence>
      </Box>

      <Box sx={{ mt: 0.75 }}>
        <TimelineRangeBrush
          fullMinMs={fullMinMs}
          fullMaxMs={fullMaxMs}
          visibleFromMs={visibleFromMs}
          visibleToMs={visibleToMs}
          onChange={handleBrushChange}
        />
      </Box>
    </Box>
  );
}
