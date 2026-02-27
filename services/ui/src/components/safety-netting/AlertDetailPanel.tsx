"use client";

import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Chip from "@mui/material/Chip";
import Button from "@mui/material/Button";
import Divider from "@mui/material/Divider";
import IconButton from "@mui/material/IconButton";
import CloseIcon from "@mui/icons-material/Close";
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutline";
import UndoIcon from "@mui/icons-material/Undo";
import OpenInNewIcon from "@mui/icons-material/OpenInNew";
import Link from "next/link";
import type { SafetyNetAlert } from "@/lib/analyticsApi";

const SEVERITY_COLORS: Record<string, "error" | "warning" | "info" | "default"> = {
  critical: "error",
  high: "error",
  medium: "warning",
  low: "info",
};

interface AlertDetailPanelProps {
  alert: SafetyNetAlert;
  onClose: () => void;
  onAction: (alertId: string, actioned: boolean) => void;
  actionLoading: boolean;
}

/** Safely render a date value that may be a string or a serialized DateTime object. */
function formatDateValue(value: unknown): string {
  if (value == null) return "-";
  if (typeof value === "string") return value;
  if (typeof value === "object" && value !== null && "_DateTime__date" in value) {
    const d = value as { _DateTime__date?: string; _DateTime__time?: string };
    const date = d._DateTime__date ?? "";
    const time = d._DateTime__time ?? "";
    return time ? `${date}T${time}` : date;
  }
  return String(value);
}

function DetailRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <Box sx={{ display: "flex", gap: 1, py: 1 }}>
      <Typography
        variant="caption"
        sx={{ width: 120, flexShrink: 0, color: "text.secondary", fontWeight: 500, pt: 0.25 }}
      >
        {label}
      </Typography>
      <Box sx={{ flex: 1, minWidth: 0 }}>{children}</Box>
    </Box>
  );
}

export default function AlertDetailPanel({
  alert,
  onClose,
  onAction,
  actionLoading,
}: AlertDetailPanelProps) {
  return (
    <Box
      sx={{
        width: 420,
        flexShrink: 0,
        borderLeft: "1px solid",
        borderColor: "divider",
        bgcolor: "background.paper",
        overflow: "auto",
        display: "flex",
        flexDirection: "column",
      }}
    >
      <Box
        sx={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          px: 2.5,
          py: 2,
          borderBottom: "1px solid",
          borderColor: "divider",
        }}
      >
        <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
          Alert Detail
        </Typography>
        <IconButton size="small" onClick={onClose} aria-label="close detail panel">
          <CloseIcon sx={{ fontSize: 18 }} />
        </IconButton>
      </Box>

      <Box sx={{ px: 2.5, py: 2, flex: 1, overflow: "auto" }}>
        <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 2 }}>
          <Chip
            label={alert.severity}
            size="small"
            color={SEVERITY_COLORS[alert.severity] ?? "default"}
            sx={{ textTransform: "capitalize" }}
          />
          {alert.actioned && (
            <Chip label="Actioned" size="small" color="success" variant="outlined" />
          )}
          {alert.needs_review && (
            <Chip label="Needs review" size="small" color="warning" variant="outlined" />
          )}
        </Box>

        <Typography variant="body1" sx={{ fontWeight: 600, mb: 0.5, fontSize: "0.95rem" }}>
          {alert.type}
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          {alert.description}
        </Typography>

        <Divider sx={{ my: 1.5 }} />

        {alert.suggested_action && (
          <DetailRow label="Suggested action">
            <Typography variant="body2" sx={{ fontSize: "0.85rem" }}>
              {alert.suggested_action}
            </Typography>
          </DetailRow>
        )}

        {alert.guideline && (
          <DetailRow label="Guideline">
            <Typography variant="body2" sx={{ fontSize: "0.85rem" }}>
              {alert.guideline}
            </Typography>
          </DetailRow>
        )}

        {alert.patient_id && (
          <DetailRow label="Patient">
            <Link href={`/patients/${alert.patient_id}`} style={{ textDecoration: "none" }}>
              <Typography
                variant="body2"
                sx={{
                  fontFamily: "monospace",
                  fontSize: "0.85rem",
                  color: "primary.main",
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 0.5,
                  "&:hover": { textDecoration: "underline" },
                }}
              >
                {alert.patient_id}
                <OpenInNewIcon sx={{ fontSize: 14 }} />
              </Typography>
            </Link>
          </DetailRow>
        )}

        {alert.condition_type && (
          <DetailRow label="Cancer type">
            <Typography variant="body2" sx={{ fontSize: "0.85rem" }}>
              {alert.condition_type}
            </Typography>
          </DetailRow>
        )}

        {alert.episode_id && (
          <DetailRow label="Pathway">
            <Link href={`/episodes?id=${alert.episode_id}`} style={{ textDecoration: "none" }}>
              <Typography
                variant="body2"
                sx={{
                  fontFamily: "monospace",
                  fontSize: "0.85rem",
                  color: "primary.main",
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 0.5,
                  "&:hover": { textDecoration: "underline" },
                }}
              >
                {alert.episode_id}
                <OpenInNewIcon sx={{ fontSize: 14 }} />
              </Typography>
            </Link>
          </DetailRow>
        )}

        {alert.encounter_date != null && (
          <DetailRow label="Encounter date">
            <Typography variant="body2" sx={{ fontSize: "0.85rem" }}>
              {formatDateValue(alert.encounter_date)}
            </Typography>
          </DetailRow>
        )}

        {alert.created_at != null && (
          <DetailRow label="Flagged">
            <Typography variant="body2" sx={{ fontSize: "0.85rem" }}>
              {formatDateValue(alert.created_at)}
            </Typography>
          </DetailRow>
        )}

        {alert.match_percent != null && (
          <DetailRow label="Confidence">
            <Typography variant="body2" sx={{ fontSize: "0.85rem" }}>
              {Math.round(alert.match_percent * 100)}%
            </Typography>
          </DetailRow>
        )}
      </Box>

      <Box
        sx={{
          px: 2.5,
          py: 2,
          borderTop: "1px solid",
          borderColor: "divider",
          display: "flex",
          gap: 1,
        }}
      >
        {alert.actioned ? (
          <Button
            variant="outlined"
            size="small"
            startIcon={<UndoIcon />}
            disabled={actionLoading}
            onClick={() => onAction(alert.id, false)}
            fullWidth
          >
            Mark outstanding
          </Button>
        ) : (
          <Button
            variant="contained"
            size="small"
            startIcon={<CheckCircleOutlineIcon />}
            disabled={actionLoading}
            onClick={() => onAction(alert.id, true)}
            fullWidth
          >
            Mark actioned
          </Button>
        )}
      </Box>
    </Box>
  );
}
