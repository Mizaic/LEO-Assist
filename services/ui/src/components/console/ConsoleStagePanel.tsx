/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-30A82196
 *   DI: DI-85B110A5
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-30A82196")
 */
"use client";

import { useState, type ReactNode } from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Button from "@mui/material/Button";
import Collapse from "@mui/material/Collapse";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import ExpandLessIcon from "@mui/icons-material/ExpandLess";

import { color, radius } from "@leo/design-system";

import { StatusDot } from "@/components/ui/StatusDot";
import type { HealthStatus } from "@/theme/tokens";

// ConsoleStagePanel -- design-system-tokenised stage panel used by the
// Intelligence Console. Replaces the bespoke StageCard in
// services/ui/src/components/ui/StageCard.tsx (which remains for any
// other legacy consumers). Visually aligns the console with the
// Knowledge tabs / Pathways list redesign while preserving the existing
// accentColor + status + action surface so the underlying console
// behaviour is unchanged.
//
// Design Controls: DI-LEO-AI-164, DO-LEO-AI-163, R-LEO-AI-165, VT-LEO-AI-162.

export interface ConsoleStagePanelProps {
  title: string;
  status: HealthStatus;
  statusReason?: string;
  metric?: ReactNode;
  actionLabel?: string;
  onAction?: () => void;
  actionDisabled?: boolean;
  children?: ReactNode;
  defaultExpanded?: boolean;
  // Stage accent colour. Used for the top strip and the action button
  // background; defaults to color.brand.primary.
  accentColor?: string;
}

export function ConsoleStagePanel({
  title,
  status,
  statusReason,
  metric,
  actionLabel,
  onAction,
  actionDisabled,
  children,
  defaultExpanded = false,
  accentColor,
}: ConsoleStagePanelProps) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const accent = accentColor ?? color.brand.primary;
  const hasBody = Boolean(children);

  const handleToggle = () => {
    if (hasBody) setExpanded((v) => !v);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (!hasBody) return;
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      setExpanded((v) => !v);
    }
  };

  return (
    <Box
      sx={{
        border: "1px solid " + color.surface.divider,
        borderRadius: `${radius.md}px`,
        overflow: "hidden",
        bgcolor: color.surface.raised,
        borderTop: "3px solid " + accent,
      }}
    >
      <Box
        sx={{
          display: "flex",
          alignItems: "center",
          gap: 1.5,
          px: 2,
          py: 1.5,
          cursor: hasBody ? "pointer" : "default",
          "&:hover": hasBody ? { bgcolor: color.surface.alt } : {},
        }}
        onClick={handleToggle}
        role={hasBody ? "button" : undefined}
        aria-expanded={hasBody ? expanded : undefined}
        tabIndex={hasBody ? 0 : undefined}
        onKeyDown={handleKeyDown}
      >
        <StatusDot status={status} reason={statusReason} size={10} />
        <Typography
          sx={{
            fontWeight: 700,
            fontSize: "0.85rem",
            color: color.text.primary,
            letterSpacing: "0.05em",
            textTransform: "uppercase",
            flex: 1,
          }}
        >
          {title}
        </Typography>
        {metric ? <Box sx={{ mr: 1 }}>{metric}</Box> : null}
        {actionLabel && onAction ? (
          <Button
            size="small"
            variant="contained"
            onClick={(e) => {
              e.stopPropagation();
              onAction();
            }}
            disabled={actionDisabled}
            sx={{
              textTransform: "none",
              fontSize: "0.78rem",
              bgcolor: accent,
              "&:hover": { bgcolor: accent + "cc" },
              mr: hasBody ? 1 : 0,
            }}
          >
            {actionLabel}
          </Button>
        ) : null}
        {hasBody ? (
          <Box sx={{ color: color.text.secondary, display: "flex" }}>
            {expanded ? (
              <ExpandLessIcon fontSize="small" />
            ) : (
              <ExpandMoreIcon fontSize="small" />
            )}
          </Box>
        ) : null}
      </Box>
      {hasBody ? (
        <Collapse in={expanded}>
          <Box
            sx={{
              px: 2,
              pb: 2,
              borderTop: "1px solid " + color.surface.divider,
            }}
          >
            {children}
          </Box>
        </Collapse>
      ) : null}
    </Box>
  );
}
