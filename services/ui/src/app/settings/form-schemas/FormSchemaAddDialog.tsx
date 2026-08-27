/**
 * Add a new form template before a referral pauses in the pipeline.
 *
 * Atlas trace: DI-5C9CA57B, DI-26546721
 */
"use client";

import { useEffect, useRef, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";

import FormSchemaAnnotator from "@/components/operations/FormSchemaAnnotator";
import { FormSchemaScopeFields } from "@/components/operations/FormSchemaScopeFields";
import { computeFormFingerprint } from "@/components/operations/formSchemaFingerprint";

interface Props {
  open: boolean;
  existingFingerprints: Set<string>;
  onClose: () => void;
  onSaved: () => void;
  onEditExisting: (fingerprint: string, formName: string) => void;
}

export default function FormSchemaAddDialog({
  open,
  existingFingerprints,
  onClose,
  onSaved,
  onEditExisting,
}: Props) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [sourceText, setSourceText] = useState("");
  const [formName, setFormName] = useState("");
  const [fingerprint, setFingerprint] = useState("");
  const [organizationId, setOrganizationId] = useState("");
  const [serviceId, setServiceId] = useState("");
  const [step, setStep] = useState<"paste" | "editor">("paste");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!open) {
      setSourceText("");
      setFormName("");
      setFingerprint("");
      setOrganizationId("");
      setServiceId("");
      setStep("paste");
      setBusy(false);
      setError("");
    }
  }, [open]);

  const canContinue = sourceText.trim().length >= 10;
  const duplicate = fingerprint && existingFingerprints.has(fingerprint);

  const handleContinue = async () => {
    setBusy(true);
    setError("");
    try {
      const fp = await computeFormFingerprint(sourceText);
      setFingerprint(fp);
      if (existingFingerprints.has(fp)) {
        setError(
          "A template with this fingerprint already exists. Edit the existing one instead.",
        );
        return;
      }
      if (!formName.trim()) {
        setFormName("New referral form");
      }
      setStep("editor");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not continue.");
    } finally {
      setBusy(false);
    }
  };

  const handleUpload = async (file: File | null) => {
    if (!file) return;
    setError("");
    try {
      const text = await file.text();
      setSourceText(text);
    } catch {
      setError("Could not read that file. Paste the letter text instead.");
    }
  };

  return (
    <Dialog
      open={open}
      onClose={onClose}
      fullWidth
      maxWidth="lg"
      aria-labelledby="form-schema-add-title"
      data-testid="form-schema-add-dialog"
    >
      <DialogTitle id="form-schema-add-title">Add form template</DialogTitle>
      <DialogContent sx={{ display: "flex", flexDirection: "column", gap: 2, minHeight: 420 }}>
        <Typography variant="body2" color="text.secondary">
          Paste or upload a sample referral letter. LEO works out a fingerprint
          and opens the schema editor so you can teach the form before it
          blocks a live referral.
        </Typography>

        {error ? <Alert severity="error">{error}</Alert> : null}

        {step === "paste" ? (
          <>
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
            <Box>
              <input
                ref={fileInputRef}
                type="file"
                accept=".txt,.md,text/plain"
                hidden
                aria-hidden="true"
                onChange={(e) => void handleUpload(e.target.files?.[0] ?? null)}
              />
              <Button
                variant="outlined"
                onClick={() => fileInputRef.current?.click()}
              >
                Upload text file
              </Button>
            </Box>
            <TextField
              label="Form name"
              value={formName}
              onChange={(e) => setFormName(e.target.value)}
              fullWidth
              placeholder="e.g. Gynae 2WW referral"
              inputProps={{ "aria-label": "Form name" }}
            />
            <FormSchemaScopeFields
              organizationId={organizationId}
              serviceId={serviceId}
              onOrganization={setOrganizationId}
              onService={setServiceId}
            />
          </>
        ) : (
          <>
            <Typography variant="caption" color="text.secondary">
              Fingerprint: {fingerprint}
            </Typography>
            <Box sx={{ flex: 1, minHeight: 360, display: "flex", flexDirection: "column" }}>
              <FormSchemaAnnotator
                fingerprint={fingerprint}
                sourceText={sourceText}
                formName={formName.trim() || "New referral form"}
                onSaved={onSaved}
                initialOrganizationId={organizationId}
                initialServiceId={serviceId}
              />
            </Box>
          </>
        )}
      </DialogContent>
      <DialogActions>
        {step === "paste" ? (
          <>
            {duplicate ? (
              <Button
                variant="outlined"
                onClick={() => onEditExisting(fingerprint, formName.trim() || "Referral form")}
              >
                Edit existing template
              </Button>
            ) : null}
            <Button
              variant="contained"
              disabled={!canContinue || busy}
              onClick={() => void handleContinue()}
            >
              {busy ? "Working..." : "Open schema editor"}
            </Button>
          </>
        ) : null}
        <Button onClick={onClose}>Close</Button>
      </DialogActions>
    </Dialog>
  );
}
