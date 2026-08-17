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
 * 12px radius, 18px padding, 3px tone-coded left accent strip,
 * token status chip, spring entry and press.
 *
 * Design Controls: DI-LEO-AI-150, DO-LEO-AI-146, VT-LEO-AI-148.
 */

import type { CSSProperties } from "react";
import { motion as fm } from "framer-motion";
import Button from "@mui/material/Button";
import Divider from "@mui/material/Divider";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import EditIcon from "@mui/icons-material/Edit";
import {
  springOrInstant,
  springs,
  tapScale,
  useMotion,
} from "@leo/design-system";
import { color, elevation, typography } from "@leo/design-system/tokens";

import type { PlanDefinition } from "./types";
import {
  PathwayCardActions,
  PathwayMeta,
  StatusChip,
  ToneChip,
  isSeededPathway,
  statusAccent,
  workflowModeLabel,
} from "./PathwayCardParts";

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
  const { reducedMotion } = useMotion();
  const accent = statusAccent(plan.status);
  const isSeeded = isSeededPathway(plan);
  const workflowMode = plan._workflowMode || "legacy_in_process";
  const deprecatedCount = plan._deprecatedSubgraphs?.length ?? 0;
  const enter = springOrInstant(reducedMotion, springs.ui);

  return (
    <fm.div
      initial={reducedMotion ? false : { opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{
        ...enter,
        delay: reducedMotion ? 0 : Math.min(index, 12) * 0.04,
      }}
      whileTap={tapScale(reducedMotion)}
      data-testid={`pathway-card-${plan.id}`}
      style={cardStyle()}
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
        <CardHeader
          plan={plan}
          isSeeded={isSeeded}
          workflowMode={workflowMode}
          deprecatedCount={deprecatedCount}
        />
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
      <PathwayMeta plan={plan} />
      <Divider sx={{ my: 1.5 }} />
      <PathwayCardActions
        plan={plan}
        busy={busy}
        isSeeded={isSeeded}
        onPublish={onPublish}
        onDuplicate={onDuplicate}
        onRetire={onRetire}
        onReactivate={onReactivate}
        onDelete={onDelete}
      />
    </fm.div>
  );
}

function CardHeader({
  plan,
  isSeeded,
  workflowMode,
  deprecatedCount,
}: {
  plan: PlanDefinition;
  isSeeded: boolean;
  workflowMode: string;
  deprecatedCount: number;
}) {
  return (
    <Stack sx={{ flex: 1, minWidth: 0 }}>
      <Stack direction="row" alignItems="center" spacing={1} flexWrap="wrap" useFlexGap>
        <Typography
          variant="subtitle1"
          sx={{
            fontWeight: 700,
            fontSize: "1rem",
            lineHeight: 1.3,
            fontFamily: typography.fontFamily.heading,
            color: color.text.primary,
          }}
        >
          {plan.name || "Untitled pathway"}
        </Typography>
        <StatusChip status={plan.status} />
        {isSeeded ? <ToneChip label="Seeded" /> : null}
        <ToneChip
          label={workflowModeLabel(workflowMode)}
          fg={workflowMode === "durable_pubsub" ? color.brand.primary : color.text.secondary}
        />
        {deprecatedCount > 0 ? (
          <ToneChip
            label={`${deprecatedCount} deprecated step${deprecatedCount !== 1 ? "s" : ""}`}
            fg={color.status.warning}
          />
        ) : null}
        {plan.version ? (
          <Typography variant="caption" sx={{ color: color.text.disabled }}>
            v{plan.version}
          </Typography>
        ) : null}
      </Stack>
      <Typography
        variant="body2"
        sx={{ mt: 0.6, fontSize: "0.85rem", lineHeight: 1.5, color: color.text.secondary }}
      >
        {plan.description || "No description yet."}
      </Typography>
    </Stack>
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
  };
}
