"use client";

import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Chip from "@mui/material/Chip";

interface Alert {
  episode_id: string;
  type: string;
  severity: string;
  description: string;
}

const SEVERITY_COLORS: Record<string, "error" | "warning" | "info" | "default"> = {
  critical: "error",
  high: "error",
  medium: "warning",
  low: "info",
};

export default function CSSAlertsSummary({ alerts }: { alerts: Alert[] }) {
  if (!alerts.length) {
    return (
      <Typography variant="body2" color="text.secondary">
        No CSS alerts detected. All episodes within expected parameters.
      </Typography>
    );
  }

  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 1.5 }}>
      {alerts.map((a, i) => (
        <Box
          key={`${a.episode_id}-${a.type}-${i}`}
          sx={{
            display: "flex",
            alignItems: "flex-start",
            gap: 1.5,
            px: 2,
            py: 1.5,
            borderRadius: 2,
            border: "1px solid",
            borderColor: "divider",
            "&:hover": { bgcolor: "grey.50" },
          }}
        >
          <Chip
            label={a.severity}
            size="small"
            color={SEVERITY_COLORS[a.severity] ?? "default"}
            sx={{ minWidth: 64, textTransform: "capitalize" }}
          />
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Typography variant="body2" sx={{ fontWeight: 600, fontSize: "0.85rem" }}>
              {a.type}
            </Typography>
            <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.25 }}>
              {a.description}
            </Typography>
          </Box>
          <Typography
            variant="caption"
            color="text.secondary"
            sx={{ whiteSpace: "nowrap", flexShrink: 0 }}
          >
            {a.episode_id}
          </Typography>
        </Box>
      ))}
    </Box>
  );
}
