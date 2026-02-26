"use client";

import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";

interface KPIs {
  avg_days_to_referral: number | null;
  avg_days_to_diagnosis: number | null;
  avg_days_to_treatment: number | null;
  avg_consultations: number | null;
  episode_count: number;
}

const ITEMS: { key: keyof KPIs; label: string; unit: string; target?: number }[] = [
  { key: "avg_days_to_referral", label: "Presentation → Referral", unit: "days", target: 14 },
  { key: "avg_days_to_diagnosis", label: "Referral → Diagnosis", unit: "days", target: 28 },
  { key: "avg_days_to_treatment", label: "Diagnosis → Treatment", unit: "days", target: 31 },
  { key: "avg_consultations", label: "Consultations before Referral", unit: "", target: 3 },
];

export default function KPICards({ kpis }: { kpis: KPIs | null }) {
  if (!kpis) {
    return (
      <Typography variant="body2" color="text.secondary">
        No referral quality data available yet. Process patient records to generate indicators.
      </Typography>
    );
  }

  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
      {ITEMS.map((item) => {
        const raw = kpis[item.key];
        const val = typeof raw === "number" ? Math.round(raw * 10) / 10 : null;
        const breached = item.target != null && val != null && val > item.target;
        return (
          <Box
            key={item.key}
            sx={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              px: 2,
              py: 1.5,
              borderRadius: 2,
              bgcolor: breached ? "error.50" : "grey.50",
              border: "1px solid",
              borderColor: breached ? "error.200" : "divider",
            }}
          >
            <Typography variant="body2" sx={{ fontWeight: 500, fontSize: "0.85rem" }}>
              {item.label}
            </Typography>
            <Box sx={{ textAlign: "right" }}>
              <Typography
                variant="h6"
                sx={{ fontSize: "1.1rem", color: breached ? "error.main" : "text.primary" }}
              >
                {val ?? "—"} {item.unit}
              </Typography>
              {item.target != null && (
                <Typography variant="caption" color="text.secondary">
                  target: {item.target} {item.unit}
                </Typography>
              )}
            </Box>
          </Box>
        );
      })}
      <Typography variant="caption" color="text.secondary" sx={{ mt: 1 }}>
        Based on {kpis.episode_count} referral pathways
      </Typography>
    </Box>
  );
}
