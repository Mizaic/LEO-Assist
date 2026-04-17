"use client";

/**
 * Pathway dialogs -- New / Publish / Delete.
 *
 * Design Controls: DI-LEO-AI-150, DO-LEO-AI-146, VT-LEO-AI-148.
 */

import { useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import AddIcon from "@mui/icons-material/Add";
import AutoFixHighIcon from "@mui/icons-material/AutoFixHigh";
import CloudUploadIcon from "@mui/icons-material/CloudUpload";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";

import { PATHWAY_TEMPLATES, type PathwayTemplate } from "./templates";
import type { PlanDefinition } from "./types";

// ----------------------------------------------------------------------------
// New pathway / template picker dialog
// ----------------------------------------------------------------------------

export function NewPathwayDialog({
  open,
  onClose,
  onCreate,
  creating,
}: {
  open: boolean;
  onClose: () => void;
  onCreate: (template: PathwayTemplate) => void;
  creating: boolean;
}) {
  const [selected, setSelected] = useState<string>("blank");
  const template =
    PATHWAY_TEMPLATES.find((t) => t.id === selected) ?? PATHWAY_TEMPLATES[0];

  return (
    <Dialog
      open={open}
      onClose={onClose}
      maxWidth="sm"
      fullWidth
      PaperProps={{ sx: { borderRadius: 3 } }}
    >
      <DialogTitle sx={{ pb: 0.5 }}>
        <Stack direction="row" alignItems="center" spacing={1}>
          <AutoFixHighIcon color="primary" sx={{ fontSize: "1.3rem" }} />
          <Typography variant="h6" fontWeight={700}>
            Start a new pathway
          </Typography>
        </Stack>
        <Typography
          variant="body2"
          color="text.secondary"
          sx={{ mt: 0.5 }}
        >
          Pick a ready-made starting point or build from scratch.
        </Typography>
      </DialogTitle>
      <DialogContent sx={{ pt: 1.5 }}>
        <Stack spacing={1.25}>
          {PATHWAY_TEMPLATES.map((t) => (
            <Paper
              key={t.id}
              variant="outlined"
              onClick={() => setSelected(t.id)}
              sx={{
                p: 1.75,
                borderRadius: 2,
                cursor: "pointer",
                borderColor:
                  selected === t.id ? "primary.main" : "divider",
                borderWidth: selected === t.id ? 2 : 1,
                bgcolor:
                  selected === t.id ? "primary.50" : "background.paper",
                transition: "all 0.15s",
                "&:hover": { borderColor: "primary.light", boxShadow: 1 },
              }}
            >
              <Stack direction="row" alignItems="flex-start" spacing={1.5}>
                <Box sx={{ flex: 1 }}>
                  <Stack direction="row" alignItems="center" spacing={1}>
                    <Typography variant="subtitle2" fontWeight={700}>
                      {t.name}
                    </Typography>
                    {t.stepCount > 0 ? (
                      <Chip
                        size="small"
                        label={`${t.stepCount} step${
                          t.stepCount !== 1 ? "s" : ""
                        } ready`}
                        color="success"
                        variant="outlined"
                        sx={{ height: 20, fontSize: "0.65rem" }}
                      />
                    ) : null}
                  </Stack>
                  <Typography
                    variant="caption"
                    color="text.secondary"
                    sx={{ mt: 0.4, display: "block", lineHeight: 1.45 }}
                  >
                    {t.description}
                  </Typography>
                </Box>
                <Box
                  sx={{
                    width: 20,
                    height: 20,
                    borderRadius: "50%",
                    border: "2px solid",
                    borderColor:
                      selected === t.id ? "primary.main" : "grey.300",
                    bgcolor:
                      selected === t.id ? "primary.main" : "transparent",
                    flexShrink: 0,
                    mt: 0.25,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                  }}
                >
                  {selected === t.id ? (
                    <Box
                      sx={{
                        width: 8,
                        height: 8,
                        borderRadius: "50%",
                        bgcolor: "#fff",
                      }}
                    />
                  ) : null}
                </Box>
              </Stack>
            </Paper>
          ))}
        </Stack>
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button
          onClick={onClose}
          disabled={creating}
          sx={{ textTransform: "none" }}
        >
          Cancel
        </Button>
        <Button
          variant="contained"
          disabled={creating}
          startIcon={
            creating ? (
              <CircularProgress size={13} color="inherit" />
            ) : (
              <AddIcon />
            )
          }
          onClick={() => onCreate(template)}
          sx={{ textTransform: "none" }}
        >
          {creating
            ? "Creating..."
            : template.id === "blank"
              ? "Create blank pathway"
              : "Use this template"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

// ----------------------------------------------------------------------------
// Publish dialog
// ----------------------------------------------------------------------------

export function PublishDialog({
  target,
  versionNotes,
  publishing,
  onClose,
  onConfirm,
  onVersionNotesChange,
}: {
  target: PlanDefinition | null;
  versionNotes: string;
  publishing: boolean;
  onClose: () => void;
  onConfirm: () => void;
  onVersionNotesChange: (v: string) => void;
}) {
  return (
    <Dialog
      open={!!target}
      onClose={() => !publishing && onClose()}
      maxWidth="xs"
      fullWidth
      PaperProps={{ sx: { borderRadius: 3 } }}
    >
      <DialogTitle sx={{ pb: 0.5 }}>
        <Stack direction="row" alignItems="center" spacing={1}>
          <CloudUploadIcon color="success" sx={{ fontSize: "1.3rem" }} />
          <Typography variant="h6" fontWeight={700}>
            Publish to live
          </Typography>
        </Stack>
      </DialogTitle>
      <DialogContent>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          <strong>{target?.name}</strong> will become the live version
          immediately. The runtime will begin using it for new pipeline
          executions.
        </Typography>
        <Alert severity="info" icon={false} sx={{ mb: 2, fontSize: "0.82rem" }}>
          To roll back, edit the pathway and publish again, or duplicate a
          previous version.
        </Alert>
        <TextField
          label="Version notes (optional)"
          placeholder="e.g. Added verification step before persist, updated extraction prompt to v3"
          multiline
          minRows={2}
          fullWidth
          size="small"
          value={versionNotes}
          onChange={(e) => onVersionNotesChange(e.target.value)}
        />
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button
          onClick={onClose}
          disabled={publishing}
          sx={{ textTransform: "none" }}
        >
          Cancel
        </Button>
        <Button
          variant="contained"
          color="success"
          disabled={publishing}
          startIcon={
            publishing ? (
              <CircularProgress size={13} color="inherit" />
            ) : (
              <CloudUploadIcon />
            )
          }
          onClick={onConfirm}
          sx={{ textTransform: "none" }}
        >
          {publishing ? "Publishing..." : "Publish to live"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

// ----------------------------------------------------------------------------
// Delete dialog
// ----------------------------------------------------------------------------

export function DeletePathwayDialog({
  target,
  confirmName,
  deleting,
  onClose,
  onConfirm,
  onConfirmNameChange,
}: {
  target: PlanDefinition | null;
  confirmName: string;
  deleting: boolean;
  onClose: () => void;
  onConfirm: () => void;
  onConfirmNameChange: (v: string) => void;
}) {
  const targetLabel = target ? target.name || target.id : "";
  const armed = confirmName.trim() === targetLabel;
  return (
    <Dialog
      open={!!target}
      onClose={() => !deleting && onClose()}
      maxWidth="sm"
      fullWidth
      PaperProps={{ sx: { borderRadius: 3 } }}
    >
      <DialogTitle sx={{ pb: 0.5 }}>
        <Stack direction="row" alignItems="center" spacing={1}>
          <DeleteOutlineIcon color="error" sx={{ fontSize: "1.3rem" }} />
          <Typography variant="h6" fontWeight={700}>
            Delete pathway permanently?
          </Typography>
        </Stack>
      </DialogTitle>
      <DialogContent>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          <strong>{targetLabel}</strong> will be removed from the admin UI and
          its stored definition, actions, and version history will be deleted
          from Neo4j. This cannot be undone.
        </Typography>
        {target?.status === "active" ? (
          <Alert severity="warning" sx={{ mb: 2 }}>
            This pathway is currently live. Deleting it may stop future runtime
            processing that depends on it.
          </Alert>
        ) : null}
        <Alert severity="error" icon={false} sx={{ mb: 2, fontSize: "0.85rem" }}>
          Type the pathway name exactly to unlock permanent deletion.
        </Alert>
        <TextField
          label="Confirm pathway name"
          placeholder={targetLabel}
          value={confirmName}
          onChange={(e) => onConfirmNameChange(e.target.value)}
          fullWidth
          autoFocus
          disabled={deleting}
          helperText={
            target ? `Type "${targetLabel}" to confirm.` : ""
          }
        />
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button
          onClick={onClose}
          disabled={deleting}
          sx={{ textTransform: "none" }}
        >
          Cancel
        </Button>
        <Button
          variant="contained"
          color="error"
          disabled={deleting || !armed}
          onClick={onConfirm}
          startIcon={
            deleting ? (
              <CircularProgress size={13} color="inherit" />
            ) : (
              <DeleteOutlineIcon />
            )
          }
          sx={{ textTransform: "none" }}
        >
          {deleting ? "Deleting..." : "Delete pathway permanently"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
