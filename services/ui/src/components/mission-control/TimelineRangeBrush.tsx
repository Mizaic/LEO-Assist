/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-5312F884
 *   DI: DI-AA1F5F5B
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-5312F884")
 */
"use client";

import { useCallback, useEffect, useRef, useState, type KeyboardEvent } from "react";
import type React from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { pctBetween } from "./timelineBins";
import { shortDate } from "./encounterTextUtils";

// Zoom brush for the encounter timeline scrubber. A slim overview
// rail with two draggable handles bound to the visible [from, to]
// range. Mouse, touch, and keyboard (ArrowLeft / ArrowRight, with
// Shift for larger steps) all supported.
//
// Design Controls: UN-LEO-AI-077, DI-LEO-AI-179, DO-LEO-AI-178,
// R-LEO-AI-174, VT-LEO-AI-173.

interface Props {
  fullMinMs: number;
  fullMaxMs: number;
  visibleFromMs: number;
  visibleToMs: number;
  onChange: (fromMs: number, toMs: number) => void;
}

const RAIL_HEIGHT = 18;
const HANDLE_WIDTH = 12;
const COLOR_RAIL = "#f1f5f9";
const COLOR_RAIL_BORDER = "#e2e8f0";
const COLOR_BAND = "rgba(37, 99, 235, 0.18)";
const COLOR_BAND_BORDER = "rgba(37, 99, 235, 0.40)";
const COLOR_HANDLE = "#0d46d6";

type DragKind = "from" | "to" | "band" | null;

interface BandDragState {
  startClientX: number;
  startFromMs: number;
  startToMs: number;
}

function clamp(v: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, v));
}

function pxToMs(px: number, width: number, minMs: number, maxMs: number): number {
  if (width <= 0) return minMs;
  const ratio = clamp(px / width, 0, 1);
  return minMs + ratio * (maxMs - minMs);
}

