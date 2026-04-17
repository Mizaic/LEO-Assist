"use client";

// -- EdgeDeleteConfirm.tsx -----------------------------------------------------
// Small modal that asks the user to confirm removing one or more wires from the
// canvas. Stateless / prop-driven so the parent can keep owning the React Flow
// edge state.

import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import Typography from "@mui/material/Typography";

export interface EdgeDeleteConfirmProps {
  open: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}

export function EdgeDeleteConfirm({
  open,
  onCancel,
  onConfirm,
}: EdgeDeleteConfirmProps) {
  return (
    <Dialog
      open={open}
      onClose={onCancel}
      maxWidth="xs"
      fullWidth
      PaperProps={{ sx: { borderRadius: 3 } }}
    >
      <Box sx={{ px: 3, pt: 2.5, pb: 1 }}>
        <Typography variant="h6" fontWeight={700} gutterBottom>
          Remove connection?
        </Typography>
        <Typography variant="body2" color="text.secondary">
          Disconnecting this wire means the next step will no longer receive
          data from this one. You can reconnect it on the canvas at any time.
        </Typography>
      </Box>
      <Box
        sx={{
          px: 3,
          pb: 2.5,
          pt: 1.5,
          display: "flex",
          justifyContent: "flex-end",
          gap: 1,
        }}
      >
        <Button onClick={onCancel} sx={{ textTransform: "none" }}>
          Keep connected
        </Button>
        <Button
          variant="contained"
          color="error"
          onClick={onConfirm}
          sx={{ textTransform: "none" }}
        >
          Remove connection
        </Button>
      </Box>
    </Dialog>
  );
}
