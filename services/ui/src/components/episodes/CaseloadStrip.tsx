"use client";

import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import type { CaseloadSummary } from "@/lib/pathwayRisk";

interface Segment {
  label: string;
  count: number;
  color: string;
  bg: string;
}

function buildSegments(summary: CaseloadSummary): Segment[] {
  return [
    {
      label: "Overdue",
      count: summary.breached,
      color: "#dc2626",
      bg: "#fef2f2",
    },
    {
      label: "At risk",
      count: summary.atRisk,
      color: "#d97706",
      bg: "#fffbeb",
    },
    {
      label: "On track",
      count: summary.onTrack,
      color: "#16a34a",
      bg: "#f0fdf4",
    },
    {
      label: "Completed",
      count: summary.completed,
      color: "#6b7280",
      bg: "#f9fafb",
    },
  ];
}

export default function CaseloadStrip({
  summary,
}: {
  summary: CaseloadSummary;
}) {
  const segments = buildSegments(summary);
  const active = summary.total - summary.completed - summary.unknown;

  return (
    <Box sx={{ mb: 2.5 }}>
      <Box
        sx={{
          display: "flex",
          gap: 2,
          mb: 1.5,
        }}
      >
        {segments.map((seg) => (
          <Box
            key={seg.label}
            sx={{
              flex: 1,
              px: 2,
              py: 1.5,
              borderRadius: 2,
              bgcolor: seg.bg,
              borderLeft: "4px solid",
              borderColor: seg.color,
            }}
          >
            <Typography
              variant="h5"
              sx={{ color: seg.color, fontWeight: 700, lineHeight: 1.2 }}
            >
              {seg.count}
            </Typography>
            <Typography
              variant="caption"
              sx={{ color: "text.secondary", fontWeight: 500 }}
            >
              {seg.label}
            </Typography>
          </Box>
        ))}
      </Box>

      {active > 0 && (
        <Box
          sx={{
            display: "flex",
            height: 6,
            borderRadius: 3,
            overflow: "hidden",
            bgcolor: "grey.200",
          }}
        >
          {segments
            .filter((s) => s.label !== "Completed" && s.count > 0)
            .map((seg) => (
              <Box
                key={seg.label}
                sx={{
                  width: `${(seg.count / active) * 100}%`,
                  bgcolor: seg.color,
                  transition: "width 0.4s ease",
                }}
              />
            ))}
        </Box>
      )}
    </Box>
  );
}
