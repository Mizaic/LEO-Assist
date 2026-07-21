/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-30A82196
 *   DI: DI-85B110A5
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-30A82196")
 */
"use client";

import React from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Typography from "@mui/material/Typography";
import Chip from "@mui/material/Chip";
import ManageAccountsOutlinedIcon from "@mui/icons-material/ManageAccountsOutlined";
import { ROLE_COPY } from "@leo/design-system";

interface ImpersonationBannerProps {
  selectedRole: string;
  onExit: () => void;
}

export default function ImpersonationBanner({
  selectedRole,
  onExit,
}: ImpersonationBannerProps) {
  const roleLabel = ROLE_COPY[selectedRole]?.label ?? selectedRole;

  return (
    <Box
      role="alert"
      aria-label="Platform admin impersonation active"
      sx={{
        bgcolor: "warning.main",
        color: "warning.contrastText",
        px: 2,
        py: 0.75,
        display: "flex",
        alignItems: "center",
        gap: 1.5,
        flexWrap: "wrap",
      }}
    >
      <ManageAccountsOutlinedIcon sx={{ fontSize: 18, flexShrink: 0 }} />
      <Typography variant="body2" sx={{ fontWeight: 600, flexShrink: 0 }}>
        Platform admin
      </Typography>
      <Chip
        size="small"
        label={roleLabel}
        sx={{
          bgcolor: "warning.dark",
          color: "warning.contrastText",
          fontWeight: 700,
          fontSize: "0.7rem",
          height: 20,
        }}
      />
      <Typography variant="body2" sx={{ flex: 1, minWidth: 0 }}>
        You are trying this role. Changes you make are real.
      </Typography>
      <Button
        size="small"
        variant="outlined"
        onClick={onExit}
        sx={{
          color: "warning.contrastText",
          borderColor: "warning.contrastText",
          flexShrink: 0,
          "&:hover": {
            bgcolor: "warning.dark",
            borderColor: "warning.contrastText",
          },
        }}
      >
        Exit to platform admin
      </Button>
    </Box>
  );
}
