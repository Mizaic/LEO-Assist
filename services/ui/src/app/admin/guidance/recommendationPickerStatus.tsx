/**
 * Status chips for RecommendationPickerDialog.
 *
 * Atlas: DI-EB716E68
 *
 * Atlas trace:
 *   DO: DO-2C03CA0E
 *   DI: DI-3F771AFB
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-2C03CA0E")
 */
"use client";

import Chip from "@mui/material/Chip";
import Tooltip from "@mui/material/Tooltip";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import GavelIcon from "@mui/icons-material/Gavel";
import HourglassEmptyIcon from "@mui/icons-material/HourglassEmpty";
import {
  attachBadgeLabel,
  attachBadgeTip,
  type RecRuleRef,
} from "./recommendationPickerSelection";

const STATUS_ICON: Record<string, React.ReactNode> = {
  active: <CheckCircleIcon sx={{ fontSize: 13 }} />,
  pending_review: <HourglassEmptyIcon sx={{ fontSize: 13 }} />,
  rejected: <GavelIcon sx={{ fontSize: 13 }} />,
};

const STATUS_COLOR: Record<string, "success" | "warning" | "error" | "default"> = {
  active: "success",
  pending_review: "warning",
  rejected: "error",
};

function rulesModeLabel(status: string): string {
  return status.replace(/_/g, " ");
}

export function RuleStatusChip({
  rule,
  attachMode = false,
  inCompiledBitmap = false,
}: {
  rule: RecRuleRef;
  attachMode?: boolean;
  inCompiledBitmap?: boolean;
}) {
  const color =
    attachMode && rule.status === "active" && inCompiledBitmap
      ? "success"
      : (STATUS_COLOR[rule.status] ?? "default");
  const label = attachMode
    ? attachBadgeLabel(rule.status, inCompiledBitmap)
    : rulesModeLabel(rule.status);
  const chip = (
    <Chip
      icon={STATUS_ICON[rule.status] as React.ReactElement}
      label={label}
      size="small"
      color={color}
      variant="outlined"
      sx={{ height: 20, fontSize: "0.68rem", mr: 0.5 }}
    />
  );
  const tip = attachMode
    ? attachBadgeTip(rule.status, inCompiledBitmap)
    : undefined;
  return tip ? <Tooltip title={tip}>{chip}</Tooltip> : chip;
}
