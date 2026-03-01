"use client";

import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Chip from "@mui/material/Chip";
import Link from "next/link";
import type { SafetyNetAlert } from "@/lib/analyticsApi";

const SEVERITY_COLOR: Record<string, "error" | "warning" | "info" | "default"> = {
  critical: "error",
  high: "error",
  medium: "warning",
  low: "info",
};

const SEVERITY_LABEL: Record<string, string> = {
  critical: "Urgent",
  high: "High priority",
  medium: "Medium priority",
  low: "Low priority",
};

/** Convert snake_case/technical codes into plain-English phrases. */
function humaniseType(raw: string | null | undefined): string {
  if (!raw) return "Alert";
  return raw
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function humaniseCancerType(raw: string | null | undefined): string {
  if (!raw) return "";
  return raw.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export default function SafetyNetAlertsSummary({ alerts }: { alerts: SafetyNetAlert[] }) {
  if (!alerts.length) {
    return (
      <Typography variant="body2" color="text.secondary">
        No safety alerts at the moment. All referral pathways are within expected guidelines.
      </Typography>
    );
  }

  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 1 }} role="list" aria-label="Recent safety alerts">
      {alerts.map((a, i) => {
        const severityLabel = SEVERITY_LABEL[a.severity] ?? humaniseType(a.severity);
        const alertTitle = a.description || humaniseType(a.rule_name) || humaniseType(a.type);
        const cancerType = humaniseCancerType(a.condition_type);

        return (
          <Box
            key={`${a.id ?? a.episode_id}-${i}`}
            role="listitem"
            aria-label={`${severityLabel} alert: ${alertTitle}${cancerType ? `, ${cancerType}` : ""}`}
            sx={{
              display: "flex",
              alignItems: "flex-start",
              gap: 1.5,
              px: 2,
              py: 1.25,
              borderRadius: 2,
              border: "1px solid",
              borderColor: "divider",
              transition: "background-color 0.15s",
              "&:hover": { bgcolor: "grey.50" },
              "&:focus-within": { outline: "2px solid", outlineColor: "primary.main", outlineOffset: 1 },
            }}
          >
            {/* Severity badge */}
            <Chip
              label={severityLabel}
              size="small"
              color={SEVERITY_COLOR[a.severity] ?? "default"}
              aria-label={`Priority: ${severityLabel}`}
              sx={{ minWidth: 88, fontWeight: 600, fontSize: "0.72rem" }}
            />

            {/* Main content */}
            <Box sx={{ flex: 1, minWidth: 0 }}>
              <Typography variant="body2" sx={{ fontWeight: 600, fontSize: "0.85rem", lineHeight: 1.3 }}>
                {alertTitle}
              </Typography>
              {cancerType && (
                <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.25 }}>
                  Cancer type: {cancerType}
                </Typography>
              )}
              {a.suggested_action && (
                <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.25 }}>
                  Suggested action: {a.suggested_action}
                </Typography>
              )}
            </Box>

            {/* Date */}
            {a.created_at && (
              <Typography
                variant="caption"
                color="text.secondary"
                sx={{ whiteSpace: "nowrap", flexShrink: 0, fontSize: "0.75rem" }}
                aria-label={`Raised on ${new Date(a.created_at).toLocaleDateString("en-GB")}`}
              >
                {new Date(a.created_at).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" })}
              </Typography>
            )}
          </Box>
        );
      })}

      <Box sx={{ textAlign: "right", pt: 0.5 }}>
        <Link href="/safety-netting" style={{ textDecoration: "none" }}>
          <Typography
            variant="caption"
            sx={{
              color: "primary.main",
              fontWeight: 700,
              "&:hover": { textDecoration: "underline" },
              "&:focus": { outline: "2px solid", outlineColor: "primary.main", outlineOffset: 2 },
            }}
          >
            View all safety alerts →
          </Typography>
        </Link>
      </Box>
    </Box>
  );
}
