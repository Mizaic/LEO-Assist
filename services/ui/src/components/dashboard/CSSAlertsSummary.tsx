"use client";

import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Chip from "@mui/material/Chip";
import Link from "next/link";
import type { CSSAlert } from "@/lib/analyticsApi";

const SEVERITY_COLORS: Record<string, "error" | "warning" | "info" | "default"> = {
  critical: "error",
  high: "error",
  medium: "warning",
  low: "info",
};

export default function CSSAlertsSummary({ alerts }: { alerts: CSSAlert[] }) {
  if (!alerts.length) {
    return (
      <Typography variant="body2" color="text.secondary">
        No safety netting alerts. All referral pathways within expected parameters.
      </Typography>
    );
  }

  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 1.5 }}>
      {alerts.map((a, i) => (
        <Box
          key={`${a.id ?? a.episode_id}-${a.type}-${i}`}
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
            {a.patient_id && (
              <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.25, fontFamily: "monospace" }}>
                Patient: {a.patient_id}
                {a.cancer_type ? ` -- ${a.cancer_type}` : ""}
              </Typography>
            )}
          </Box>
          <Typography
            variant="caption"
            color="text.secondary"
            sx={{ whiteSpace: "nowrap", flexShrink: 0 }}
          >
            {a.episode_id ?? ""}
          </Typography>
        </Box>
      ))}

      <Box sx={{ textAlign: "right", pt: 0.5 }}>
        <Link href="/css" style={{ textDecoration: "none" }}>
          <Typography
            variant="caption"
            sx={{ color: "primary.main", fontWeight: 600, "&:hover": { textDecoration: "underline" } }}
          >
            View all alerts
          </Typography>
        </Link>
      </Box>
    </Box>
  );
}
