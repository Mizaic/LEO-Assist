/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-146D93D0
 *   DI: DI-6EA84931
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-146D93D0")
 */
"use client";

import { useMemo } from "react";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Typography from "@mui/material/Typography";
import type { EpisodeMilestone } from "@/lib/missionControlApi";
import { MILESTONE_LABELS, shortDate } from "./encounterTextUtils";

// Row of chips above the EncounterTextTab list that lets the
// reviewer jump to a specific milestone-anchor encounter. Pure
// presentation -- the parent owns focus state and the click
// handler.

interface Props {
  milestones: EpisodeMilestone[];
  focusedEncounterId: string | null;
  onJump: (encounterId: string) => void;
}

interface MilestoneJump {
  key: string;
  encounterId: string;
  label: string;
  date: string | null;
}

function buildJumps(milestones: EpisodeMilestone[]): MilestoneJump[] {
  const rows = milestones
    .filter((m) => Boolean(m.encounter_id))
    .map((m, idx) => ({
      key: `${m.milestone_type}-${m.encounter_id}-${idx}`,
      encounterId: String(m.encounter_id),
      label:
        MILESTONE_LABELS[m.milestone_type] ??
        m.milestone_type.replaceAll("_", " "),
      date: m.date ?? null,
    }));
  return rows.sort((a, b) => {
    const ta = Date.parse(a.date ?? "");
    const tb = Date.parse(b.date ?? "");
    if (!Number.isFinite(ta)) return 1;
    if (!Number.isFinite(tb)) return -1;
    return ta - tb;
  });
}

export default function MilestoneJumpChips({
  milestones,
  focusedEncounterId,
  onJump,
}: Props) {
  const jumps = useMemo(() => buildJumps(milestones), [milestones]);
  if (jumps.length === 0) return null;
  return (
    <Box
      sx={{
        display: "flex",
        gap: 1,
        flexWrap: "wrap",
        alignItems: "center",
      }}
      data-testid="milestone-jump-chips"
    >
      <Typography variant="caption" color="text.secondary">
        Jump to milestone encounter:
      </Typography>
      {jumps.map((milestone) => (
        <Chip
          key={milestone.key}
          size="small"
          clickable
          onClick={() => onJump(milestone.encounterId)}
          color={
            focusedEncounterId === milestone.encounterId ? "primary" : "default"
          }
          variant={
            focusedEncounterId === milestone.encounterId ? "filled" : "outlined"
          }
          label={`${milestone.label} - ${shortDate(milestone.date)}`}
        />
      ))}
    </Box>
  );
}
