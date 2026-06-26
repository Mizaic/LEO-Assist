"use client";

/**
 * PresentationMode -- full-screen progressive tile reveal.
 *
 * Features:
 *   - Tiles shown one section at a time, full viewport width
 *   - Section title card shown before each group
 *   - Tiles with story.animate_in=true fade/slide in on enter
 *   - Keyboard nav: Right/Space = next, Left = previous, Escape = exit
 *   - Progress indicator showing current section and tile position
 *
 * Atlas trace: DO-A9863AB6 / DI-758B73A5
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import Box from "@mui/material/Box";
import IconButton from "@mui/material/IconButton";
import Typography from "@mui/material/Typography";
import ArrowBackIosNewIcon from "@mui/icons-material/ArrowBackIosNew";
import ArrowForwardIosIcon from "@mui/icons-material/ArrowForwardIos";
import CloseIcon from "@mui/icons-material/Close";

import type { AuditTemplate, MetricRunResult } from "@/lib/auditTemplateApi";
import MetricTile from "./MetricTile";
import WidgetTile from "./WidgetTile";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface PresentationModeProps {
  template: AuditTemplate;
  orgId: string;
  mockResults?: Map<string, MetricRunResult>;
  onClose: () => void;
}

type Slide =
  | { kind: "section-title"; label: string; count: number }
  | { kind: "tile"; tileId: string };

// ---------------------------------------------------------------------------
// Build slide deck from template
// ---------------------------------------------------------------------------

function buildSlides(template: AuditTemplate): Slide[] {
  const groups: Record<string, typeof template.tiles> = {};
  for (const tile of template.tiles) {
    const key = tile.section?.trim() || "General";
    if (!groups[key]) groups[key] = [];
    groups[key].push(tile);
  }

  const slides: Slide[] = [];
  for (const [label, tiles] of Object.entries(groups)) {
    slides.push({ kind: "section-title", label, count: tiles.length });
    for (const tile of tiles) {
      slides.push({ kind: "tile", tileId: tile.id ?? tile.tile_id });
    }
  }
  return slides;
}

// ---------------------------------------------------------------------------
// Progress dots
// ---------------------------------------------------------------------------

function ProgressBar({
  current,
  total,
}: {
  current: number;
  total: number;
}) {
  return (
    <Box sx={{ display: "flex", gap: 0.5, alignItems: "center" }}>
      {Array.from({ length: Math.min(total, 20) }, (_, i) => (
        <Box
          key={i}
          sx={{
            width: i === current ? 20 : 6,
            height: 6,
            borderRadius: 3,
            bgcolor: i === current ? "primary.main" : "rgba(255,255,255,0.4)",
            transition: "all 300ms ease",
          }}
        />
      ))}
      <Typography variant="caption" sx={{ ml: 1, color: "rgba(255,255,255,0.7)", fontSize: 11 }}>
        {current + 1} / {total}
      </Typography>
    </Box>
  );
}

// ---------------------------------------------------------------------------
// Section title card
// ---------------------------------------------------------------------------

function SectionTitleCard({
  label,
  count,
  animateIn,
}: {
  label: string;
  count: number;
  animateIn: boolean;
}) {
  return (
    <Box
      sx={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        height: "100%",
        opacity: animateIn ? 1 : 0,
        transform: animateIn ? "translateY(0)" : "translateY(24px)",
        transition: "opacity 400ms ease, transform 400ms ease",
        px: 6,
        textAlign: "center",
      }}
    >
      <Typography
        variant="overline"
        sx={{ color: "rgba(255,255,255,0.6)", letterSpacing: 4, mb: 1 }}
      >
        Section
      </Typography>
      <Typography
        variant="h3"
        fontWeight={700}
        sx={{ color: "white", mb: 1.5, lineHeight: 1.2 }}
      >
        {label}
      </Typography>
      <Typography variant="body1" sx={{ color: "rgba(255,255,255,0.7)" }}>
        {count} {count === 1 ? "tile" : "tiles"} in this section
      </Typography>
    </Box>
  );
}

// ---------------------------------------------------------------------------
// Tile slide
// ---------------------------------------------------------------------------

function TileSlide({
  tileId,
  template,
  orgId,
  mockResults,
  animateIn,
}: {
  tileId: string;
  template: AuditTemplate;
  orgId: string;
  mockResults?: Map<string, MetricRunResult>;
  animateIn: boolean;
}) {
  const tile = template.tiles.find((t) => (t.id ?? t.tile_id) === tileId);
  if (!tile) return null;

  const shouldAnimate = tile.story?.animate_in ?? false;
  const mockData = mockResults?.get(tile.metric_id);

  return (
    <Box
      sx={{
        maxWidth: 900,
        width: "100%",
        mx: "auto",
        px: 4,
        opacity: !shouldAnimate || animateIn ? 1 : 0,
        transform: !shouldAnimate || animateIn ? "translateY(0)" : "translateY(32px)",
        transition: "opacity 350ms ease 100ms, transform 350ms ease 100ms",
      }}
    >
      {tile.tile_type === "widget" ? (
        <WidgetTile tile={tile} orgId={orgId} />
      ) : (
        <MetricTile tile={tile} orgId={orgId} mockData={mockData} />
      )}
    </Box>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function PresentationMode({
  template,
  orgId,
  mockResults,
  onClose,
}: PresentationModeProps) {
  const slides = useMemo(() => buildSlides(template), [template]);
  const [current, setCurrent] = useState(0);
  const [animateIn, setAnimateIn] = useState(true);

  const goTo = useCallback(
    (index: number) => {
      setAnimateIn(false);
      setTimeout(() => {
        setCurrent(Math.max(0, Math.min(index, slides.length - 1)));
        setAnimateIn(true);
      }, 120);
    },
    [slides.length],
  );

  const next = useCallback(() => {
    if (current < slides.length - 1) goTo(current + 1);
    else onClose();
  }, [current, slides.length, goTo, onClose]);

  const prev = useCallback(() => {
    if (current > 0) goTo(current - 1);
  }, [current, goTo]);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "ArrowRight" || e.key === " ") { e.preventDefault(); next(); }
      else if (e.key === "ArrowLeft") { e.preventDefault(); prev(); }
      else if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [next, prev, onClose]);

  const slide = slides[current];
  const isSectionTitle = slide?.kind === "section-title";

  return (
    <Box
      sx={{
        position: "fixed",
        inset: 0,
        zIndex: 1400,
        bgcolor: isSectionTitle ? "#1E293B" : "#0F172A",
        display: "flex",
        flexDirection: "column",
        transition: "background-color 500ms ease",
      }}
    >
      {/* Top bar */}
      <Box
        sx={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          px: 3,
          py: 1.5,
          flexShrink: 0,
        }}
      >
        <Typography variant="subtitle2" sx={{ color: "rgba(255,255,255,0.6)" }}>
          {template.title}
        </Typography>
        <ProgressBar current={current} total={slides.length} />
        <IconButton size="small" onClick={onClose} sx={{ color: "rgba(255,255,255,0.7)" }}>
          <CloseIcon />
        </IconButton>
      </Box>

      {/* Slide content */}
      <Box
        sx={{
          flex: 1,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          overflow: "hidden",
          py: 2,
        }}
      >
        {slide?.kind === "section-title" && (
          <SectionTitleCard
            label={slide.label}
            count={slide.count}
            animateIn={animateIn}
          />
        )}
        {slide?.kind === "tile" && (
          <TileSlide
            tileId={slide.tileId}
            template={template}
            orgId={orgId}
            mockResults={mockResults}
            animateIn={animateIn}
          />
        )}
      </Box>

      {/* Navigation controls */}
      <Box
        sx={{
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          gap: 4,
          py: 2,
          flexShrink: 0,
        }}
      >
        <IconButton
          onClick={prev}
          disabled={current === 0}
          sx={{ color: "white", opacity: current === 0 ? 0.3 : 1 }}
        >
          <ArrowBackIosNewIcon />
        </IconButton>
        <Typography variant="caption" sx={{ color: "rgba(255,255,255,0.5)", fontSize: 11 }}>
          Arrow keys to navigate -- Esc to exit
        </Typography>
        <IconButton onClick={next} sx={{ color: "white" }}>
          <ArrowForwardIosIcon />
        </IconButton>
      </Box>
    </Box>
  );
}
