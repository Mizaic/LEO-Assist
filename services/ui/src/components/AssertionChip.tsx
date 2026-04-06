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
    color: "#dc2626",
    bg: "#fee2e2",
    tooltip: "This was recorded as absent or ruled out.",
  },
  refuted: {
    label: "Refuted",
    color: "#991b1b",
    bg: "#fecaca",
    tooltip: "Initial impression overridden by subsequent investigation (e.g. biopsy revised the diagnosis).",
  },
  possible: {
    label: "Uncertain",
    color: "#d97706",
    bg: "#fef3c7",
    tooltip: "This was recorded as uncertain or possible.",
  },
  historical: {
    label: "Historical",
    color: "#6b7280",
    bg: "#f3f4f6",
    tooltip: "This was recorded as a past or historical event.",
  },
  planned: {
    label: "Planned / not done",
    color: "#2563eb",
    bg: "#dbeafe",
    tooltip: "This was booked or referred for -- it is confirmed but has not happened yet.",
  },
  hypothetical: {
    label: "Hypothetical",
    color: "#7c3aed",
    bg: "#ede9fe",
    tooltip: "This is a conditional or speculative future event -- it has not been arranged.",
  },
  family: {
    label: "Family history",
    color: "#4f46e5",
    bg: "#ede9fe",
    tooltip: "This was recorded as a family history item, not the patient directly.",
  },
  declined: {
    label: "Patient declined",
    color: "#ea580c",
    bg: "#ffedd5",
    tooltip: "The patient declined this. Search for a 'patient declined' SNOMED code.",
  },
  cancelled: {
    label: "Patient cancelled",
    color: "#ea580c",
    bg: "#ffedd5",
    tooltip: "This appointment or procedure was cancelled. Search for a 'patient cancelled' SNOMED code.",
  },
};

interface Props {
  assertion: string | undefined | null;
  size?: "small" | "medium";
}

/**
 * Shows a coloured chip for any assertion that is not "present".
 * Returns null for present or unknown assertions so callers need no guard.
 */
export default function AssertionChip({ assertion, size = "small" }: Props) {
  if (!assertion || assertion === "present") return null;
  const meta = ASSERTION_META[assertion];
  if (!meta) return null;

  return (
    <Tooltip title={meta.tooltip} arrow placement="top">
      <Chip
        label={meta.label}
        size={size}
        sx={{
          height: size === "small" ? 18 : 24,
          fontSize: size === "small" ? "0.65rem" : "0.75rem",
          fontWeight: 600,
          bgcolor: meta.bg,
          color: meta.color,
          border: `1px solid ${meta.color}40`,
          "& .MuiChip-label": { px: 0.75 },
        }}
      />
    </Tooltip>
  );
}
