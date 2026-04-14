"use client";

import { useState, ReactNode } from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Button from "@mui/material/Button";
import Collapse from "@mui/material/Collapse";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import ExpandLessIcon from "@mui/icons-material/ExpandLess";
import { StatusDot } from "./StatusDot";
import { HealthStatus, FONT_SIZES } from "@/theme/tokens";

interface StageCardProps {
  title: string;
  status: HealthStatus;
  statusReason?: string;
  metric?: ReactNode;
  actionLabel?: string;
  onAction?: () => void;
  actionDisabled?: boolean;
  children?: ReactNode;
  defaultExpanded?: boolean;
  accentColor?: string;
}

export function StageCard({
  title,
  status,
  statusReason,
  metric,
  actionLabel,
  onAction,
  actionDisabled,
  children,
  defaultExpanded = false,
  accentColor = "#1565c0",
}: StageCardProps) {
  const [expanded, setExpanded] = useState(defaultExpanded);

  return (
    <Box
      sx={{
        border: "1px solid",
        borderColor: "divider",
        borderRadius: 2,
        overflow: "hidden",
        bgcolor: "background.paper",
        borderTop: `3px solid ${accentColor}`,
      }}
    >
      <Box
        sx={{
          display: "flex",
          alignItems: "center",
          gap: 1.5,
          px: 2,
          py: 1.5,
          cursor: children ? "pointer" : "default",
          "&:hover": children ? { bgcolor: "action.hover" } : {},
        }}
        onClick={() => children && setExpanded((v) => !v)}
        role={children ? "button" : undefined}
        aria-expanded={children ? expanded : undefined}
        tabIndex={children ? 0 : undefined}
        onKeyDown={(e) => {
          if (children && (e.key === "Enter" || e.key === " ")) {
            e.preventDefault();
            setExpanded((v) => !v);
          }
        }}
      >
        <StatusDot status={status} reason={statusReason} size={10} />
        <Typography
          sx={{
            fontWeight: 700,
            fontSize: FONT_SIZES.subtitle,
            color: "text.primary",
            letterSpacing: "0.05em",
            textTransform: "uppercase",
            flex: 1,
          }}
        >
          {title}
        </Typography>
        {metric && <Box sx={{ mr: 1 }}>{metric}</Box>}
        {actionLabel && onAction && (
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
              fontSize: FONT_SIZES.label,
              bgcolor: accentColor,
              "&:hover": { bgcolor: `${accentColor}cc` },
              mr: children ? 1 : 0,
            }}
          >
            {actionLabel}
          </Button>
        )}
        {children && (
          <Box sx={{ color: "text.secondary", display: "flex" }}>
            {expanded ? (
              <ExpandLessIcon fontSize="small" />
            ) : (
              <ExpandMoreIcon fontSize="small" />
            )}
          </Box>
        )}
      </Box>
      {children && (
        <Collapse in={expanded}>
          <Box sx={{ px: 2, pb: 2, borderTop: "1px solid", borderColor: "divider" }}>
            {children}
          </Box>
        </Collapse>
      )}
    </Box>
  );
}
