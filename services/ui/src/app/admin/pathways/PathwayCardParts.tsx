/**
 * Atlas trace:
 *   DO: DO-11232EFB
 *   DI: DI-CD931485
 */
"use client";

import type { ReactNode } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import IconButton from "@mui/material/IconButton";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import AccountTreeIcon from "@mui/icons-material/AccountTree";
import ArchiveIcon from "@mui/icons-material/Archive";
import CloudUploadIcon from "@mui/icons-material/CloudUpload";
import ContentCopyIcon from "@mui/icons-material/ContentCopy";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import PlayCircleOutlineIcon from "@mui/icons-material/PlayCircleOutline";
import ReplayIcon from "@mui/icons-material/Replay";
import { color, typography } from "@leo/design-system/tokens";

import type { PlanDefinition } from "./types";

export function statusAccent(status: string): string {
  if (status === "active") return color.status.success;
  if (status === "draft") return color.status.warning;
  return color.text.disabled;
}

export function statusLabel(status: string): string {
  if (status === "active") return "Live";
  if (status === "draft") return "Draft";
  if (status === "retired") return "Retired";
  return status;
}

export function isSeededPathway(plan: Pick<PlanDefinition, "meta" | "source">): boolean {
  return Boolean(plan.meta?.seeded || plan.source === "seed");
}

export function workflowModeLabel(mode: string | undefined): string {
  if (mode === "durable_pubsub") return "Durable";
  if (mode === "legacy_in_process") return "Legacy";
  return mode ? mode.replace(/_/g, " ") : "Legacy";
}

export function StatusChip({ status }: { status: string }) {
  const fg =
    status === "active"
      ? color.status.success
      : status === "draft"
        ? color.status.warning
        : color.status.neutral;
  return <ToneChip label={statusLabel(status)} fg={fg} />;
}

export function ToneChip({
  label,
  fg = color.text.secondary,
}: {
  label: string;
  fg?: string;
}) {
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        height: 22,
        fontSize: 11,
        fontWeight: 600,
        background: color.surface.alt,
        color: fg,
        border: "1px solid " + color.text.secondary,
        borderRadius: 999,
        padding: "0 8px",
        fontFamily: typography.fontFamily.body,
      }}
    >
      {label}
    </span>
  );
}

export function PathwayMeta({ plan }: { plan: PlanDefinition }) {
  const actionCount = plan.actionCount ?? plan.actions?.length ?? 0;
  const durableStepCount = plan._durableSteps?.length ?? 0;
  const triggerLabel = plan.trigger?.event?.replace(/-/g, " ") ?? null;
  const workflowMode = plan._workflowMode || "legacy_in_process";
  return (
    <Stack direction="row" spacing={1.5} sx={{ mt: 1.25 }} alignItems="center" flexWrap="wrap" useFlexGap>
      {actionCount > 0 ? (
        <MetaItem
          icon={<AccountTreeIcon sx={{ fontSize: "0.85rem", color: color.text.disabled }} />}
          text={
            workflowMode === "durable_pubsub" && durableStepCount > 0
              ? `${durableStepCount} durable step${durableStepCount !== 1 ? "s" : ""}`
              : `${actionCount} step${actionCount !== 1 ? "s" : ""}`
          }
        />
      ) : null}
      {triggerLabel ? (
        <MetaItem
          icon={<PlayCircleOutlineIcon sx={{ fontSize: "0.85rem", color: color.text.disabled }} />}
          text={triggerLabel}
          capitalize
        />
      ) : null}
      {plan.date ? (
        <Typography variant="caption" sx={{ color: color.text.disabled }}>
          Updated {new Date(plan.date).toLocaleDateString()}
        </Typography>
      ) : null}
    </Stack>
  );
}

function MetaItem({
  icon,
  text,
  capitalize,
}: {
  icon: ReactNode;
  text: string;
  capitalize?: boolean;
}) {
  return (
    <Stack direction="row" alignItems="center" spacing={0.5}>
      {icon}
      <Typography
        variant="caption"
        sx={{ color: color.text.disabled, textTransform: capitalize ? "capitalize" : "none" }}
      >
        {text}
      </Typography>
    </Stack>
  );
}

export interface PathwayCardActionProps {
  plan: PlanDefinition;
  busy: boolean;
  isSeeded: boolean;
  onPublish: () => void;
  onDuplicate: () => void;
  onRetire: () => void;
  onReactivate: () => void;
  onDelete: () => void;
}

export function PathwayCardActions(props: PathwayCardActionProps) {
  return (
    <Stack direction="row" spacing={0.75} alignItems="center">
      <PrimaryActions {...props} />
      <Box sx={{ flex: 1 }} />
      <DangerActions {...props} />
    </Stack>
  );
}

function PrimaryActions(props: PathwayCardActionProps) {
  return (
    <>
      <PublishLiveButton {...props} />
      <DuplicateActions {...props} />
      <ReactivateButton {...props} />
    </>
  );
}

function PublishLiveButton({ plan, busy, onPublish }: PathwayCardActionProps) {
  if (plan.status !== "draft") return null;
  return (
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
  );
}

function DuplicateActions({ plan, busy, onDuplicate }: PathwayCardActionProps) {
  if (plan.status === "active") {
    return (
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
    );
  }
  return (
    <Tooltip title="Duplicate as a new draft">
      <IconButton size="small" onClick={onDuplicate} disabled={busy} sx={{ color: color.text.secondary }}>
        <ContentCopyIcon sx={{ fontSize: "1rem" }} />
      </IconButton>
    </Tooltip>
  );
}

function ReactivateButton({ plan, busy, onReactivate }: PathwayCardActionProps) {
  if (plan.status !== "retired") return null;
  return (
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
  );
}

function DangerActions({
  plan,
  busy,
  isSeeded,
  onRetire,
  onDelete,
}: PathwayCardActionProps) {
  return (
    <>
      {plan.status !== "retired" ? (
        <Tooltip
          title={plan.status === "active" ? "Retire this pathway from live use" : "Mark as retired"}
        >
          <IconButton
            size="small"
            onClick={onRetire}
            disabled={busy}
            sx={{ color: color.text.disabled, "&:hover": { color: "error.main" } }}
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
            sx={{ color: color.text.disabled, "&:hover": { color: "error.main" } }}
          >
            <DeleteOutlineIcon sx={{ fontSize: "1rem" }} />
          </IconButton>
        </span>
      </Tooltip>
    </>
  );
}
