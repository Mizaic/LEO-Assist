"use client";

import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import WarningAmberRoundedIcon from "@mui/icons-material/WarningAmberRounded";
import CheckCircleOutlineRoundedIcon from "@mui/icons-material/CheckCircleOutlineRounded";

interface KPIs {
  avg_days_to_referral: number | null;
  avg_days_to_diagnosis: number | null;
  avg_days_to_treatment: number | null;
  avg_consultations: number | null;
  episode_count: number;
  inferred_diagnosis_count?: number | null;
}

const ITEMS: { key: keyof KPIs; label: string; sublabel: string; unit: string; target?: number }[] = [
  {
    key: "avg_days_to_referral",
    label: "First appointment to referral",
    sublabel: "Days from first GP visit to cancer referral being sent",
    unit: "days",
    target: 14,
  },
  {
    key: "avg_days_to_diagnosis",
    label: "Referral to diagnosis",
    sublabel: "Days from referral to a confirmed or ruled-out diagnosis",
    unit: "days",
    target: 28,
  },
  {
    key: "avg_days_to_treatment",
    label: "Diagnosis to treatment start",
    sublabel: "Days from confirmed diagnosis to first treatment",
    unit: "days",
    target: 31,
  },
  {
    key: "avg_consultations",
    label: "GP visits before referral",
    sublabel: "Average number of GP appointments before the referral was sent",
    unit: "",
    target: 3,
  },
];

export default function KPICards({ kpis }: { kpis: KPIs | null }) {
  if (!kpis) {
    return (
      <Typography variant="body2" color="text.secondary">
        No waiting time data is available yet. Run the analysis pipeline to generate these figures.
      </Typography>
    );
  }

  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 1.5 }} role="list">
      {ITEMS.map((item) => {
        const raw = kpis[item.key];
        const val = typeof raw === "number" ? Math.round(raw * 10) / 10 : null;
        const breached = item.target != null && val != null && val > item.target;
        const withinTarget = item.target != null && val != null && !breached;

        return (
          <Box
            key={item.key}
            role="listitem"
            aria-label={`${item.label}: ${val != null ? `${val} ${item.unit}` : "no data"}${breached ? " — over NHS target" : ""}`}
            sx={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "flex-start",
              gap: 2,
              px: 2,
              py: 1.5,
              borderRadius: 2,
              bgcolor: breached ? "#FFF7ED" : "grey.50",
              border: "1px solid",
              borderColor: breached ? "#FDBA74" : "divider",
            }}
          >
            <Box sx={{ flex: 1, minWidth: 0 }}>
              <Typography variant="body2" sx={{ fontWeight: 600, fontSize: "0.85rem", lineHeight: 1.3 }}>
                {item.label}
              </Typography>
              <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.25, fontSize: "0.75rem" }}>
                {item.sublabel}
              </Typography>
            </Box>

            <Box sx={{ textAlign: "right", flexShrink: 0 }}>
              <Box sx={{ display: "flex", alignItems: "center", justifyContent: "flex-end", gap: 0.75 }}>
                {breached && (
                  <WarningAmberRoundedIcon
                    sx={{ fontSize: 18, color: "#C2410C" }}
                    aria-hidden="true"
                    titleAccess="Over NHS target"
                  />
                )}
                {withinTarget && (
                  <CheckCircleOutlineRoundedIcon
                    sx={{ fontSize: 18, color: "#15803D" }}
                    aria-hidden="true"
                    titleAccess="Within NHS target"
                  />
                )}
                <Typography
                  variant="h6"
                  component="span"
                  sx={{
                    fontSize: "1.15rem",
                    fontWeight: 700,
                    color: breached ? "#C2410C" : withinTarget ? "#15803D" : "text.primary",
                  }}
                >
                  {val != null ? `${val}${item.unit ? ` ${item.unit}` : ""}` : "—"}
                </Typography>
              </Box>
              {item.target != null && (
                <Typography variant="caption" color="text.secondary" sx={{ fontSize: "0.73rem" }}>
                  NHS target: {item.target}{item.unit ? ` ${item.unit}` : ""}
                </Typography>
              )}
            </Box>
          </Box>
        );
      })}

      <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: "block" }}>
        Calculated from {kpis.episode_count} referral {kpis.episode_count === 1 ? "pathway" : "pathways"}
        {kpis.inferred_diagnosis_count != null && kpis.inferred_diagnosis_count > 0 && (
          <Box
            component="span"
            sx={{ ml: 0.75, color: "#B45309", fontStyle: "italic" }}
            title="Referral-to-diagnosis interval includes episodes where the outcome was inferred from post-clinic encounter text, not a coded diagnosis. Review these in the audit tab."
          >
            (incl. {kpis.inferred_diagnosis_count} inferred)
          </Box>
        )}
      </Typography>
    </Box>
  );
}
