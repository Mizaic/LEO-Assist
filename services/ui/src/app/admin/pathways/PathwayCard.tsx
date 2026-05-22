/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-11232EFB
 *   DI: DI-CD931485
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-11232EFB")
 */
"use client";

/**
 * PathwayCard -- restyled Phase 6 card for one PlanDefinition.
 *
 * Visually consistent with the wider Knowledge tab system:
 * 12px radius, 1px divider border, 3px tone-coded left accent strip,
 * tone-tinted status chip, framer-motion stagger entry.
 *
 * Design Controls: DI-LEO-AI-150, DO-LEO-AI-146, VT-LEO-AI-148.
 */

import { motion as fm } from "framer-motion";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Divider from "@mui/material/Divider";
import IconButton from "@mui/material/IconButton";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import AccountTreeIcon from "@mui/icons-material/AccountTree";
import ArchiveIcon from "@mui/icons-material/Archive";
import CloudUploadIcon from "@mui/icons-material/CloudUpload";
import ContentCopyIcon from "@mui/icons-material/ContentCopy";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import EditIcon from "@mui/icons-material/Edit";
import PlayCircleOutlineIcon from "@mui/icons-material/PlayCircleOutline";
import ReplayIcon from "@mui/icons-material/Replay";

import type { PlanDefinition } from "./types";

interface CardProps {
  plan: PlanDefinition;
  index: number;
  onEdit: () => void;
  onPublish: () => void;
  onDuplicate: () => void;
  onRetire: () => void;
  onReactivate: () => void;
  onDelete: () => void;
  busy: boolean;
}

function statusAccent(status: string): string {
  if (status === "active") return "#16A34A";
  if (status === "draft") return "#D97706";
  if (status === "retired") return "#94A3B8";
  return "#94A3B8";
}

function statusChipStyle(status: string) {
  if (status === "active") {
    return { bg: "#ECFDF5", fg: "#047857", border: "#A7F3D0" };
  }
  if (status === "draft") {
    return { bg: "#FEF3C7", fg: "#92400E", border: "#FDE68A" };
  }
  if (status === "retired") {
    return { bg: "#F1F5F9", fg: "#475569", border: "#E2E8F0" };
  }
  return { bg: "#F1F5F9", fg: "#475569", border: "#E2E8F0" };
}

function statusLabel(status: string): string {
  if (status === "active") return "Live";
  if (status === "draft") return "Draft";
  if (status === "retired") return "Retired";
  return status;
}

function isSeededPathway(plan: Pick<PlanDefinition, "meta" | "source">): boolean {
  return Boolean(plan.meta?.seeded || plan.source === "seed");
}

function workflowModeLabel(mode: string | undefined): string {
  if (mode === "durable_pubsub") return "Durable";
  if (mode === "legacy_in_process") return "Legacy";
  return mode ? mode.replace(/_/g, " ") : "Legacy";
}

