/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-B5DB3744
 *   DI: DI-C6700F52
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-B5DB3744")
 */
"use client";

import type { ReactNode } from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { color, typography } from "@leo/design-system/tokens";

interface NodeHeaderProps {
  /** Optional leading icon. */
  icon?: ReactNode;
  /** Primary title text. */
  title: string;
  /** Optional trailing slot - usually NodeStatusStrip. */
  trailing?: ReactNode;
}

/**
 * NodeHeader - shared title row used by every pathway node.
 * Always: optional icon + bold title (flex 1) + optional trailing status pip.
 */
export function NodeHeader({ icon, title, trailing }: NodeHeaderProps) {
  return (
    <Box sx={{ display: "flex", alignItems: "center", gap: 0.75 }}>
      {icon ? (
        <Box sx={{ display: "flex", alignItems: "center" }} aria-hidden="true">
          {icon}
        </Box>
      ) : null}
      <Typography
        component="h3"
        variant="body2"
        fontWeight={700}
        sx={{
          flex: 1,
          m: 0,
          fontFamily: typography.fontFamily.heading,
          color: color.text.primary,
        }}
      >
        {title}
      </Typography>
      {trailing}
    </Box>
  );
}
