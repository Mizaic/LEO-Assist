"use client";

import { useState } from "react";
import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Drawer from "@mui/material/Drawer";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";

interface DiffBuckets {
  added: string[];
  removed: string[];
  modified: string[];
}

interface Props {
  code: string | null;
  onClose: () => void;
  onImported: () => void;
}

export default function LocalGuidelineChangesDrawer({
  code,
  onClose,
  onImported,
}: Props) {
  const [text, setText] = useState("");
  const [diff, setDiff] = useState<DiffBuckets | null>(null);
  const [draft, setDraft] = useState<Record<string, unknown> | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reset = () => {
    setText("");
    setDiff(null);
    setDraft(null);
    setError(null);
    setBusy(false);
  };

  const handleClose = () => {
    reset();
    onClose();
  };

  const handleRestructure = async () => {
    if (!code || text.trim().length < 20) return;
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`/api/guidance/local/${encodeURIComponent(code)}/re-structure`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });
      if (!res.ok) throw new Error(await res.text());
      const body = await res.json();
      setDraft(body.draft);
      setDiff(body.diff);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not re-structure.");
    } finally {
      setBusy(false);
    }
  };

  const handleReimport = async () => {
    if (!code || !draft) return;
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`/api/guidance/local/${encodeURIComponent(code)}/re-import`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ draft }),
      });
      if (!res.ok) throw new Error(await res.text());
      reset();
      onImported();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not re-import.");
      setBusy(false);
    }
  };

  return (
    <Drawer anchor="right" open={Boolean(code)} onClose={handleClose}>
      <Stack spacing={2} sx={{ width: 440, p: 3 }}>
        <Typography variant="h6" component="h2">Update local guideline</Typography>
        <Typography variant="body2">
          Paste the updated guideline text for {code}. We will show what changed before you import.
        </Typography>
        <TextField
          label="Updated guideline text"
          value={text}
          onChange={(e) => setText(e.target.value)}
          multiline
          minRows={8}
          fullWidth
        />
        {error && <Alert severity="error">{error}</Alert>}
        {diff && (
          <Alert severity="info">
            Added {diff.added.length}, removed {diff.removed.length}, modified {diff.modified.length}.
          </Alert>
        )}
        <Button
          variant="contained"
          onClick={() => void handleRestructure()}
          disabled={busy || text.trim().length < 20}
        >
          {busy && !draft ? "Comparing..." : "Re-structure and compare"}
        </Button>
        <Button
          variant="outlined"
          onClick={() => void handleReimport()}
          disabled={busy || !draft}
        >
          Confirm re-import
        </Button>
        <Button onClick={handleClose}>Close</Button>
      </Stack>
    </Drawer>
  );
}
