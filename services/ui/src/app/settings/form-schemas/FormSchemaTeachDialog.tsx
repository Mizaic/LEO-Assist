/**
 * Standalone Teach this form dialog for settings and admin paths.
 *
 * Atlas trace: DI-5C9CA57B, DI-26546721
 */
"use client";

import { useEffect, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Divider from "@mui/material/Divider";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";

import FormSchemaAnnotator from "@/components/operations/FormSchemaAnnotator";
import { fetchLetterTextByUbrn } from "./formSchemaApi";

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
  const [ubrnInput, setUbrnInput] = useState("");
  const [ubrnLoading, setUbrnLoading] = useState(false);
  const [ubrnError, setUbrnError] = useState("");

  useEffect(() => {
    if (!open) {
      setSourceText("");
      setReady(false);
      setUbrnInput("");
      setUbrnError("");
    }
  }, [open, fingerprint]);

  const canTeach = sourceText.trim().length >= 10;

  async function handleLoadFromReferral() {
    const ubrn = ubrnInput.trim();
    if (!ubrn) return;
    setUbrnLoading(true);
    setUbrnError("");
    try {
      const result = await fetchLetterTextByUbrn(ubrn, organizationId);
      setSourceText(result.text);
    } catch (err) {
      setUbrnError(err instanceof Error ? err.message : "Could not load the referral.");
    } finally {
      setUbrnLoading(false);
    }
  }

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
          Paste a sample referral letter below, or load one directly from a
          referral record using its UBRN. LEO uses the letter to match
          sections and checkboxes while you edit the schema.
        </Typography>

        <Box
          sx={{ display: "flex", gap: 1, alignItems: "flex-start" }}
          data-testid="load-from-referral-row"
        >
          <TextField
            label="Load from referral (UBRN)"
            value={ubrnInput}
            onChange={(e) => setUbrnInput(e.target.value)}
            size="small"
            sx={{ flex: 1 }}
            placeholder="e.g. 000 123 4567"
            inputProps={{ "aria-label": "UBRN" }}
            onKeyDown={(e) => {
              if (e.key === "Enter") handleLoadFromReferral();
            }}
          />
          <Button
            variant="outlined"
            size="small"
            disabled={!ubrnInput.trim() || ubrnLoading}
            onClick={handleLoadFromReferral}
            startIcon={ubrnLoading ? <CircularProgress size={14} /> : null}
            data-testid="load-from-referral-btn"
          >
            Load
          </Button>
        </Box>

        {ubrnError ? (
          <Alert severity="error" data-testid="ubrn-error">
            {ubrnError}
          </Alert>
        ) : null}

        <Divider>
          <Typography variant="caption" color="text.secondary">
            or paste manually
          </Typography>
        </Divider>

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
