/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-30A82196
 *   DI: DI-85B110A5
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-30A82196")
 */
"use client";

import Chip from "@mui/material/Chip";
import Tooltip from "@mui/material/Tooltip";

interface AssertionMeta {
  label: string;
  color: string;
  bg: string;
  tooltip: string;
}

const ASSERTION_META: Record<string, AssertionMeta> = {
  absent: {
    label: "Not present",
    color: "#991b1b",
    bg: "#fee2e2",
    tooltip: "This was recorded as absent or ruled out.",
  },
  refuted: {
    label: "Refuted",
    color: "#7f1d1d",
    bg: "#fecaca",
    tooltip:
      "Initial impression overridden by later investigation (for example a biopsy revised the diagnosis).",
  },
  possible: {
    label: "Uncertain",
    color: "#92400e",
    bg: "#fef3c7",
    tooltip: "This was recorded as uncertain or possible.",
  },
  historical: {
    label: "Historical",
    color: "#374151",
    bg: "#f3f4f6",
    tooltip: "This was recorded as a past or historical event.",
  },
  planned: {
    label: "Planned / not done",
    color: "#1d4ed8",
    bg: "#dbeafe",
    tooltip:
      "This was booked or referred for; it is confirmed but has not happened yet.",
  },
  hypothetical: {
    label: "Hypothetical",
    color: "#5b21b6",
    bg: "#ede9fe",
    tooltip:
      "This is a conditional or speculative future event; it has not been arranged.",
  },
  family: {
    label: "Family history",
    color: "#3730a3",
    bg: "#e0e7ff",
    tooltip:
      "This was recorded as a family history item, not the patient directly.",
  },
  declined: {
    label: "Patient declined",
    color: "#9a3412",
    bg: "#ffedd5",
    tooltip:
      "The patient declined this. Search for a 'patient declined' SNOMED code.",
  },
  cancelled: {
    label: "Patient cancelled",
    color: "#9a3412",
    bg: "#ffedd5",
    tooltip:
      "This appointment or procedure was cancelled. Search for a 'patient cancelled' SNOMED code.",
  },
};

interface Props {
  assertion: string | undefined | null;
  size?: "small" | "medium";
}

/**
 * Shows a coloured chip for any assertion that is not "present".
 * Returns null for present or unknown assertions so callers need no guard.
 *
 * Minimum font size is 12px (0.75rem) per DI-LEO-AI-118. Contrast pairs
 * used here are WCAG AA normal-text compliant against their bg tokens.
 */
export default function AssertionChip({ assertion, size = "small" }: Props) {
  if (!assertion || assertion === "present") return null;
  const meta = ASSERTION_META[assertion];
  if (!meta) return null;

  const isSmall = size === "small";
  return (
    <Tooltip title={meta.tooltip} arrow placement="top">
      <Chip
        label={meta.label}
        size={size}
        aria-label={`${meta.label}: ${meta.tooltip}`}
        sx={{
          height: isSmall ? 22 : 26,
          fontSize: isSmall ? "0.75rem" : "0.8125rem",
          fontWeight: 600,
          bgcolor: meta.bg,
          color: meta.color,
          border: `1px solid ${meta.color}66`,
          "& .MuiChip-label": { px: 0.9 },
        }}
      />
    </Tooltip>
  );
}
