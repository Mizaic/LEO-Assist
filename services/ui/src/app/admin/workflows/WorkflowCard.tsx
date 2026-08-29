"use client";

import type { CSSProperties } from "react";
import { motion as fm } from "framer-motion";
import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import IconButton from "@mui/material/IconButton";
import Tooltip from "@mui/material/Tooltip";
import EditIcon from "@mui/icons-material/Edit";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import AccountTreeOutlinedIcon from "@mui/icons-material/AccountTreeOutlined";
import SmartToyOutlinedIcon from "@mui/icons-material/SmartToyOutlined";
import PersonOutlineIcon from "@mui/icons-material/PersonOutline";
import { springOrInstant, springs, tapScale, useMotion } from "@leo/design-system";
import { color, elevation, typography } from "@leo/design-system/tokens";
import type { Workflow } from "./types";
import { workflowTitle } from "./workflowDisplay";

interface WorkflowCardProps {
  workflow: Workflow;
  index: number;
  onEdit: () => void;
  onDelete: () => void;
}

const ACCENT = color.brand.primary; // Electric Blue

export default function WorkflowCard({
  workflow,
  index,
  onEdit,
  onDelete,
}: WorkflowCardProps) {
  const { reducedMotion } = useMotion();
  const enter = springOrInstant(reducedMotion, springs.ui);

  const title = workflowTitle(workflow);
  const createdDate = workflow.createdAt
    ? new Date(workflow.createdAt).toLocaleDateString("en-GB", {
        day: "numeric",
        month: "short",
        year: "numeric",
      })
    : null;
  const showServiceChip =
    Boolean(workflow.serviceName) && workflow.serviceName !== title;

  return (
    <fm.div
      initial={reducedMotion ? false : { opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ ...enter, delay: reducedMotion ? 0 : Math.min(index, 12) * 0.04 }}
      whileTap={tapScale(reducedMotion)}
      data-testid={`workflow-card-${workflow.id}`}
      style={cardStyle()}
    >
      {/* Tone accent strip */}
      <span
        aria-hidden="true"
        style={{
          position: "absolute",
          left: 0,
          top: 14,
          bottom: 14,
          width: 3,
          borderRadius: 2,
          background: ACCENT,
        }}
      />

      <Stack direction="row" alignItems="flex-start" spacing={1.5}>
        <Box
          sx={{
            width: 40,
            height: 40,
            borderRadius: 2,
            bgcolor: "rgba(13, 70, 214, 0.08)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            flexShrink: 0,
          }}
        >
          <AccountTreeOutlinedIcon sx={{ color: ACCENT, fontSize: 22 }} />
        </Box>

        <Stack sx={{ flex: 1, minWidth: 0 }}>
          <Stack direction="row" alignItems="center" spacing={1} flexWrap="wrap" useFlexGap>
            <Typography
              variant="subtitle1"
              component="h2"
              sx={{
                fontWeight: 700,
                fontSize: "1rem",
                lineHeight: 1.3,
                fontFamily: typography.fontFamily.heading,
                color: color.text.primary,
              }}
            >
              {title}
            </Typography>
            {showServiceChip && (
              <Chip
                size="small"
                label={workflow.serviceName}
                sx={{ fontSize: "0.72rem", height: 20 }}
              />
            )}
          </Stack>

          <Stack direction="row" spacing={2} sx={{ mt: 0.8 }}>
            <Stack direction="row" alignItems="center" spacing={0.4}>
              <SmartToyOutlinedIcon sx={{ fontSize: 14, color: color.text.secondary }} />
              <Typography variant="caption" sx={{ color: color.text.secondary }}>
                {workflow.stepCount ?? 0} agent step
                {(workflow.stepCount ?? 0) !== 1 ? "s" : ""}
              </Typography>
            </Stack>
            <Stack direction="row" alignItems="center" spacing={0.4}>
              <PersonOutlineIcon sx={{ fontSize: 14, color: color.text.secondary }} />
              <Typography variant="caption" sx={{ color: color.text.secondary }}>
                {workflow.humanCount ?? 0} human gate
                {(workflow.humanCount ?? 0) !== 1 ? "s" : ""}
              </Typography>
            </Stack>
            {createdDate && (
              <Typography variant="caption" sx={{ color: color.text.disabled }}>
                Created {createdDate}
              </Typography>
            )}
          </Stack>
        </Stack>

        <Stack direction="row" spacing={0.5} alignItems="center" flexShrink={0}>
          <Button
            size="small"
            variant="outlined"
            startIcon={<EditIcon sx={{ fontSize: "0.95rem !important" }} />}
            onClick={onEdit}
            sx={{ textTransform: "none" }}
          >
            Open
          </Button>
          <Tooltip title="Delete workflow">
            <IconButton
              aria-label={`Delete workflow ${title}`}
              size="small"
              onClick={onDelete}
              sx={{ color: color.text.secondary }}
            >
              <DeleteOutlineIcon fontSize="small" />
            </IconButton>
          </Tooltip>
        </Stack>
      </Stack>
    </fm.div>
  );
}

function cardStyle(): CSSProperties {
  return {
    position: "relative",
    background: color.surface.raised,
    border: 0,
    borderRadius: 12,
    padding: 18,
    boxShadow: elevation.card,
    fontFamily: typography.fontFamily.body,
    minHeight: 88,
  };
}
