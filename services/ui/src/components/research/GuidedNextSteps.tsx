"use client";

import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Button from "@mui/material/Button";
import EastOutlinedIcon from "@mui/icons-material/EastOutlined";
import type { RunResult } from "@/lib/researchApi";

interface Props {
  result: RunResult | null;
  onNavigate: (missionId: string) => void;
}

export default function GuidedNextSteps({ result, onNavigate }: Props) {
  if (!result?.next_steps?.length) return null;

  return (
    <Box sx={{ mt: 2 }}>
      <Typography
        variant="caption"
        sx={{
          fontWeight: 600,
          color: "text.secondary",
          textTransform: "uppercase",
          letterSpacing: "0.08em",
        }}
      >
        You might also want to check
      </Typography>
      <Box
        sx={{
          mt: 1,
          display: "flex",
          flexDirection: "column",
          gap: 0.5,
        }}
      >
        {result.next_steps.map((step) => (
          <Button
            key={step.target}
            variant="text"
            size="small"
            endIcon={<EastOutlinedIcon fontSize="small" />}
            onClick={() => onNavigate(step.target)}
            sx={{
              textTransform: "none",
              justifyContent: "flex-start",
              fontSize: "0.8125rem",
              px: 0,
              color: "primary.main",
              "&:hover": { bgcolor: "transparent", textDecoration: "underline" },
            }}
            aria-label={`Explore: ${step.label}`}
          >
            {step.label}
          </Button>
        ))}
      </Box>
    </Box>
  );
}