export default function TimelineRangeBrush({
  fullMinMs,
  fullMaxMs,
  visibleFromMs,
  visibleToMs,
  onChange,
}: Props) {
  const railRef = useRef<HTMLDivElement | null>(null);
  const [drag, setDrag] = useState<DragKind>(null);
  const bandDragRef = useRef<BandDragState | null>(null);

  const fromPct = pctBetween(visibleFromMs, fullMinMs, fullMaxMs);
  const toPct = pctBetween(visibleToMs, fullMinMs, fullMaxMs);
  const minSpanMs = Math.max(86_400_000, (fullMaxMs - fullMinMs) * 0.02);

  const handleMouseDown = (kind: "from" | "to") => (
    event: React.MouseEvent<HTMLDivElement>
  ) => {
    event.preventDefault();
    event.stopPropagation();
    setDrag(kind);
  };

  const handleBandMouseDown = (event: React.MouseEvent<HTMLDivElement>) => {
    event.preventDefault();
    bandDragRef.current = {
      startClientX: event.clientX,
      startFromMs: visibleFromMs,
      startToMs: visibleToMs,
    };
    setDrag("band");
  };

  const updateHandle = useCallback(
    (clientX: number, kind: "from" | "to") => {
      const rail = railRef.current;
      if (!rail) return;
      const rect = rail.getBoundingClientRect();
      const ms = pxToMs(clientX - rect.left, rect.width, fullMinMs, fullMaxMs);
      if (kind === "from") {
        const next = clamp(ms, fullMinMs, visibleToMs - minSpanMs);
        onChange(next, visibleToMs);
      } else {
        const next = clamp(ms, visibleFromMs + minSpanMs, fullMaxMs);
        onChange(visibleFromMs, next);
      }
    },
    [fullMinMs, fullMaxMs, visibleFromMs, visibleToMs, minSpanMs, onChange]
  );

  const updateBand = useCallback(
    (clientX: number) => {
      const rail = railRef.current;
      const start = bandDragRef.current;
      if (!rail || !start) return;
      const rect = rail.getBoundingClientRect();
      const span = fullMaxMs - fullMinMs;
      if (rect.width <= 0 || span <= 0) return;
      const deltaMs = ((clientX - start.startClientX) / rect.width) * span;
      const width = start.startToMs - start.startFromMs;
      let nextFrom = start.startFromMs + deltaMs;
      let nextTo = start.startToMs + deltaMs;
      if (nextFrom < fullMinMs) {
        nextFrom = fullMinMs;
        nextTo = fullMinMs + width;
      }
      if (nextTo > fullMaxMs) {
        nextTo = fullMaxMs;
        nextFrom = fullMaxMs - width;
      }
      onChange(nextFrom, nextTo);
    },
    [fullMinMs, fullMaxMs, onChange]
  );

  useEffect(() => {
    if (!drag) return;
    const onMove = (event: MouseEvent) => {
      if (drag === "band") updateBand(event.clientX);
      else updateHandle(event.clientX, drag);
    };
    const onUp = () => {
      bandDragRef.current = null;
      setDrag(null);
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
  }, [drag, updateHandle, updateBand]);

  const stepHandle = (kind: "from" | "to", direction: -1 | 1, large: boolean) => {
    const span = fullMaxMs - fullMinMs;
    const step = (large ? 0.05 : 0.01) * span * direction;
    if (kind === "from") {
      const next = clamp(visibleFromMs + step, fullMinMs, visibleToMs - minSpanMs);
      onChange(next, visibleToMs);
    } else {
      const next = clamp(visibleToMs + step, visibleFromMs + minSpanMs, fullMaxMs);
      onChange(visibleFromMs, next);
    }
  };

  const stepBand = (direction: -1 | 1, large: boolean) => {
    const span = fullMaxMs - fullMinMs;
    const step = (large ? 0.05 : 0.01) * span * direction;
    const width = visibleToMs - visibleFromMs;
    let nextFrom = visibleFromMs + step;
    let nextTo = visibleToMs + step;
    if (nextFrom < fullMinMs) {
      nextFrom = fullMinMs;
      nextTo = fullMinMs + width;
    }
    if (nextTo > fullMaxMs) {
      nextTo = fullMaxMs;
      nextFrom = fullMaxMs - width;
    }
    onChange(nextFrom, nextTo);
  };

  const handleKeyDown = (kind: "from" | "to") => (
    event: KeyboardEvent<HTMLDivElement>
  ) => {
    if (event.key === "ArrowLeft") {
      event.preventDefault();
      stepHandle(kind, -1, event.shiftKey);
    } else if (event.key === "ArrowRight") {
      event.preventDefault();
      stepHandle(kind, 1, event.shiftKey);
    } else if (event.key === "Home") {
      event.preventDefault();
      if (kind === "from") onChange(fullMinMs, visibleToMs);
      else onChange(visibleFromMs, visibleFromMs + minSpanMs);
    } else if (event.key === "End") {
      event.preventDefault();
      if (kind === "to") onChange(visibleFromMs, fullMaxMs);
      else onChange(visibleToMs - minSpanMs, visibleToMs);
    }
  };

  const handleBandKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "ArrowLeft") {
      event.preventDefault();
      stepBand(-1, event.shiftKey);
    } else if (event.key === "ArrowRight") {
      event.preventDefault();
      stepBand(1, event.shiftKey);
    }
  };

  const fromLabel = shortDate(new Date(visibleFromMs).toISOString());
  const toLabel = shortDate(new Date(visibleToMs).toISOString());

  const handleSx = {
    position: "absolute" as const,
    top: -3,
    width: HANDLE_WIDTH,
    height: RAIL_HEIGHT + 6,
    bgcolor: COLOR_HANDLE,
    borderRadius: "3px",
    cursor: "ew-resize",
    boxShadow: "0 1px 4px rgba(15, 23, 42, 0.25)",
    "&:focus-visible": { outline: "2px solid #002178", outlineOffset: 2 },
  };

  return (
    <Box data-testid="timeline-range-brush" sx={{ width: "100%" }}>
      <Box
        ref={railRef}
        sx={{
          position: "relative",
          width: "100%",
          height: RAIL_HEIGHT,
          bgcolor: COLOR_RAIL,
          border: `1px solid ${COLOR_RAIL_BORDER}`,
          borderRadius: "4px",
        }}
      >
        <Box
          role="button"
          tabIndex={0}
          aria-label={`Timeline focus window from ${fromLabel} to ${toLabel}. Drag to pan, or use Arrow keys.`}
          data-testid="timeline-range-band"
          data-handle="band"
          onMouseDown={handleBandMouseDown}
          onKeyDown={handleBandKeyDown}
          sx={{
            position: "absolute",
            top: 0,
            bottom: 0,
            left: `${fromPct}%`,
            width: `${Math.max(0.5, toPct - fromPct)}%`,
            bgcolor: COLOR_BAND,
            border: `1px solid ${COLOR_BAND_BORDER}`,
            borderRadius: "3px",
            cursor: drag === "band" ? "grabbing" : "grab",
            "&:focus-visible": { outline: "2px solid #002178", outlineOffset: 2 },
          }}
        />
        <Box
          role="slider"
          tabIndex={0}
          aria-label="Timeline zoom start"
          aria-valuemin={fullMinMs}
          aria-valuemax={fullMaxMs}
          aria-valuenow={visibleFromMs}
          aria-valuetext={fromLabel}
          data-handle="from"
          onMouseDown={handleMouseDown("from")}
          onKeyDown={handleKeyDown("from")}
          sx={{
            ...handleSx,
            left: `calc(${fromPct}% - ${HANDLE_WIDTH / 2}px)`,
          }}
        />
        <Box
          role="slider"
          tabIndex={0}
          aria-label="Timeline zoom end"
          aria-valuemin={fullMinMs}
          aria-valuemax={fullMaxMs}
          aria-valuenow={visibleToMs}
          aria-valuetext={toLabel}
          data-handle="to"
          onMouseDown={handleMouseDown("to")}
          onKeyDown={handleKeyDown("to")}
          sx={{
            ...handleSx,
            left: `calc(${toPct}% - ${HANDLE_WIDTH / 2}px)`,
          }}
        />
      </Box>
      <Box sx={{ display: "flex", justifyContent: "space-between", mt: 0.25 }}>
        <Typography variant="caption" sx={{ color: "text.disabled", fontSize: "0.62rem" }}>
          {fromLabel}
        </Typography>
        <Typography variant="caption" sx={{ color: "text.disabled", fontSize: "0.62rem" }}>
          {toLabel}
        </Typography>
      </Box>
    </Box>
  );
}
