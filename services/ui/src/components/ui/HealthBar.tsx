"use client";

import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Tooltip from "@mui/material/Tooltip";
import { HealthStatus, HEALTH_COLORS, STAGE_COLORS, FONT_SIZES } from "@/theme/tokens";

export interface StageHealth {
  key: string;
  label: string;
  status: HealthStatus;
  reason?: string;
}

interface HealthBarProps {
  stages: StageHealth[];
  activeStage?: string;
  onStageClick?: (key: string) => void;
}

export function HealthBar({ stages, activeStage, onStageClick }: HealthBarProps) {
  return (
    <Box
      sx={{
        display: "flex",
        gap: 0.5,
        bgcolor: "background.paper",
        border: "1px solid",
        borderColor: "divider",
        borderRadius: 2,
        p: 0.75,
        flexWrap: "wrap",
      }}
      role="navigation"
      aria-label="Pipeline stages"
    >
      {stages.map((stage, i) => {
        const isActive = stage.key === activeStage;
        const dotColor = HEALTH_COLORS[stage.status];
        const accentColor = STAGE_COLORS[stage.key] ?? "#1565c0";

        return (
          <Box key={stage.key} sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
            {i > 0 && (
              <Box
                component="span"
                sx={{ color: "text.disabled", fontSize: FONT_SIZES.label, mx: 0.25 }}
                aria-hidden="true"
              >
                -&gt;
              </Box>
            )}
            <Tooltip title={stage.reason ?? stage.label} arrow placement="bottom">
              <Box
                role="button"
                tabIndex={0}
                aria-pressed={isActive}
                aria-label={`${stage.label}: ${stage.status}${stage.reason ? ` - ${stage.reason}` : ""}`}
                onClick={() => onStageClick?.(stage.key)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    onStageClick?.(stage.key);
                  }
                }}
                sx={{
                  display: "flex",
                  alignItems: "center",
                  gap: 0.75,
                  px: 1.25,
                  py: 0.5,
                  borderRadius: 1.5,
                  cursor: "pointer",
                  bgcolor: isActive ? `${accentColor}14` : "transparent",
                  border: "1px solid",
                  borderColor: isActive ? accentColor : "transparent",
                  "&:hover": { bgcolor: `${accentColor}0e` },
                  transition: "all 0.15s ease",
                }}
              >
                <Box
                  sx={{
                    width: 8,
                    height: 8,
                    borderRadius: "50%",
                    bgcolor: dotColor,
                    flexShrink: 0,
                  }}
                />
                <Typography
                  sx={{
                    fontSize: FONT_SIZES.label,
                    fontWeight: isActive ? 700 : 500,
                    color: isActive ? accentColor : "text.primary",
                    letterSpacing: "0.04em",
                    textTransform: "uppercase",
                  }}
                >
                  {stage.label}
                </Typography>
              </Box>
            </Tooltip>
          </Box>
        );
      })}
    </Box>
  );
}
