/**
 * Validation Lab three-path home with open-findings strip.
 *
 * Atlas: DI-238DA59A / DO-4FD76836
 *
 * Atlas trace:
 *   DO: DO-158BE606
 *   DI: DI-2289D095
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-158BE606")
 */
"use client";

import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { color, typography } from "@leo/design-system/tokens";

import { HOME_DOORS, type LabDoor } from "./accuracyLoopDoors";
import { DoorCard, FindingsStrip } from "./AccuracyLoopHomeParts";
import type { LabCase } from "./labApi";
import type { ValidationFinding } from "./findingTypes";

export type { LabDoor };

interface Props {
  goldCases: LabCase[];
  openFindings: ValidationFinding[];
  onOpenDoor: (door: LabDoor) => void;
  onOpenGold: (caseId: string) => void;
  onOpenFinding: (runId: string) => void;
}

export default function AccuracyLoopHome({
  goldCases,
  openFindings,
  onOpenDoor,
  onOpenFinding,
}: Props) {
  return (
    <Box data-testid="validation-lab-home">
      <Typography
        sx={{
          mb: 0.5,
          fontFamily: typography.fontFamily.heading,
          fontWeight: 700,
          fontSize: 22,
          color: color.text.primary,
        }}
      >
        Validation Lab
      </Typography>
      <Typography
        sx={{
          mb: 3,
          maxWidth: 560,
          fontSize: 14,
          color: color.text.secondary,
        }}
      >
        Check that LEO reads a letter the way you would. Pick one path.
      </Typography>
      <Box
        data-testid="validation-lab-home-doors"
        sx={{
          display: "grid",
          gridTemplateColumns: { xs: "1fr", md: "1fr 1fr 1fr" },
          gap: 2,
          mb: 3,
        }}
      >
        {HOME_DOORS.map((door, index) => (
          <DoorCard
            key={door.id}
            door={door}
            index={index}
            goldCount={door.id === "saved" ? goldCases.length : undefined}
            onClick={() => onOpenDoor(door.id)}
          />
        ))}
      </Box>
      <FindingsStrip
        openFindings={openFindings}
        onOpenFinding={onOpenFinding}
      />
    </Box>
  );
}
