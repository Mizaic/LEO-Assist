/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-30A82196
 *   DI: DI-85B110A5
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-30A82196")
 */
"use client";

import Box from "@mui/material/Box";
import Tooltip from "@mui/material/Tooltip";
import type { Milestone } from "@/lib/pathwayRisk";
import { MILESTONE_ORDER } from "@/lib/pathwayRisk";

const STAGE_LABELS: Record<string, string> = {
  presentation: "Referred",
  referral: "Booked",
  first_clinic: "First Seen",
  diagnosis: "Diagnostics",
  treatment_decision: "Outcome Planned",
  first_treatment: "Outcome",
};

export default function PathwayProgressBar({
  milestones,
}: {
  milestones: Milestone[];
}) {
  const achieved = new Set(milestones.map((m) => m.milestone_type));
  const current =
    MILESTONE_ORDER.find((step) => !achieved.has(step)) ?? null;

  return (
    <Box
      sx={{
        display: "flex",
        alignItems: "center",
        width: "100%",
        py: 0.25,
      }}
    >
      {MILESTONE_ORDER.map((step, index) => {
        const isAchieved = achieved.has(step);
        const isCurrent = current === step;
        const dotColor = isAchieved
          ? "#16a34a"
          : isCurrent
            ? "#d97706"
            : "#d1d5db";

        return (
          <Box
            key={step}
            sx={{
              display: "flex",
              alignItems: "center",
              flex: index < MILESTONE_ORDER.length - 1 ? 1 : "none",
            }}
          >
            <Tooltip title={STAGE_LABELS[step] ?? step} arrow>
              <Box
                sx={{
                  width: 11,
                  height: 11,
                  borderRadius: "50%",
                  bgcolor: dotColor,
                  flexShrink: 0,
                  boxShadow: isCurrent
                    ? `0 0 0 2.5px ${dotColor}40`
                    : "none",
                  transition: "box-shadow 0.2s",
                }}
              />
            </Tooltip>
            {index < MILESTONE_ORDER.length - 1 && (
              <Box
                sx={{
                  flex: 1,
                  height: 2,
                  mx: 0.5,
                  borderRadius: 1,
                  bgcolor: isAchieved ? "#16a34a" : "#e5e7eb",
                  minWidth: 6,
                }}
              />
            )}
          </Box>
        );
      })}
    </Box>
  );
}