export default function PathwayCard({
  plan,
  index,
  onEdit,
  onPublish,
  onDuplicate,
  onRetire,
  onReactivate,
  onDelete,
  busy,
}: CardProps) {
  const accent = statusAccent(plan.status);
  const chip = statusChipStyle(plan.status);
  const actionCount = plan.actionCount ?? plan.actions?.length ?? 0;
  const durableStepCount = plan._durableSteps?.length ?? 0;
  const triggerLabel = plan.trigger?.event?.replace(/-/g, " ") ?? null;
  const isSeeded = isSeededPathway(plan);
  const workflowMode = plan._workflowMode || "legacy_in_process";
  const deprecatedCount = plan._deprecatedSubgraphs?.length ?? 0;

  return (
    <fm.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{
        duration: 0.22,
        ease: "easeOut",
        delay: Math.min(index, 12) * 0.04,
      }}
      whileHover={{ boxShadow: "0 6px 16px rgba(15, 23, 42, 0.08)" }}
      data-testid={`pathway-card-${plan.id}`}
      style={{
        position: "relative",
        background: "#FFFFFF",
        border: "1px solid #E2E8F0",
        borderRadius: 12,
        padding: 18,
      }}
    >
      <span
        aria-hidden="true"
        style={{
          position: "absolute",
          left: 0,
          top: 14,
          bottom: 14,
          width: 3,
          borderRadius: 2,
          background: accent,
        }}
      />
      <Stack direction="row" alignItems="flex-start" spacing={1}>
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Stack
            direction="row"
            alignItems="center"
            spacing={1}
            flexWrap="wrap"
            useFlexGap
          >
            <Typography
              variant="subtitle1"
              sx={{ fontWeight: 700, fontSize: "1rem", lineHeight: 1.3 }}
            >
              {plan.name || "Untitled pathway"}
            </Typography>
            <Chip
              label={statusLabel(plan.status)}
              size="small"
              sx={{
                height: 22,
                fontSize: "0.7rem",
                fontWeight: 600,
                bgcolor: chip.bg,
                color: chip.fg,
                border: `1px solid ${chip.border}`,
              }}
            />
            {isSeeded ? (
              <Chip
                label="Seeded"
                size="small"
                variant="outlined"
                sx={{ height: 22, fontSize: "0.7rem" }}
              />
            ) : null}
            <Chip
              label={workflowModeLabel(workflowMode)}
              size="small"
              color={workflowMode === "durable_pubsub" ? "info" : "default"}
              variant={workflowMode === "durable_pubsub" ? "filled" : "outlined"}
              sx={{ height: 22, fontSize: "0.7rem" }}
            />
            {deprecatedCount > 0 ? (
              <Chip
                label={`${deprecatedCount} deprecated step${deprecatedCount !== 1 ? "s" : ""}`}
                size="small"
                color="warning"
                variant="outlined"
                sx={{ height: 22, fontSize: "0.7rem" }}
              />
            ) : null}
            {plan.version ? (
              <Typography variant="caption" color="text.disabled">
                v{plan.version}
              </Typography>
            ) : null}
          </Stack>
          <Typography
            variant="body2"
            color="text.secondary"
            sx={{ mt: 0.6, fontSize: "0.85rem", lineHeight: 1.5 }}
          >
            {plan.description || "No description yet."}
          </Typography>
        </Box>

        <Button
          size="small"
          variant="outlined"
          startIcon={<EditIcon sx={{ fontSize: "0.95rem !important" }} />}
          onClick={onEdit}
          sx={{ textTransform: "none", flexShrink: 0 }}
        >
          Edit
        </Button>
      </Stack>

      <Stack
        direction="row"
        spacing={1.5}
        sx={{ mt: 1.25 }}
        alignItems="center"
        flexWrap="wrap"
        useFlexGap
      >
        {actionCount > 0 ? (
          <Stack direction="row" alignItems="center" spacing={0.5}>
            <AccountTreeIcon sx={{ fontSize: "0.85rem", color: "text.disabled" }} />
            <Typography variant="caption" color="text.disabled">
              {workflowMode === "durable_pubsub" && durableStepCount > 0
                ? `${durableStepCount} durable step${durableStepCount !== 1 ? "s" : ""}`
                : `${actionCount} step${actionCount !== 1 ? "s" : ""}`}
            </Typography>
          </Stack>
        ) : null}
        {triggerLabel ? (
          <Stack direction="row" alignItems="center" spacing={0.5}>
            <PlayCircleOutlineIcon sx={{ fontSize: "0.85rem", color: "text.disabled" }} />
            <Typography
              variant="caption"
              color="text.disabled"
              sx={{ textTransform: "capitalize" }}
            >
              {triggerLabel}
            </Typography>
          </Stack>
        ) : null}
        {plan.date ? (
          <Typography variant="caption" color="text.disabled">
            Updated {new Date(plan.date).toLocaleDateString()}
          </Typography>
        ) : null}
      </Stack>

      <Divider sx={{ my: 1.5 }} />

      <Stack direction="row" spacing={0.75} alignItems="center">
        {plan.status === "draft" ? (
          <Tooltip title="Publish this draft to live - it will immediately be used by the runtime">
            <span>
              <Button
                size="small"
                variant="contained"
                color="success"
                startIcon={
                  busy ? (
                    <CircularProgress size={11} color="inherit" />
                  ) : (
                    <CloudUploadIcon sx={{ fontSize: "0.95rem !important" }} />
                  )
                }
                disabled={busy}
                onClick={onPublish}
                sx={{ textTransform: "none" }}
              >
                Publish to live
              </Button>
            </span>
          </Tooltip>
        ) : null}

        {plan.status === "active" ? (
          <Tooltip title="Save a draft copy to edit without affecting the live version">
            <Button
              size="small"
              variant="outlined"
              startIcon={<ContentCopyIcon sx={{ fontSize: "0.95rem !important" }} />}
              onClick={onDuplicate}
              disabled={busy}
              sx={{ textTransform: "none" }}
            >
              New draft
            </Button>
          </Tooltip>
        ) : null}

        {plan.status !== "active" ? (
          <Tooltip title="Duplicate as a new draft">
            <IconButton
              size="small"
              onClick={onDuplicate}
              disabled={busy}
              sx={{ color: "text.secondary" }}
            >
              <ContentCopyIcon sx={{ fontSize: "1rem" }} />
            </IconButton>
          </Tooltip>
        ) : null}

        {plan.status === "retired" ? (
          <Tooltip title="Reactivate - publish this back to live">
            <Button
              size="small"
              variant="outlined"
              color="warning"
              startIcon={<ReplayIcon sx={{ fontSize: "0.95rem !important" }} />}
              onClick={onReactivate}
              disabled={busy}
              sx={{ textTransform: "none" }}
            >
              Reactivate
            </Button>
          </Tooltip>
        ) : null}

        <Box sx={{ flex: 1 }} />

        {plan.status !== "retired" ? (
          <Tooltip
            title={
              plan.status === "active"
                ? "Retire this pathway from live use"
                : "Mark as retired"
            }
          >
            <IconButton
              size="small"
              onClick={onRetire}
              disabled={busy}
              sx={{ color: "text.disabled", "&:hover": { color: "error.main" } }}
            >
              <ArchiveIcon sx={{ fontSize: "1rem" }} />
            </IconButton>
          </Tooltip>
        ) : null}
        <Tooltip
          title={
            isSeeded
              ? "Seeded pathways cannot be deleted from the UI"
              : "Delete this pathway permanently"
          }
        >
          <span>
            <IconButton
              size="small"
              onClick={onDelete}
              disabled={busy || isSeeded}
              sx={{ color: "text.disabled", "&:hover": { color: "error.main" } }}
            >
              <DeleteOutlineIcon sx={{ fontSize: "1rem" }} />
            </IconButton>
          </span>
        </Tooltip>
      </Stack>
    </fm.div>
  );
}
