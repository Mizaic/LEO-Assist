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
import Collapse from "@mui/material/Collapse";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Divider from "@mui/material/Divider";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";

import FormSchemaAnnotator from "@/components/operations/FormSchemaAnnotator";
import { fetchFormSchema, fetchLetterTextByUbrn } from "./formSchemaApi";

const LETTER_PANEL_ID = "form-schema-sample-letter-panel";

function countLines(text: string): number {
  return text.split("\n").filter((line) => line.trim()).length;
}

interface Props {
  open: boolean;
  fingerprint: string;
  formName: string;
  organizationId?: string;
  serviceId?: string;
  onClose: () => void;
  onSaved?: () => void;
}

function useSavedSchemaEditor(open: boolean, fingerprint: string) {
  const [ready, setReady] = useState(false);
  const [savedHasSections, setSavedHasSections] = useState(false);
  const [schemaLoading, setSchemaLoading] = useState(false);

  useEffect(() => {
    if (!open) {
      setReady(false);
      setSavedHasSections(false);
      setSchemaLoading(false);
      return;
    }
    let cancelled = false;
    setSchemaLoading(true);
    fetchFormSchema(fingerprint)
      .then((schema) => {
        if (cancelled) return;
        const hasSections = (schema?.sections?.length ?? 0) > 0;
        setSavedHasSections(hasSections);
        if (hasSections) setReady(true);
      })
      .catch(() => {
        if (!cancelled) setSavedHasSections(false);
      })
      .finally(() => {
        if (!cancelled) setSchemaLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, fingerprint]);

  return { ready, setReady, savedHasSections, schemaLoading };
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
  const [ubrnInput, setUbrnInput] = useState("");
  const [ubrnLoading, setUbrnLoading] = useState(false);
  const [ubrnError, setUbrnError] = useState("");
  const [letterOpen, setLetterOpen] = useState(true);
  const { ready, setReady, savedHasSections, schemaLoading } =
    useSavedSchemaEditor(open, fingerprint);

  useEffect(() => {
    if (!open) {
      setSourceText("");
      setUbrnInput("");
      setUbrnError("");
      setLetterOpen(true);
    }
  }, [open, fingerprint]);

  const canTeach = sourceText.trim().length >= 10;
  const canOpenEditor = canTeach || savedHasSections;

  async function handleLoadFromReferral() {
    const ubrn = ubrnInput.trim();
    if (!ubrn) return;
    setUbrnLoading(true);
    setUbrnError("");
    try {
      const result = await fetchLetterTextByUbrn(ubrn, organizationId);
      setSourceText(result.text);
      setLetterOpen(false);
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
      slotProps={{ paper: { sx: { height: "90vh" } } }}
    >
      <DialogTitle id="form-schema-teach-title">
        Teach form: {formName}
      </DialogTitle>
      <DialogContent sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
        <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
          <Button
            size="small"
            onClick={() => setLetterOpen((prev) => !prev)}
            aria-expanded={letterOpen}
            aria-controls={LETTER_PANEL_ID}
            endIcon={
              <ExpandMoreIcon
                sx={{ transform: letterOpen ? "rotate(180deg)" : "none" }}
              />
            }
          >
            Sample letter
          </Button>
          {!letterOpen && sourceText.trim() ? (
            <Typography
              variant="body2"
              color="text.secondary"
              data-testid="sample-letter-summary"
            >
              Sample letter loaded ({countLines(sourceText)} lines).
            </Typography>
          ) : null}
        </Box>
        <Collapse in={letterOpen} id={LETTER_PANEL_ID}>
          <Box sx={{ display: "flex", flexDirection: "column", gap: 2, pt: 1 }}>
            <Typography variant="body2" color="text.secondary">
              Load the letter you taught this form from. You need it to save
              changes.
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
          </Box>
        </Collapse>
        {schemaLoading && !ready ? (
          <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
            <CircularProgress size={18} aria-label="Loading" role="status" />
            <Typography variant="body2">Loading the saved schema...</Typography>
          </Box>
        ) : null}
        {ready ? (
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
            disabled={!canOpenEditor || schemaLoading}
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
