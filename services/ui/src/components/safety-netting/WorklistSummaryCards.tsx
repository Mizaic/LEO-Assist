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
import Paper from "@mui/material/Paper";
import Typography from "@mui/material/Typography";

interface WorklistSummary {
  totalActive: number;
  overdueBreached: number;
  atRisk: number;
  onTrack: number;
  actionRequired: number;
}

const ITEMS: Array<{
  key: keyof WorklistSummary;
  label: string;
  color: string;
  bgColor: string;
}> = [
  { key: "totalActive", label: "Total Active", color: "#111827", bgColor: "#f8fafc" },
  { key: "overdueBreached", label: "Overdue / Breached", color: "#dc2626", bgColor: "#fef2f2" },
  { key: "atRisk", label: "At Risk", color: "#d97706", bgColor: "#fffbeb" },
  { key: "onTrack", label: "On Track", color: "#16a34a", bgColor: "#f0fdf4" },
  { key: "actionRequired", label: "Action Required", color: "#7c3aed", bgColor: "#f5f3ff" },
];

export default function WorklistSummaryCards({ summary }: { summary: WorklistSummary }) {
  return (
    <Box sx={{ display: "flex", gap: 2, flexWrap: "wrap", mb: 2.5 }}>
      {ITEMS.map(({ key, label, color, bgColor }) => {
        const val = summary[key];
        return (
          <Paper
            key={key}
            variant="outlined"
            sx={{
              flex: "1 1 130px",
              maxWidth: 210,
              px: 2.5,
              py: 1.5,
              borderColor: val > 0 ? color : "divider",
              borderWidth: val > 0 ? 2 : 1,
              bgcolor: val > 0 ? bgColor : "background.paper",
              borderRadius: 2,
            }}
          >
            <Typography
              variant="h4"
              sx={{
                color: val > 0 ? color : "text.disabled",
                fontWeight: 700,
                lineHeight: 1.1,
                mb: 0.25,
              }}
            >
              {val}
            </Typography>
            <Typography variant="caption" sx={{ color: "text.secondary", fontWeight: 600 }}>
              {label}
            </Typography>
          </Paper>
        );
      })}
    </Box>
  );
}
