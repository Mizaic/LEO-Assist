/**
 * Atlas trace:
 *   DO: DO-2E8544FD
 *   DI: DI-C65FD45B
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-2E8544FD")
 *
 * Modal wrapper for the "Open detail" zoom on /care/audit evolution
 * cards. Sections that have a richer per-year visualisation (type
 * breakdown bar chart, multi-bucket compositional bar, etc.) embed it
 * in the dialog body so the section card itself stays focused on its
 * single headline KPI.
 */
"use client";

import CloseIcon from "@mui/icons-material/Close";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import IconButton from "@mui/material/IconButton";
import Button from "@mui/material/Button";
import Box from "@mui/material/Box";
import type { ReactNode } from "react";

interface Props {
  open: boolean;
  onClose: () => void;
  title: string;
  subtitle?: string;
  children: ReactNode;
  maxWidth?: "sm" | "md" | "lg" | "xl";
}

export default function EvolutionDetailDialog({
  open,
  onClose,
  title,
  subtitle,
  children,
  maxWidth = "md",
}: Props) {
  return (
    <Dialog
      open={open}
      onClose={onClose}
      maxWidth={maxWidth}
      fullWidth
      aria-labelledby="audit-evolution-detail-title"
    >
      <DialogTitle
        id="audit-evolution-detail-title"
        sx={{
          display: "flex",
          alignItems: "flex-start",
          justifyContent: "space-between",
          gap: 2,
          pr: 6,
          pb: 1,
        }}
      >
        <Box sx={{ minWidth: 0 }}>
          <Box sx={{ fontSize: "1.05rem", fontWeight: 700 }}>{title}</Box>
          {subtitle && (
            <Box
              sx={{
                fontSize: "0.78rem",
                color: "text.secondary",
                mt: 0.25,
                fontWeight: 500,
              }}
            >
              {subtitle}
            </Box>
          )}
        </Box>
        <IconButton
          aria-label="Close detail"
          onClick={onClose}
          sx={{ position: "absolute", top: 8, right: 8 }}
        >
          <CloseIcon />
        </IconButton>
      </DialogTitle>
      <DialogContent dividers>{children}</DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Close</Button>
      </DialogActions>
    </Dialog>
  );
}
