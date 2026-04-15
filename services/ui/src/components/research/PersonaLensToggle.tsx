"use client";

import Box from "@mui/material/Box";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import Typography from "@mui/material/Typography";
import type { PersonaLens } from "@/lib/researchApi";

interface Props {
  value: PersonaLens;
  onChange: (lens: PersonaLens) => void;
}

const LENSES: Array<{ value: PersonaLens; label: string; hint: string }> = [
  {
    value: "patients",
    label: "Patients",
    hint: "Where are my patients and what is happening to them?",
  },
  {
    value: "pathways",
    label: "Pathways",
    hint: "How are our processes performing?",
  },
  {
    value: "capacity",
    label: "Capacity",
    hint: "Where should we focus our resources?",
  },
];

export default function PersonaLensToggle({ value, onChange }: Props) {
  const activeHint = LENSES.find((l) => l.value === value)?.hint ?? "";

  return (
    <Box>
      <Typography
        variant="caption"
        sx={{
          fontWeight: 600,
          color: "text.secondary",
          textTransform: "uppercase",
          letterSpacing: "0.08em",
          mr: 1.5,
        }}
      >
        I am interested in:
      </Typography>
      <ToggleButtonGroup
        value={value}
        exclusive
        onChange={(_, v) => v && onChange(v as PersonaLens)}
        size="small"
        aria-label="Perspective lens"
        sx={{ verticalAlign: "middle" }}
      >
        {LENSES.map((l) => (
          <ToggleButton
            key={l.value}
            value={l.value}
            aria-label={`${l.label} perspective`}
            sx={{
              textTransform: "none",
              fontSize: "0.8125rem",
              px: 2,
              py: 0.625,
              border: "1px solid",
              borderColor: "divider",
              "&.Mui-selected": {
                bgcolor: "primary.main",
                color: "primary.contrastText",
                "&:hover": { bgcolor: "primary.dark" },
              },
            }}
          >
            {l.label}
          </ToggleButton>
        ))}
      </ToggleButtonGroup>
      {activeHint && (
        <Typography
          variant="caption"
          sx={{ ml: 1.5, color: "text.secondary", verticalAlign: "middle" }}
        >
          {activeHint}
        </Typography>
      )}
    </Box>
  );
}
