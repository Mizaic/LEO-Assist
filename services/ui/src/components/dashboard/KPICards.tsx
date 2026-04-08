"use client";

import Box from "@mui/material/Box";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import WarningAmberRoundedIcon from "@mui/icons-material/WarningAmberRounded";
import CheckCircleOutlineRoundedIcon from "@mui/icons-material/CheckCircleOutlineRounded";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";

interface KPIs {
  avg_days_to_referral: number | null;
  n_days_to_referral?: number | null;
  avg_days_to_diagnosis: number | null;
  n_days_to_diagnosis?: number | null;
  avg_days_to_treatment: number | null;
  n_days_to_treatment?: number | null;
  avg_consultations: number | null;
  episode_count: number;
  inferred_diagnosis_count?: number | null;
}

const ITEMS: {
  key: keyof KPIs;
  label: string;
  sublabel: string;
  unit: string;
  target?: number;
  nullNote?: string;
}[] = [
  {
    key: "avg_days_to_referral",
    label: "First presentation to referral",
    sublabel: "Days from first coded cancer-related symptom/sign to referral",
    unit: "days",
    target: 14,
    nullNote: "Requires first-presentation dates to be coded in clinical records",
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
    sublabel: "Days from confirmed diagnosis to first treatment (excludes pathways without both milestones)",
    unit: "days",
    target: 31,
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

  const nByMetric: Record<string, number | null | undefined> = {
    avg_days_to_referral: kpis.n_days_to_referral,
    avg_days_to_diagnosis: kpis.n_days_to_diagnosis,
    avg_days_to_treatment: kpis.n_days_to_treatment,
  };

  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 1.5 }} role="list">
      {ITEMS.map((item) => {
        const metricN = nByMetric[item.key as string];
        const raw = kpis[item.key];
        const val = typeof raw === "number" ? Math.round(raw * 10) / 10 : null;
        // A negative value means the calculation data is inconsistent
        // (e.g. treatment milestones predating diagnosis). Treat as unavailable.
        const plausible = val === null || val >= 0;
        const displayVal = plausible ? val : null;
        const implausible = val !== null && val < 0;

        const breached = item.target != null && displayVal != null && displayVal > item.target;
        const withinTarget = item.target != null && displayVal != null && !breached;

        return (
          <Box
            key={item.key}
            role="listitem"
            aria-label={`${item.label}: ${displayVal != null ? `${displayVal} ${item.unit}` : "no data"}${breached ? " — over NHS target" : ""}`}
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
              {metricN != null && metricN > 0 && (
                <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.35, fontSize: "0.72rem" }}>
                  Based on {metricN} eligible {metricN === 1 ? "pathway" : "pathways"}
                </Typography>
              )}
              {implausible && (
                <Typography variant="caption" sx={{ display: "block", mt: 0.5, color: "warning.dark", fontSize: "0.72rem" }}>
                  Data not yet complete for this metric
                </Typography>
              )}
              {displayVal === null && item.nullNote && (
                <Typography variant="caption" sx={{ display: "block", mt: 0.5, color: "text.disabled", fontSize: "0.72rem" }}>
                  {item.nullNote}
                </Typography>
              )}
            </Box>

            <Box sx={{ textAlign: "right", flexShrink: 0 }}>
              <Box sx={{ display: "flex", alignItems: "center", justifyContent: "flex-end", gap: 0.75 }}>
                {implausible && (
                  <Tooltip title="The calculation returned an unexpected result. Check that diagnosis and treatment milestones are correctly coded in the patient record.">
                    <WarningAmberRoundedIcon sx={{ fontSize: 18, color: "warning.main" }} aria-hidden="true" />
                  </Tooltip>
                )}
                {breached && !implausible && (
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
                {displayVal === null && item.nullNote && !implausible && (
                  <Tooltip title={item.nullNote}>
                    <InfoOutlinedIcon sx={{ fontSize: 16, color: "text.disabled" }} aria-hidden="true" />
                  </Tooltip>
                )}
                <Typography
                  variant="h6"
                  component="span"
                  sx={{
                    fontSize: "1.15rem",
                    fontWeight: 700,
                    color: implausible
                      ? "warning.main"
                      : breached
                        ? "#C2410C"
                        : withinTarget
                          ? "#15803D"
                          : "text.primary",
                  }}
                >
                  {displayVal != null ? `${displayVal}${item.unit ? ` ${item.unit}` : ""}` : "—"}
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
        Cohort size: {kpis.episode_count} referral {kpis.episode_count === 1 ? "pathway" : "pathways"}
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
