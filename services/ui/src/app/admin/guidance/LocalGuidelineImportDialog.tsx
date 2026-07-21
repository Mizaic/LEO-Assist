/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-2C03CA0E
 *   DI: DI-3F771AFB
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-2C03CA0E")
 */
"use client";

import { useState } from "react";
import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";

interface Draft {
  metadata: { short_code: string; title: string };
  likely_incorrect: boolean;
  verification_errors: string[];
  chapters: Array<{ recommendations: unknown[] }>;
}

interface Props {
  open: boolean;
  onClose: () => void;
  onImported: (guidelineId?: string) => void;
}

async function readErrorDetail(response: Response, fallback: string): Promise<string> {
  const body = await response.json().catch(() => null);
  if (!body || typeof body !== "object") return fallback;
  const detail = (body as { detail?: unknown }).detail;
  if (typeof detail === "string" && detail.trim()) return detail;
  return fallback;
}

export default function LocalGuidelineImportDialog({
  open,
  onClose,
  onImported,
}: Props) {
  const [shortCode, setShortCode] = useState("");
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const [draft, setDraft] = useState<Draft | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [working, setWorking] = useState(false);

  const metaOk = /^[A-Z0-9][A-Z0-9-]{2,31}$/.test(shortCode) && title.length >= 3;
  const canStructure = metaOk && text.trim().length >= 20;
  // Blank create needs only identity fields; pasted text is ignored.
  const canCreateBlank = metaOk;

  const resetAndClose = () => {
    setShortCode("");
    setTitle("");
    setText("");
    setDraft(null);
    setError(null);
    setSuccess(null);
    onClose();
  };

  const structure = async () => {
    setWorking(true);
    setError(null);
    setSuccess(null);
    try {
      const response = await fetch("/api/guidance/local/structure", {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          "X-Requested-With": "XMLHttpRequest",
        },
        body: JSON.stringify({
          metadata: { short_code: shortCode, title },
          text,
        }),
      });
      if (!response.ok) {
        throw new Error(
          await readErrorDetail(response, "Could not structure the guideline."),
        );
      }
      setDraft((await response.json()) as Draft);
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "Could not structure the guideline.",
      );
    } finally {
      setWorking(false);
    }
  };

  const createBlank = async () => {
    if (!canCreateBlank || working) return;
    setWorking(true);
    setError(null);
    setSuccess(null);
    try {
      const response = await fetch("/api/guidance/local/create-blank", {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          "X-Requested-With": "XMLHttpRequest",
        },
        body: JSON.stringify({
          metadata: { short_code: shortCode, title },
        }),
      });
      if (!response.ok) {
        throw new Error(
          await readErrorDetail(response, "Could not create the blank guideline."),
        );
      }
      const result = (await response.json()) as { guideline_id?: string };
      const id = result.guideline_id || shortCode;
      setSuccess(`Created ${id}. Opening the loaded guidelines list.`);
      onImported(id);
      window.setTimeout(() => {
        resetAndClose();
        document
          .querySelector("#loaded-guidelines")
          ?.scrollIntoView({ behavior: "smooth", block: "start" });
      }, 600);
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "Could not create the blank guideline.",
      );
    } finally {
      setWorking(false);
    }
  };

  const importDraft = async () => {
    if (!draft || draft.likely_incorrect) return;
    setWorking(true);
    setError(null);
    try {
      const response = await fetch("/api/guidance/local/import", {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          "X-Requested-With": "XMLHttpRequest",
        },
        body: JSON.stringify({ draft }),
      });
      if (!response.ok) {
        throw new Error(
          await readErrorDetail(response, "Could not import the guideline."),
        );
      }
      onImported(draft.metadata.short_code);
      resetAndClose();
      document
        .querySelector("#loaded-guidelines")
        ?.scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "Could not import the guideline.",
      );
    } finally {
      setWorking(false);
    }
  };

  return (
    <Dialog open={open} onClose={resetAndClose} fullWidth maxWidth="md">
      <DialogTitle>Import local guideline</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ pt: 1 }}>
          {error && <Alert severity="error">{error}</Alert>}
          {success && <Alert severity="success">{success}</Alert>}
          <TextField
            label="Short code"
            value={shortCode}
            onChange={(event) => setShortCode(event.target.value.toUpperCase())}
            helperText="Example: SEL-MSK-01"
          />
          <TextField
            label="Guideline title"
            value={title}
            onChange={(event) => setTitle(event.target.value)}
          />
          <TextField
            label="Guideline text (optional)"
            helperText="Optional. For Build by hand, leave this empty and click Create blank. The title becomes the recommendation text."
            value={text}
            onChange={(event) => {
              setText(event.target.value);
              setDraft(null);
            }}
            multiline
            minRows={8}
          />
          <Typography variant="body2" color="text.secondary">
            Create blank needs only short code and title. Then open
            Recommendations and choose Build by hand.
          </Typography>
          {draft && (
            <Stack direction="row" spacing={1}>
              <Chip
                label={draft.likely_incorrect ? "Needs correction" : "Verified"}
                color={draft.likely_incorrect ? "error" : "success"}
              />
              <Chip
                label={`${draft.chapters.reduce(
                  (total, chapter) => total + chapter.recommendations.length,
                  0,
                )} recommendations`}
              />
            </Stack>
          )}
          {draft?.verification_errors.map((message) => (
            <Alert key={message} severity="warning">
              {message}
            </Alert>
          ))}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button type="button" onClick={resetAndClose}>
          Cancel
        </Button>
        <Button
          type="button"
          variant="contained"
          onClick={createBlank}
          disabled={!canCreateBlank || working}
        >
          {working ? "Creating..." : "Create blank"}
        </Button>
        <Button
          type="button"
          onClick={structure}
          disabled={!canStructure || working}
        >
          Structure and verify
        </Button>
        <Button
          type="button"
          variant="outlined"
          onClick={importDraft}
          disabled={!draft || draft.likely_incorrect || working}
        >
          Import structured
        </Button>
      </DialogActions>
    </Dialog>
  );
}
