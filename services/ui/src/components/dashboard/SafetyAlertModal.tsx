"use client";

import { useState } from "react";
import Link from "next/link";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Divider from "@mui/material/Divider";
import IconButton from "@mui/material/IconButton";
import Typography from "@mui/material/Typography";
import CloseIcon from "@mui/icons-material/Close";
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

function humaniseType(raw: string | null | undefined): string {
  if (!raw) return "Alert";
  return raw.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function humaniseCancerType(raw: string | null | undefined): string {
  if (!raw) return "";
  return raw.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

interface Props {
  alert: SafetyNetAlert | null;
  onClose: () => void;
  onAction: (alertId: string, actioned: boolean) => Promise<void>;
}

export default function SafetyAlertModal({ alert, onClose, onAction }: Props) {
  const [actionLoading, setActionLoading] = useState(false);
  const [actionSuccess, setActionSuccess] = useState(false);

  const open = alert !== null;

  const handleAction = async () => {
    if (!alert) return;
    setActionLoading(true);
    try {
      await onAction(alert.id, true);
      setActionSuccess(true);
      setTimeout(() => {
        setActionSuccess(false);
        onClose();
      }, 1200);
    } finally {
      setActionLoading(false);
    }
  };

  const handleClose = () => {
    setActionSuccess(false);
    onClose();
  };

  if (!alert) return null;

  const severityLabel = SEVERITY_LABEL[alert.severity] ?? humaniseType(alert.severity);
  const alertTitle = alert.description || humaniseType(alert.rule_name) || humaniseType(alert.type);
  const cancerType = humaniseCancerType(alert.condition_type);
  const isActioned = alert.actioned || actionSuccess;

  // Build the deepest available link: encounter > patient > safety-netting
  const pathwayHref =
    alert.patient_id && alert.encounter_id
      ? `/care/patients/${alert.patient_id}/encounters/${alert.encounter_id}`
      : alert.patient_id
        ? `/care/patients/${alert.patient_id}`
        : "/care/safety-netting";

  return (
    <Dialog
      open={open}
      onClose={handleClose}
      maxWidth="sm"
      fullWidth
      aria-labelledby="safety-alert-dialog-title"
    >
      {/* ── Header ────────────────────────────────────────────────────── */}
      <DialogTitle
        id="safety-alert-dialog-title"
        sx={{ display: "flex", alignItems: "flex-start", gap: 1.5, pr: 6, pb: 1.5 }}
      >
        <Chip
          label={severityLabel}
          size="small"
          color={SEVERITY_COLOR[alert.severity] ?? "default"}
          sx={{ fontWeight: 700, fontSize: "0.72rem", mt: 0.25, flexShrink: 0 }}
        />
        <Typography
          component="span"
          sx={{ fontWeight: 700, fontSize: "1rem", lineHeight: 1.35, flex: 1 }}
        >
          {alertTitle}
        </Typography>
        <IconButton
          aria-label="Close alert detail"
          onClick={handleClose}
          size="small"
          sx={{ position: "absolute", top: 12, right: 12 }}
        >
          <CloseIcon fontSize="small" />
        </IconButton>
      </DialogTitle>

      <DialogContent dividers sx={{ pt: 2 }}>
        {/* ── Alert detail section ──────────────────────────────────── */}
        <Typography
          variant="overline"
          color="text.secondary"
          sx={{ display: "block", mb: 1, letterSpacing: 0.8, fontSize: "0.68rem" }}
        >
          What triggered this alert
        </Typography>

        <Box sx={{ display: "flex", flexDirection: "column", gap: 0.75, mb: 2 }}>
          {alert.patient_id && (
            <DetailRow label="Patient" value={alert.patient_id} />
          )}
          {cancerType && (
            <DetailRow label="Cancer type" value={cancerType} />
          )}
          {alert.rule_name && (
            <DetailRow label="Rule" value={humaniseType(alert.rule_name)} />
          )}
          {alert.description && (
            <DetailRow label="Description" value={alert.description} />
          )}
          {alert.guideline && (
            <DetailRow label="Guideline" value={alert.guideline} />
          )}
          {alert.match_percent != null && (
            <DetailRow label="Match confidence" value={`${Math.round(alert.match_percent)}%`} />
          )}
          {alert.encounter_date && (
            <DetailRow
              label="Encounter date"
              value={new Date(alert.encounter_date).toLocaleDateString("en-GB", {
                day: "numeric",
                month: "short",
                year: "numeric",
              })}
            />
          )}
          {alert.created_at && (
            <DetailRow
              label="Alert raised"
              value={new Date(alert.created_at).toLocaleDateString("en-GB", {
                day: "numeric",
                month: "short",
                year: "numeric",
              })}
            />
          )}
          <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 2 }}>
            <Typography variant="caption" color="text.secondary" sx={{ flexShrink: 0 }}>
              Status
            </Typography>
            <Chip
              size="small"
              label={isActioned ? "Actioned" : "Outstanding"}
              color={isActioned ? "success" : "warning"}
              variant="outlined"
              sx={{ fontSize: "0.7rem", height: 20 }}
            />
          </Box>
        </Box>

        <Divider sx={{ mb: 2 }} />

        {/* ── Suggested action section ──────────────────────────────── */}
        <Typography
          variant="overline"
          color="text.secondary"
          sx={{ display: "block", mb: 1, letterSpacing: 0.8, fontSize: "0.68rem" }}
        >
          Suggested action
        </Typography>

        {actionSuccess ? (
          <Alert severity="success" sx={{ fontSize: "0.85rem" }}>
            Action recorded successfully.
          </Alert>
        ) : (
          <Alert severity="warning" sx={{ fontSize: "0.85rem" }}>
            {alert.suggested_action ??
              "No automated action suggested. Refer to your local safety-netting protocol."}
          </Alert>
        )}
      </DialogContent>

      {/* ── Actions ──────────────────────────────────────────────────── */}
      <DialogActions sx={{ px: 3, py: 2, gap: 1, flexWrap: "wrap" }}>
        <Button
          variant="contained"
          onClick={handleAction}
          disabled={isActioned || actionLoading}
          aria-label="Record that action has been taken for this alert"
        >
          {actionLoading ? "Saving…" : isActioned ? "Actioned" : "Record Action Taken"}
        </Button>
        <Button
          variant="outlined"
          component={Link}
          href={pathwayHref}
          onClick={handleClose}
          aria-label="Open the patient encounter that triggered this alert"
        >
          View Full Pathway →
        </Button>
        <Button variant="text" onClick={handleClose}>
          Cancel
        </Button>
      </DialogActions>
    </Dialog>
  );
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <Box sx={{ display: "flex", justifyContent: "space-between", gap: 2 }}>
      <Typography variant="caption" color="text.secondary" sx={{ flexShrink: 0 }}>
        {label}
      </Typography>
      <Typography
        variant="caption"
        sx={{ fontWeight: 600, textAlign: "right", wordBreak: "break-all" }}
      >
        {value}
      </Typography>
    </Box>
  );
}
