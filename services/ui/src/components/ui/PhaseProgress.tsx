"use client";

import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import LinearProgress from "@mui/material/LinearProgress";
import Typography from "@mui/material/Typography";
import { FONT_SIZES } from "@/theme/tokens";

const PHASES = ["export", "train", "evaluate", "upload", "register"];
const PHASE_LABELS: Record<string, string> = {
  export:   "Export",
  train:    "Train",
  evaluate: "Evaluate",
  upload:   "Upload",
  register: "Register",
};

interface PhaseProgressProps {
  phase: string;
  elapsed?: number | null;
  liveF1?: number | null;
}

export function PhaseProgress({ phase, elapsed, liveF1 }: PhaseProgressProps) {
  const idx = PHASES.indexOf(phase);
  const pct = idx < 0 ? 0 : Math.round(((idx + 1) / PHASES.length) * 100);

  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 0.75 }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
        {PHASES.map((p, i) => {
          const done = idx >= 0 && i < idx;
          const active = p === phase;
          return (
            <Chip
              key={p}
              label={PHASE_LABELS[p]}
              size="small"
              sx={{
                fontWeight: active ? 700 : 400,
                fontSize: FONT_SIZES.label,
                bgcolor: active
                  ? "primary.main"
                  : done
                  ? "success.main"
                  : "action.hover",
                color:
                  active || done ? "common.white" : "text.secondary",
                height: 22,
              }}
            />
          );
        })}
        {elapsed != null && (
          <Typography sx={{ ml: "auto", fontSize: FONT_SIZES.label, color: "text.secondary" }}>
            {Math.round(elapsed)}s
          </Typography>
        )}
      </Box>
      <LinearProgress
        variant="determinate"
        value={pct}
        sx={{ height: 4, borderRadius: 2 }}
        color={idx >= 0 && idx === PHASES.length - 1 ? "success" : "primary"}
      />
      {liveF1 != null && (
        <Typography sx={{ fontSize: FONT_SIZES.label, color: "text.secondary" }}>
          Live F1: {(liveF1 * 100).toFixed(1)}%
        </Typography>
      )}
    </Box>
  );
}
