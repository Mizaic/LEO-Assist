/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-2C03CA0E
 *   DI: DI-3F771AFB
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-2C03CA0E")
 */
"use client";

// -- DeletePathwayDialog.tsx ---------------------------------------------------
// Type-the-name confirm gate before permanently deleting a pathway. Matches the
// pattern used by other destructive actions across the app.

import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import Dialog from "@mui/material/Dialog";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";

export interface DeletePathwayDialogProps {
  open: boolean;
  onClose: () => void;
  onConfirm: () => void;
  isDeleting: boolean;
  isLive: boolean;
  pathwayName: string;
  confirmText: string;
  onConfirmTextChange: (text: string) => void;
}

export function DeletePathwayDialog(props: DeletePathwayDialogProps) {
  const {
    open,
    onClose,
    onConfirm,
    isDeleting,
    isLive,
    pathwayName,
    confirmText,
    onConfirmTextChange,
  } = props;

  const canDelete = !isDeleting && confirmText.trim() === pathwayName;

  return (
    <Dialog
      open={open}
      onClose={() => !isDeleting && onClose()}
      maxWidth="sm"
      fullWidth
      PaperProps={{ sx: { borderRadius: 3 } }}
    >
      <Box
        sx={{
          px: 3,
          pt: 2.5,
          pb: 1,
          borderBottom: 1,
          borderColor: "divider",
        }}
      >
        <Stack direction="row" alignItems="center" spacing={1}>
          <DeleteOutlineIcon color="error" />
          <Typography variant="h6" fontWeight={700}>
            Delete pathway permanently?
          </Typography>
        </Stack>
        <Typography variant="caption" color="text.secondary">
          {pathwayName} will be removed from the admin UI and deleted from
          Neo4j.
        </Typography>
      </Box>

      <Box sx={{ px: 3, py: 2 }}>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          This deletes the pathway definition, its linked actions, and its
          saved version history from Neo4j. This cannot be undone.
        </Typography>
        {isLive ? (
          <Alert severity="warning" sx={{ mb: 2 }}>
            This pathway is currently live. Deleting it may stop future runtime
            processing that depends on it.
          </Alert>
        ) : null}
        <Alert severity="error" icon={false} sx={{ mb: 2, fontSize: "0.78rem" }}>
          Type the pathway name exactly to unlock permanent deletion.
        </Alert>
        <TextField
          label="Confirm pathway name"
          fullWidth
          size="small"
          autoFocus
          value={confirmText}
          onChange={(e) => onConfirmTextChange(e.target.value)}
          disabled={isDeleting}
          helperText={`Type "${pathwayName}" to confirm.`}
        />
      </Box>

      <Box
        sx={{
          px: 3,
          pb: 2.5,
          display: "flex",
          justifyContent: "flex-end",
          gap: 1,
        }}
      >
        <Button
          onClick={onClose}
          disabled={isDeleting}
          sx={{ textTransform: "none" }}
        >
          Cancel
        </Button>
        <Button
          variant="contained"
          color="error"
          disabled={!canDelete}
          startIcon={
            isDeleting ? (
              <CircularProgress size={13} color="inherit" />
            ) : (
              <DeleteOutlineIcon />
            )
          }
          onClick={onConfirm}
          sx={{ textTransform: "none" }}
          aria-label="Delete pathway permanently"
        >
          {isDeleting ? "Deleting..." : "Delete pathway permanently"}
        </Button>
      </Box>
    </Dialog>
  );
}
