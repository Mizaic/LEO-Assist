"use client";

// -- PublishDialog.tsx ---------------------------------------------------------
// Publish-to-live confirmation. Shows step count, validation summary, and a
// version notes field. Prop-driven so the parent owns publish state.

import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import Dialog from "@mui/material/Dialog";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import CloudUploadIcon from "@mui/icons-material/CloudUpload";

export interface PublishDialogProps {
  open: boolean;
  onClose: () => void;
  onConfirm: () => void;
  isSaving: boolean;
  planName: string;
  stepCount: number;
  errorCount: number;
  warningCount: number;
  versionNotes: string;
  onVersionNotesChange: (notes: string) => void;
}

export function PublishDialog(props: PublishDialogProps) {
  const {
    open,
    onClose,
    onConfirm,
    isSaving,
    planName,
    stepCount,
    errorCount,
    warningCount,
    versionNotes,
    onVersionNotesChange,
  } = props;

  return (
    <Dialog
      open={open}
      onClose={() => !isSaving && onClose()}
      maxWidth="xs"
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
          <CloudUploadIcon color="success" />
          <Typography variant="h6" fontWeight={700}>
            Publish to live
          </Typography>
        </Stack>
        <Typography variant="caption" color="text.secondary">
          {planName || "This pathway"} will immediately be used by the runtime
          for new executions.
        </Typography>
      </Box>

      <Box sx={{ px: 3, py: 2 }}>
        <Stack spacing={0.75} sx={{ mb: 2 }}>
          <Stack direction="row" justifyContent="space-between">
            <Typography variant="caption" color="text.secondary">
              Pipeline steps
            </Typography>
            <Typography variant="caption" fontWeight={600}>
              {stepCount}
            </Typography>
          </Stack>
          <Stack direction="row" justifyContent="space-between">
            <Typography variant="caption" color="text.secondary">
              Validation errors
            </Typography>
            <Typography
              variant="caption"
              fontWeight={600}
              color={errorCount > 0 ? "error.main" : "success.main"}
            >
              {errorCount === 0
                ? "None"
                : `${errorCount} error${errorCount > 1 ? "s" : ""}`}
            </Typography>
          </Stack>
          {warningCount > 0 ? (
            <Stack direction="row" justifyContent="space-between">
              <Typography variant="caption" color="text.secondary">
                Warnings
              </Typography>
              <Typography
                variant="caption"
                fontWeight={600}
                color="warning.main"
              >
                {warningCount}
              </Typography>
            </Stack>
          ) : null}
        </Stack>

        <Alert severity="info" icon={false} sx={{ mb: 2, fontSize: "0.75rem" }}>
          To roll back: edit the pathway, adjust the steps, and publish again.
          For a clean rollback, duplicate a known-good version as a new draft
          and publish that.
        </Alert>

        <TextField
          label="Version notes (optional)"
          placeholder="e.g. Added verification step before persist; updated extraction prompt to v3"
          multiline
          minRows={2}
          fullWidth
          size="small"
          value={versionNotes}
          onChange={(e) => onVersionNotesChange(e.target.value)}
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
          disabled={isSaving}
          sx={{ textTransform: "none" }}
        >
          Cancel
        </Button>
        <Button
          variant="contained"
          color="success"
          disabled={isSaving}
          startIcon={
            isSaving ? (
              <CircularProgress size={13} color="inherit" />
            ) : (
              <CloudUploadIcon />
            )
          }
          onClick={onConfirm}
          sx={{ textTransform: "none" }}
          aria-label="Publish to live"
        >
          {isSaving ? "Publishing..." : "Publish to live"}
        </Button>
      </Box>
    </Dialog>
  );
}
