"use client";

import { type KeyboardEvent } from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { motion as fm } from "framer-motion";
import type { DatedEncounter, TimelineBin } from "./timelineBins";
import { shortDate, shortPreview } from "./encounterTextUtils";

// Per-bin popover for the encounter timeline scrubber. Renders one
// row per encounter in the bin (date, coded count, linked badge,
// short preview); each row jumps to its encounter on click.
//
// Design Controls: UN-LEO-AI-077, DI-LEO-AI-179, DO-LEO-AI-178,
// R-LEO-AI-174, VT-LEO-AI-173.

interface Props {
  bin: TimelineBin;
  anchorPct: number;
  trackHeight: number;
  reducedMotion: boolean;
  onJump: (encounterId: string) => void;
  onClose: () => void;
}

const COLOR_LINKED = "#2563eb";

function rowKeyDown(
  event: KeyboardEvent<HTMLDivElement>,
  encounterId: string,
  onJump: (encounterId: string) => void
) {
  if (event.key === "Enter" || event.key === " ") {
    event.preventDefault();
    onJump(encounterId);
  }
}

function PopoverRow({
  row,
  onJump,
}: {
  row: DatedEncounter;
  onJump: (encounterId: string) => void;
}) {
  const id = String(row.enc.encounter_id);
  const date = shortDate(row.enc.date);
  const preview = shortPreview(row.enc.text, 80);
  const codedSummary =
    row.enc.coded_count > 0
      ? `${row.enc.coded_count} coded`
      : "no codes";
  return (
    <Box
      role="button"
      tabIndex={0}
      data-encounter-id={id}
      data-popover-row="true"
      onClick={() => onJump(id)}
      onKeyDown={(e) => rowKeyDown(e, id, onJump)}
      aria-label={`Jump to encounter on ${date}, ${codedSummary}${row.isLinked ? ", linked to focused episode" : ""}`}
      sx={{
        display: "flex",
        flexDirection: "column",
        gap: 0.25,
        px: 1,
        py: 0.75,
        borderRadius: "6px",
        cursor: "pointer",
        outline: "none",
        "&:hover, &:focus-visible": { bgcolor: "#f1f5f9" },
        "&:focus-visible": { boxShadow: `0 0 0 2px ${COLOR_LINKED} inset` },
      }}
    >
      <Box sx={{ display: "flex", alignItems: "center", gap: 0.75 }}>
        <Typography
          variant="caption"
          sx={{ fontWeight: 700, color: "#0f172a", fontSize: "0.72rem" }}
        >
          {date}
        </Typography>
        <Typography
          variant="caption"
          sx={{ color: "#475569", fontSize: "0.68rem" }}
        >
          {codedSummary}
        </Typography>
        {row.isLinked && (
          <Box
            component="span"
            data-linked-badge="true"
            sx={{
              fontSize: "0.6rem",
              fontWeight: 700,
              color: "white",
              bgcolor: COLOR_LINKED,
              borderRadius: "4px",
              px: 0.5,
              py: 0.1,
              textTransform: "uppercase",
              letterSpacing: 0.4,
            }}
          >
            Linked
          </Box>
        )}
      </Box>
      {preview && (
        <Typography
          variant="caption"
          sx={{
            color: "#334155",
            fontSize: "0.68rem",
            lineHeight: 1.35,
            display: "-webkit-box",
            WebkitLineClamp: 2,
            WebkitBoxOrient: "vertical",
            overflow: "hidden",
          }}
        >
          {preview}
        </Typography>
      )}
    </Box>
  );
}

export default function TimelineBinPopover({
  bin,
  anchorPct,
  trackHeight,
  reducedMotion,
  onJump,
  onClose,
}: Props) {
  const dur = reducedMotion ? 0 : 0.18;
  const handleRootKey = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Escape") {
      event.preventDefault();
      onClose();
    }
  };
  const startLabel = shortDate(new Date(bin.startMs).toISOString());
  return (
    <fm.div
      data-testid="timeline-bin-popover"
      data-bin-label={bin.label}
      role="dialog"
      aria-label={`Encounters in ${bin.label}`}
      tabIndex={-1}
      onKeyDown={handleRootKey}
      initial={{ opacity: 0, y: 6, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: 4, scale: 0.98 }}
      transition={{ duration: dur, ease: "easeOut" }}
      style={{
        position: "absolute",
        bottom: trackHeight + 8,
        left: `${anchorPct}%`,
        transform: "translateX(-50%)",
        background: "white",
        border: "1px solid #e2e8f0",
        borderRadius: 10,
        boxShadow: "0 14px 40px rgba(15, 23, 42, 0.18)",
        padding: 8,
        minWidth: 240,
        maxWidth: 320,
        maxHeight: 280,
        overflowY: "auto",
        zIndex: 30,
      }}
    >
      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", px: 0.5, pb: 0.5 }}>
        <Typography variant="caption" sx={{ fontWeight: 700, color: "#0f172a" }}>
          {bin.label}
        </Typography>
        <Typography variant="caption" sx={{ color: "#64748b", fontSize: "0.65rem" }}>
          {bin.total} encounters{bin.linked > 0 ? `, ${bin.linked} linked` : ""}
        </Typography>
      </Box>
      <Typography variant="caption" sx={{ display: "block", px: 0.5, color: "#94a3b8", fontSize: "0.62rem", mb: 0.5 }}>
        Starts {startLabel} - tap a row to jump
      </Typography>
      <Box sx={{ display: "flex", flexDirection: "column", gap: 0.25 }}>
        {bin.encounters.map((row) => (
          <PopoverRow
            key={`pop-${row.enc.encounter_id}`}
            row={row}
            onJump={onJump}
          />
        ))}
      </Box>
    </fm.div>
  );
}
