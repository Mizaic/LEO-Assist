"use client";

import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Paper from "@mui/material/Paper";
import type { CaseloadSummary } from "@/lib/pathwayRisk";

const ITEMS: Array<{
  key: keyof CaseloadSummary;
  label: string;
  color: string;
  bgColor: string;
}> = [
  { key: "breached", label: "Breached", color: "#dc2626", bgColor: "#fef2f2" },
  { key: "atRisk", label: "At risk", color: "#d97706", bgColor: "#fffbeb" },
  { key: "onTrack", label: "On track", color: "#16a34a", bgColor: "#f0fdf4" },
  { key: "completed", label: "Completed", color: "#6b7280", bgColor: "#f9fafb" },
];

export default function CaseloadSummaryStrip({
  summary,
}: {
  summary: CaseloadSummary;
}) {
  return (
    <Box sx={{ display: "flex", gap: 2, mb: 2.5 }}>
      {ITEMS.map(({ key, label, color, bgColor }) => (
        <Paper
          key={key}
          variant="outlined"
          sx={{
            px: 2.5,
            py: 1.5,
            minWidth: 130,
            borderColor: summary[key] > 0 ? color : "divider",
            borderWidth: summary[key] > 0 ? 2 : 1,
            bgcolor: summary[key] > 0 ? bgColor : "background.paper",
          }}
        >
          <Typography
            variant="h5"
            sx={{ color, fontWeight: 700, lineHeight: 1.2 }}
          >
            {summary[key]}
          </Typography>
          <Typography
            variant="caption"
            sx={{ color: "text.secondary", fontWeight: 500 }}
          >
            {label}
          </Typography>
        </Paper>
      ))}
      <Paper
        variant="outlined"
        sx={{ px: 2.5, py: 1.5, minWidth: 100, borderColor: "divider" }}
      >
        <Typography
          variant="h5"
          sx={{ color: "text.primary", fontWeight: 700, lineHeight: 1.2 }}
        >
          {summary.total}
        </Typography>
        <Typography
          variant="caption"
          sx={{ color: "text.secondary", fontWeight: 500 }}
        >
          Total
        </Typography>
      </Paper>
    </Box>
  );
}
