/**
 * Four-phase rewind rail for clinical run review.
 *
 * Atlas: DI-49BA8E04 / VT-592D30E9
 */
"use client";

import Box from "@mui/material/Box";
import ButtonBase from "@mui/material/ButtonBase";
import Typography from "@mui/material/Typography";

import {
  CLINICAL_PHASE_LABEL,
  CLINICAL_PHASES,
  phaseIndex,
  type ClinicalPhaseId,
} from "./clinicalPhases";

interface Props {
  selected: ClinicalPhaseId;
  onSelect: (phase: ClinicalPhaseId) => void;
}

export function PhaseRail({ selected, onSelect }: Props) {
  const current = phaseIndex(selected);
  return (
    <Box
      sx={{
        width: 120,
        minWidth: 120,
        borderRight: "1px solid",
        borderColor: "divider",
        display: "flex",
        flexDirection: "column",
        gap: 0.5,
        p: 1.5,
        bgcolor: "#FAFAFA",
      }}
      data-testid="validation-lab-phase-rail"
    >
      <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 700 }}>
        {current} / {CLINICAL_PHASES.length}
      </Typography>
      {CLINICAL_PHASES.map((phase) => {
        const active = phase === selected;
        return (
          <ButtonBase
            key={phase}
            onClick={() => onSelect(phase)}
            aria-current={active ? "step" : undefined}
            data-testid={`validation-lab-phase-${phase}`}
            sx={{
              display: "block",
              width: "100%",
              textAlign: "left",
              px: 1,
              py: 0.75,
              borderRadius: "8px",
              borderLeft: "3px solid",
              borderLeftColor: active ? "primary.main" : "transparent",
              bgcolor: active ? "#FFFFFF" : "transparent",
              fontWeight: active ? 700 : 500,
              cursor: "pointer",
            }}
          >
            <Typography variant="body2" sx={{ fontWeight: "inherit" }}>
              {CLINICAL_PHASE_LABEL[phase]}
            </Typography>
          </ButtonBase>
        );
      })}
    </Box>
  );
}
