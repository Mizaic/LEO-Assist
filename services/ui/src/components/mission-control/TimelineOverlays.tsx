"use client";

import Box from "@mui/material/Box";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import { MILESTONE_LABELS, shortDate } from "./encounterTextUtils";
import { pctBetween } from "./timelineBins";

// Visual overlays drawn on top of the EncounterTimelineScrubber
// histogram. Pure presentation - no state, no observers.
//
// Design Controls: UN-LEO-AI-077, DI-LEO-AI-213, DO-LEO-AI-210,
// R-LEO-AI-174, VT-LEO-AI-205.

const COLOR_LINKED_TICK = "#2563eb";
const COLOR_MILESTONE = "#b45309";
const COLOR_MILESTONE_LABEL_BG = "#FEF3C7";

export interface LinkedTick {
  encounterId: string;
  ts: number;
}

interface LinkedEncounterTicksProps {
  ticks: LinkedTick[];
  fullMinMs: number;
  fullMaxMs: number;
}

export function LinkedEncounterTicks({
  ticks,
  fullMinMs,
  fullMaxMs,
}: LinkedEncounterTicksProps) {
  if (ticks.length === 0) return null;
  return (
    <>
      {ticks.map((tick) => (
        <Box
          key={`linked-tick-${tick.encounterId}`}
          aria-hidden="true"
          data-testid="timeline-linked-tick"
          data-encounter-id={tick.encounterId}
          sx={{
            position: "absolute",
            bottom: -1,
            left: `${pctBetween(tick.ts, fullMinMs, fullMaxMs)}%`,
            transform: "translateX(-50%)",
            width: 2,
            height: 7,
            bgcolor: COLOR_LINKED_TICK,
            borderRadius: "1px",
            pointerEvents: "none",
          }}
        />
      ))}
    </>
  );
}

export interface MilestoneMarker {
  key: string;
  encounterId: string;
  type: string;
  label: string;
  date: string;
  ts: number;
}

interface MilestoneMarkersProps {
  markers: MilestoneMarker[];
  fullMinMs: number;
  fullMaxMs: number;
  onJumpToEncounter?: (encounterId: string) => void;
}

export function MilestoneMarkers({
  markers,
  fullMinMs,
  fullMaxMs,
  onJumpToEncounter,
}: MilestoneMarkersProps) {
  if (markers.length === 0) return null;
  return (
    <>
      {markers.map((m) => {
        const leftPct = pctBetween(m.ts, fullMinMs, fullMaxMs);
        return (
          <Tooltip
            key={`milestone-${m.key}`}
            title={`${m.label} - ${shortDate(m.date)}`}
            placement="top"
            arrow
          >
            <Box
              data-testid="timeline-milestone-marker"
              data-milestone-type={m.type}
              data-encounter-id={m.encounterId}
              role={onJumpToEncounter ? "button" : undefined}
              tabIndex={onJumpToEncounter ? 0 : -1}
              aria-label={`Milestone: ${m.label} on ${shortDate(m.date)}`}
              onClick={() => onJumpToEncounter?.(m.encounterId)}
              onKeyDown={(event) => {
                if (!onJumpToEncounter) return;
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  onJumpToEncounter(m.encounterId);
                }
              }}
              sx={{
                position: "absolute",
                top: 0,
                bottom: 0,
                left: `${leftPct}%`,
                transform: "translateX(-50%)",
                width: 12,
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                cursor: onJumpToEncounter ? "pointer" : "default",
                outline: "none",
                "&:focus-visible > [data-marker-flag]": {
                  boxShadow: "0 0 0 2px rgba(180, 83, 9, 0.45)",
                },
                "&:hover > [data-marker-line]": {
                  opacity: 1,
                },
              }}
            >
              <Box
                data-marker-flag="true"
                sx={{
                  px: 0.5,
                  py: 0.1,
                  bgcolor: COLOR_MILESTONE_LABEL_BG,
                  border: `1px solid ${COLOR_MILESTONE}`,
                  borderRadius: "3px",
                  fontSize: "0.55rem",
                  fontWeight: 700,
                  color: COLOR_MILESTONE,
                  lineHeight: 1.2,
                  whiteSpace: "nowrap",
                  transform: "translateY(-50%)",
                  pointerEvents: "auto",
                }}
              >
                <Typography
                  component="span"
                  sx={{
                    fontSize: "inherit",
                    fontWeight: "inherit",
                    color: "inherit",
                    lineHeight: "inherit",
                  }}
                >
                  {m.label.charAt(0).toUpperCase()}
                </Typography>
              </Box>
              <Box
                data-marker-line="true"
                aria-hidden="true"
                sx={{
                  flex: 1,
                  width: 1,
                  bgcolor: COLOR_MILESTONE,
                  opacity: 0.45,
                  transition: "opacity 0.15s ease-out",
                  pointerEvents: "none",
                }}
              />
            </Box>
          </Tooltip>
        );
      })}
    </>
  );
}

export function buildMilestoneMarkers(
  milestones: Array<{ milestone_type: string; encounter_id: string; date: string }>
): MilestoneMarker[] {
  const rows: MilestoneMarker[] = [];
  milestones.forEach((m, idx) => {
    if (!m.date || !m.encounter_id) return;
    const ts = Date.parse(m.date);
    if (!Number.isFinite(ts)) return;
    const label = MILESTONE_LABELS[m.milestone_type] ?? m.milestone_type.replaceAll("_", " ");
    rows.push({
      key: `${m.milestone_type}-${m.encounter_id}-${idx}`,
      encounterId: String(m.encounter_id),
      type: m.milestone_type,
      label,
      date: m.date,
      ts,
    });
  });
  return rows.sort((a, b) => a.ts - b.ts);
}
