/**
 * Highlight-and-code editor for a paused extraction review.
 *
 * Atlas: DI-4A012A59 / DO-E7824FED
 */
"use client";

import { useEffect, useState } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import LetterMarkdownView from "@/app/admin/validation-lab/LetterMarkdownView";
import { letterHighlightMarks } from "@/app/admin/validation-lab/letterHighlight";

interface DraftEntity {
  text: string;
  semantic_tag?: string;
}

interface Props {
  taskId: string;
  open: boolean;
  onClose: () => void;
  onUnlocked: () => void;
}

export default function ExtractionQualityReviewDialog({
  taskId,
  open,
  onClose,
  onUnlocked,
}: Props) {
  const [sourceText, setSourceText] = useState("");
  const [entities, setEntities] = useState<DraftEntity[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open || !taskId) return;
    setError("");
    fetch(`/api/operations/extraction-reviews/${taskId}`, {
      credentials: "include",
      headers: { "X-Requested-With": "XMLHttpRequest" },
    })
      .then((res) => {
        if (!res.ok) throw new Error("load");
        return res.json();
      })
      .then((data) => {
        setSourceText(String(data.source_text || ""));
        setEntities(Array.isArray(data.draft_entities) ? data.draft_entities : []);
      })
      .catch(() => setError("Could not load the letter. Try again."));
  }, [open, taskId]);

  const marks = letterHighlightMarks(entities);
  const addSelection = () => {
    const text = window.getSelection()?.toString().trim() || "";
    if (!text) return;
    setEntities((prev) =>
      prev.some((row) => row.text === text) ? prev : [...prev, { text }],
    );
  };
  const unlock = async () => {
    setBusy(true);
    setError("");
    try {
      const res = await fetch("/api/operations/extraction-reviews/complete", {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          "X-Requested-With": "XMLHttpRequest",
        },
        body: JSON.stringify({
          task_id: taskId,
          source_text: sourceText,
          reviewed_entities: entities,
          resolved_by: "operations_ui",
        }),
      });
      if (!res.ok) throw new Error("complete");
      onUnlocked();
    } catch {
      setError("Could not unlock the referral. Check the facts and try again.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="md">
      <DialogTitle>Check the draft facts</DialogTitle>
      <DialogContent>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          Highlight text on the letter to add a fact. Remove a chip if it is wrong.
          Then unlock the referral.
        </Typography>
        {error ? (
          <Typography color="error" sx={{ mb: 2 }}>
            {error}
          </Typography>
        ) : null}
        <Box onMouseUp={addSelection} data-testid="extraction-quality-letter">
          <LetterMarkdownView
            text={sourceText}
            marks={marks}
            emptyLabel="No letter text on this run."
          />
        </Box>
        <Stack direction="row" gap={1} flexWrap="wrap" sx={{ mt: 2 }}>
          {entities.map((row) => (
            <Chip
              key={row.text}
              label={row.text}
              onDelete={() =>
                setEntities((prev) => prev.filter((item) => item.text !== row.text))
              }
            />
          ))}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={busy}>
          Back
        </Button>
        <Button
          variant="contained"
          onClick={() => void unlock()}
          disabled={busy || entities.length === 0}
        >
          Unlock referral
        </Button>
      </DialogActions>
    </Dialog>
  );
}
