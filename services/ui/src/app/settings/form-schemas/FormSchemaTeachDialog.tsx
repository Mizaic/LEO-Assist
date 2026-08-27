/**
 * Standalone Teach this form dialog for settings and admin paths.
 *
 * Atlas trace: DI-5C9CA57B, DI-26546721
 */
"use client";

import { useEffect, useState } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";

import FormSchemaAnnotator from "@/components/operations/FormSchemaAnnotator";

interface Props {
  open: boolean;
  fingerprint: string;
  formName: string;
  organizationId?: string;
  serviceId?: string;
  onClose: () => void;
  onSaved?: () => void;
}

export default function FormSchemaTeachDialog({
  open,
  fingerprint,
  formName,
  organizationId = "",
  serviceId = "",
  onClose,
  onSaved,
}: Props) {
  const [sourceText, setSourceText] = useState("");
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!open) {
      setSourceText("");
      setReady(false);
    }
  }, [open, fingerprint]);

  const canTeach = sourceText.trim().length >= 10;

  return (
    <Dialog
      open={open}
      onClose={onClose}
      fullWidth
      maxWidth="lg"
      aria-labelledby="form-schema-teach-title"
      data-testid="form-schema-teach-dialog"
    >
      <DialogTitle id="form-schema-teach-title">
        Teach form: {formName}
      </DialogTitle>
      <DialogContent sx={{ display: "flex", flexDirection: "column", gap: 2, minHeight: 480 }}>
        <Typography variant="body2" color="text.secondary">
          Paste a sample referral letter for this form. LEO uses it to match
          sections and checkboxes while you edit the schema.
        </Typography>
        <TextField
          label="Sample referral letter"
          value={sourceText}
          onChange={(e) => setSourceText(e.target.value)}
          multiline
          minRows={6}
          maxRows={14}
          fullWidth
          placeholder="Paste the referral text here..."
          inputProps={{ "aria-label": "Sample referral letter" }}
        />
        <Typography variant="caption" color="text.secondary">
          Fingerprint: {fingerprint}
        </Typography>
        {canTeach && ready ? (
          <Box sx={{ flex: 1, minHeight: 360, display: "flex", flexDirection: "column" }}>
            <FormSchemaAnnotator
              fingerprint={fingerprint}
              sourceText={sourceText}
              formName={formName}
              onSaved={onSaved}
              initialOrganizationId={organizationId}
              initialServiceId={serviceId}
            />
          </Box>
        ) : null}
      </DialogContent>
      <DialogActions>
        {!ready ? (
          <Button
            variant="contained"
            disabled={!canTeach}
            onClick={() => setReady(true)}
          >
            Open schema editor
          </Button>
        ) : null}
        <Button onClick={onClose}>Close</Button>
      </DialogActions>
    </Dialog>
  );
}
