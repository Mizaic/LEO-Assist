"use client";

import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Button from "@mui/material/Button";
import TipsAndUpdatesOutlinedIcon from "@mui/icons-material/TipsAndUpdatesOutlined";
import { FONT_SIZES } from "@/theme/tokens";

interface NudgeBannerProps {
  message: string;
  actionLabel?: string;
  onAction?: () => void;
  severity?: "info" | "warning" | "error";
}

const SEVERITY_STYLES = {
  info:    { bg: "#e3f2fd", border: "#90caf9", color: "#0d47a1", icon: "#1565c0" },
  warning: { bg: "#fff3e0", border: "#ffcc02", color: "#e65100", icon: "#ed6c02" },
  error:   { bg: "#ffebee", border: "#ef9a9a", color: "#b71c1c", icon: "#d32f2f" },
};

export function NudgeBanner({
  message,
  actionLabel,
  onAction,
  severity = "info",
}: NudgeBannerProps) {
  const s = SEVERITY_STYLES[severity];
  return (
    <Box
      role="status"
      aria-live="polite"
      sx={{
        display: "flex",
        alignItems: "center",
        gap: 1.5,
        bgcolor: s.bg,
        border: `1px solid ${s.border}`,
        borderRadius: 1.5,
        px: 2,
        py: 1.25,
        mb: 2,
      }}
    >
      <TipsAndUpdatesOutlinedIcon sx={{ color: s.icon, fontSize: 20, flexShrink: 0 }} />
      <Typography sx={{ flex: 1, fontSize: FONT_SIZES.body, color: s.color, lineHeight: 1.5 }}>
        {message}
      </Typography>
      {actionLabel && onAction && (
        <Button
          size="small"
          onClick={onAction}
          sx={{
            color: s.color,
            fontWeight: 700,
            fontSize: FONT_SIZES.label,
            textTransform: "none",
            whiteSpace: "nowrap",
            flexShrink: 0,
          }}
        >
          {actionLabel}
        </Button>
      )}
    </Box>
  );
}
